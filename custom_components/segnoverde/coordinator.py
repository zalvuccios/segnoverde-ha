"""Coordinator dati per Segnoverde."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import STORAGE_DIR

from .api import (
    SegnoverdeApiClient,
    SegnoverdeApiError,
    SegnoverdeAuthError,
    SegnoverdePwdExpiredError,
)
from .const import DOMAIN, STATO_PAGATA
from .parser import parse_fattura_pdf, parse_storico_annuo

_LOGGER = logging.getLogger(__name__)


@dataclass
class SegnoverdeData:
    """Stato dei dati Segnoverde esposto alle entità."""
    fatture: list[dict[str, Any]] = field(default_factory=list)
    ultima_fattura: dict[str, Any] = field(default_factory=dict)
    fatture_non_pagate: list[dict[str, Any]] = field(default_factory=list)
    annuo: dict[str, Any] = field(default_factory=dict)
    spesa_annua: float | None = None
    storico_kwh: dict[str, float] = field(default_factory=dict)
    storico_importi: dict[str, float] = field(default_factory=dict)
    storico_mensile: dict[str, dict[str, Any]] = field(default_factory=dict)
    codice_cliente: str = ""
    login_ok: bool = True
    last_update: str = ""
    history_sync_in_progress: bool = False
    history_sync_done: int = 0
    history_sync_total: int = 0


def _fattura_to_dict(f) -> dict[str, Any]:
    return {
        "mese": f.mese,
        "anno": f.anno,
        "mese_idx": f.mese_idx,
        "numero_fattura": f.numero_fattura,
        "importo": f.importo,
        "scadenza": f.scadenza.isoformat() if f.scadenza else None,
        "stato": f.stato,
        "kwh": f.kwh,
        "prezzo_medio": f.prezzo_medio,
        "periodo": f.periodo,
        "f1": f.f1,
        "f2": f.f2,
        "f3": f.f3,
        "potenza_max": f.potenza_max,
        "download_token": f.download_token,
    }


class SegnoverdeCoordinator(DataUpdateCoordinator):
    """Coordinator: scarica elenco fatture e dettaglio ultima bolletta."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SegnoverdeApiClient,
        entry: ConfigEntry,
        scan_interval: timedelta,
        download_folder: str | None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=scan_interval,
        )
        self.client = client
        self._entry = entry
        self._download_folder = download_folder
        self._cache_file = os.path.join(
            hass.config.path(STORAGE_DIR),
            f"{DOMAIN}_{entry.entry_id}.json",
        )
        self._cached_storico: dict[str, float] = {}
        self._cached_storico_importi: dict[str, float] = {}
        self._cached_storico_annuo: dict[str, dict[str, Any]] = {}
        self._cached_fatture_pdf: set[str] = set()
        self._history_lock = asyncio.Lock()
        self.history_sync_in_progress = False
        self.history_sync_done = 0
        self.history_sync_total = 0

    async def async_load_cache(self) -> None:
        """Carica il cache dal disco senza bloccare l'event loop."""
        await self.hass.async_add_executor_job(self._load_cache)

    @property
    def has_missing_history(self) -> bool:
        """True se esistono mesi fatturati senza kWh estratti dal PDF."""
        return any(
            key not in self._cached_storico
            for key in self._cached_storico_importi
        )

    def _publish_history_progress(self) -> None:
        """Aggiorna in tempo reale gli attributi del sensore diagnostico."""
        if self.data is None:
            return
        self.data.history_sync_in_progress = self.history_sync_in_progress
        self.data.history_sync_done = self.history_sync_done
        self.data.history_sync_total = self.history_sync_total
        self.async_set_updated_data(self.data)

    def _load_cache(self) -> None:
        """Carica lo storico kWh precedentemente scaricato dal cache file.

        Eseguito sempre tramite ``async_load_cache`` (executor) per evitare
        blocking I/O nell'event loop.
        """
        try:
            with open(self._cache_file, encoding="utf-8") as fp:
                cache = json.load(fp)
            self._cached_storico = dict(cache.get("storico_kwh", {}))
            self._cached_storico_importi = dict(cache.get("storico_importi", {}))
            self._cached_storico_annuo = dict(cache.get("storico_annuo", {}))
            self._cached_fatture_pdf = set(cache.get("fatture_pdf", []))
            _LOGGER.debug(
                "Cache caricato: %s voci storico kWh, %s importi",
                len(self._cached_storico), len(self._cached_storico_importi),
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._cached_storico = {}
            self._cached_storico_importi = {}
            self._cached_storico_annuo = {}
            self._cached_fatture_pdf = set()

    def _save_cache(
        self,
        storico: dict[str, float],
        fatture_pdf: set[str],
        storico_importi: dict[str, float] | None = None,
        storico_annuo: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "storico_kwh": storico,
                        "storico_importi": storico_importi or {},
                        "storico_annuo": storico_annuo or {},
                        "fatture_pdf": list(fatture_pdf),
                    },
                    fp,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError as err:
            _LOGGER.warning("Impossibile salvare cache Segnoverde: %s", err)

    async def _async_update_data(self) -> SegnoverdeData:
        try:
            q_session = await self.client.async_login()
            tokens = await self.client.async_get_tokens(q_session)
            fatture = await self.client.async_get_fatture(tokens["bollette"])
        except SegnoverdePwdExpiredError as err:
            raise UpdateFailed("Password scaduta: rivalidare le credenziali.") from err
        except SegnoverdeAuthError as err:
            raise UpdateFailed(f"Credenziali Segnoverde non valide: {err}") from err
        except SegnoverdeApiError as err:
            raise UpdateFailed(f"Errore portale Segnoverde: {err}") from err

        nuova_storico: dict[str, float] = dict(self._cached_storico)
        nuova_storico_importi: dict[str, float] = dict(self._cached_storico_importi)
        nuovo_storico_annuo: dict[str, dict[str, Any]] = dict(self._cached_storico_annuo)
        fatts_pdf_keys: set[str] = set(self._cached_fatture_pdf)
        storico_annuo: dict[str, Any] = {}

        # Ripristina importi e kWh dal cache su TUTTE le fatture. Gli oggetti
        # Fattura vengono ricreati a ogni refresh, quindi senza questo passaggio
        # l'ultima bolletta verrebbe riscaricata inutilmente ogni volta.
        for f in fatture:
            if not f.mese_idx:
                continue
            chiave = f"{f.mese_idx:02d}_{f.anno}"
            nuova_storico_importi[chiave] = f.importo
            if chiave in nuova_storico:
                f.kwh = nuova_storico[chiave]

        if fatture:
            ult = fatture[0]  # più recente in cima
            # Scarica SEMPRE il PDF dell'ultima fattura se non abbiamo ancor
            # i dati kWh/bolletta (anche se era già scaricata in cache ma il
            # parsing era fallito). Questo garantisce recupero automatico.
            ha_dati_pdf = ult.kwh is not None
            # Recupera lo storico annuo dal cache se presente per questa fattura
            if ult.numero_fattura in nuovo_storico_annuo and not storico_annuo:
                storico_annuo = dict(nuovo_storico_annuo[ult.numero_fattura])
            if ult.download_token and (
                ult.numero_fattura not in fatts_pdf_keys or not ha_dati_pdf
                or not storico_annuo
            ):
                _LOGGER.info(
                    "Segnoverde: scarico PDF ultima fattura %s",
                    ult.numero_fattura,
                )
                try:
                    pdf_bytes = await self.client.async_download_pdf(
                        ult.download_token
                    )
                    fatts_pdf_keys.add(ult.numero_fattura)
                    await self.hass.async_add_executor_job(
                        parse_fattura_pdf, pdf_bytes, ult
                    )
                    if ult.kwh is None:
                        _LOGGER.error(
                            "Segnoverde: parsing PDF fattura %s NON ha estratto "
                            "i kWh. Verifica che 'pdfplumber' sia installato "
                            "correttamente nel proprio ambiente Home Assistant.",
                            ult.numero_fattura,
                        )
                    else:
                        storico_annuo = await self.hass.async_add_executor_job(
                            parse_storico_annuo, pdf_bytes
                        )
                        nuovo_storico_annuo[ult.numero_fattura] = dict(storico_annuo)
                        await self.hass.async_add_executor_job(
                            self._maybe_save_pdf, ult, pdf_bytes
                        )
                except SegnoverdeApiError as err:
                    _LOGGER.error(
                        "Segnoverde: download PDF ultima fattura %s fallito: %s",
                        ult.numero_fattura,
                        err,
                    )

            if ult.kwh is not None and ult.mese_idx:
                chiave = f"{ult.mese_idx:02d}_{ult.anno}"
                nuova_storico[chiave] = ult.kwh

        fatture_dict = [_fattura_to_dict(f) for f in fatture]
        non_pagate = [
            f for f in fatture_dict if f["stato"].upper() != STATO_PAGATA
        ]
        ultima = fatture_dict[0] if fatture_dict else {}
        spesa_annua = storico_annuo.get("spesa_annua")

        # Totale consumo annuo = F1 + F2 + F3
        f1, f2, f3 = (storico_annuo.get("f1"), storico_annuo.get("f2"), storico_annuo.get("f3"))
        totale_annuo = None
        if f1 is not None or f2 is not None or f3 is not None:
            totale_annuo = (f1 or 0) + (f2 or 0) + (f3 or 0)

        annuo = {
            "f1": f1,
            "f2": f2,
            "f3": f3,
            "totale": totale_annuo,
            "periodo_dal": storico_annuo.get("periodo_dal"),
            "periodo_al": storico_annuo.get("periodo_al"),
            "spesa_periodo_dal": storico_annuo.get("spesa_periodo_dal"),
            "spesa_periodo_al": storico_annuo.get("spesa_periodo_al"),
        }

        # Storico mensile combinato: {mm_aaaa: {importo, kwh, stato, numero_fattura, scadenza}}
        tutte_chiavi = sorted(set(nuova_storico) | set(nuova_storico_importi))
        mappa_fatture = {
            f"{f.mese_idx:02d}_{f.anno}" if f.mese_idx else None: f
            for f in fatture
        }
        storico_mensile: dict[str, dict[str, Any]] = {}
        for chiave in tutte_chiavi:
            f_obj = mappa_fatture.get(chiave)
            storico_mensile[chiave] = {
                "importo": nuova_storico_importi.get(chiave),
                "kwh": nuova_storico.get(chiave),
                "stato": (f_obj.stato if f_obj else None),
                "numero_fattura": (f_obj.numero_fattura if f_obj else None),
                "scadenza": (
                    f_obj.scadenza.isoformat() if f_obj and f_obj.scadenza else None
                ),
            }

        self._cached_storico = nuova_storico
        self._cached_storico_importi = nuova_storico_importi
        self._cached_storico_annuo = nuovo_storico_annuo
        self._cached_fatture_pdf = fatts_pdf_keys
        await self.hass.async_add_executor_job(
            self._save_cache,
            nuova_storico,
            fatts_pdf_keys,
            nuova_storico_importi,
            nuovo_storico_annuo,
        )

        return SegnoverdeData(
            fatture=fatture_dict,
            ultima_fattura=ultima,
            fatture_non_pagate=non_pagate,
            annuo=annuo,
            spesa_annua=spesa_annua,
            storico_kwh=dict(nuova_storico),
            storico_importi=dict(nuova_storico_importi),
            storico_mensile=storico_mensile,
            codice_cliente=self._entry.data.get("codice_cliente", ""),
            login_ok=True,
            last_update=datetime.now().isoformat(),
            history_sync_in_progress=self.history_sync_in_progress,
            history_sync_done=self.history_sync_done,
            history_sync_total=self.history_sync_total,
        )

    def _maybe_save_pdf(self, fattura, pdf_bytes: bytes) -> None:
        """Salva su disco il PDF della fattura, se configurato."""
        if not self._download_folder:
            return
        folder = self.hass.config.path(self._download_folder)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as err:
            _LOGGER.warning("Impossibile creare cartella %s: %s", folder, err)
            return
        nome = (
            f"{fattura.anno}_{fattura.mese_idx:02d}_"
            f"{fattura.numero_fattura.replace('/', '_')}.pdf"
            if fattura.mese_idx
            else f"{fattura.numero_fattura.replace('/', '_')}.pdf"
        )
        path = os.path.join(folder, nome)
        try:
            with open(path, "wb") as fp:
                fp.write(pdf_bytes)
            _LOGGER.debug("PDF salvato: %s", path)
        except OSError as err:
            _LOGGER.warning("Impossibile salvare PDF %s: %s", path, err)

    async def async_scarica_storico(self) -> None:
        """Popola automaticamente solo i PDF realmente mancanti dal cache."""
        if self._history_lock.locked():
            _LOGGER.info("Sincronizzazione storico Segnoverde già in corso")
            return

        async with self._history_lock:
            self.history_sync_in_progress = True
            self.history_sync_done = 0
            self.history_sync_total = 0
            self._publish_history_progress()
            try:
                q_session = await self.client.async_login()
                tokens = await self.client.async_get_tokens(q_session)
                fatture = await self.client.async_get_fatture(tokens["bollette"])

                nuova_storico = dict(self._cached_storico)
                nuova_importi = dict(self._cached_storico_importi)
                nuovo_storico_annuo = dict(self._cached_storico_annuo)
                fatts_keys = set(self._cached_fatture_pdf)
                prima_numero = fatture[0].numero_fattura if fatture else None

                for f in fatture:
                    if f.mese_idx:
                        nuova_importi[f"{f.mese_idx:02d}_{f.anno}"] = f.importo

                mancanti = []
                for f in fatture:
                    chiave = f"{f.mese_idx:02d}_{f.anno}" if f.mese_idx else None
                    ha_kwh = chiave is not None and chiave in nuova_storico
                    manca_annuo = (
                        f.numero_fattura == prima_numero
                        and f.numero_fattura not in nuovo_storico_annuo
                    )
                    if f.download_token and (not ha_kwh or manca_annuo):
                        mancanti.append(f)

                self.history_sync_total = len(mancanti)
                self._publish_history_progress()
                for f in mancanti:
                    try:
                        pdf = await self.client.async_download_pdf(f.download_token)
                    except SegnoverdeApiError as err:
                        _LOGGER.warning("Download %s fallito: %s", f.numero_fattura, err)
                        self.history_sync_done += 1
                        self._publish_history_progress()
                        continue

                    fatts_keys.add(f.numero_fattura)
                    await self.hass.async_add_executor_job(parse_fattura_pdf, pdf, f)
                    if f.kwh is not None and f.mese_idx:
                        nuova_storico[f"{f.mese_idx:02d}_{f.anno}"] = f.kwh
                    if f.numero_fattura == prima_numero:
                        annuale = await self.hass.async_add_executor_job(
                            parse_storico_annuo, pdf
                        )
                        if annuale:
                            nuovo_storico_annuo[f.numero_fattura] = dict(annuale)
                    await self.hass.async_add_executor_job(
                        self._maybe_save_pdf, f, pdf
                    )
                    self.history_sync_done += 1
                    self._publish_history_progress()
                    await asyncio.sleep(1.0)  # rate-limit cortese

                self._cached_storico = nuova_storico
                self._cached_storico_importi = nuova_importi
                self._cached_storico_annuo = nuovo_storico_annuo
                self._cached_fatture_pdf = fatts_keys
                await self.hass.async_add_executor_job(
                    self._save_cache,
                    nuova_storico,
                    fatts_keys,
                    nuova_importi,
                    nuovo_storico_annuo,
                )
            except (SegnoverdeAuthError, SegnoverdeApiError) as err:
                _LOGGER.error("Sincronizzazione storico fallita: %s", err)
            finally:
                self.history_sync_in_progress = False
                self._publish_history_progress()

        await self.async_request_refresh()

    async def async_scarica_pdf_fattura(self, numero_fattura: str | None) -> str | None:
        """Scarica il PDF di una fattura specifica (o l'ultima se None)."""
        try:
            q_session = await self.client.async_login()
            tokens = await self.client.async_get_tokens(q_session)
            fatture = await self.client.async_get_fatture(tokens["bollette"])
        except (SegnoverdeAuthError, SegnoverdeApiError) as err:
            _LOGGER.error("Login fallito: %s", err)
            return None

        target = None
        if numero_fattura:
            target = next(
                (f for f in fatture if f.numero_fattura == numero_fattura),
                None,
            )
        else:
            target = fatture[0] if fatture else None
        if not target or not target.download_token:
            return None
        try:
            pdf = await self.client.async_download_pdf(target.download_token)
        except SegnoverdeApiError as err:
            _LOGGER.warning("Download %s fallito: %s", target.numero_fattura, err)
            return None
        await self.hass.async_add_executor_job(self._maybe_save_pdf, target, pdf)
        return target.numero_fattura