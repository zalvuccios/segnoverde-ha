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
from .const import (
    DOMAIN,
    STATO_PAGATA,
)
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
    codice_cliente: str = ""
    login_ok: bool = True
    last_update: str = ""


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
        self._client = client
        self._entry = entry
        self._download_folder = download_folder
        self._cache_file = os.path.join(
            hass.config.path(STORAGE_DIR),
            f"{DOMAIN}_{entry.entry_id}.json",
        )
        self._cached_storico: dict[str, float] = {}
        self._cached_fatture_pdf: set[str] = set()
        self._load_cache()

    def _load_cache(self) -> None:
        """Carica lo storico kWh precedentemente scaricato dal cache file."""
        try:
            with open(self._cache_file, encoding="utf-8") as fp:
                cache = json.load(fp)
            self._cached_storico = dict(cache.get("storico_kwh", {}))
            self._cached_fatture_pdf = set(cache.get("fatture_pdf", []))
            _LOGGER.debug(
                "Cache caricato: %s voci storico kWh", len(self._cached_storico)
            )
        except (FileNotFoundError, json.JSONDecodeError):
            self._cached_storico = {}
            self._cached_fatture_pdf = set()

    def _save_cache(
        self, storico: dict[str, float], fatture_pdf: set[str]
    ) -> None:
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as fp:
                json.dump(
                    {"storico_kwh": storico, "fatture_pdf": list(fatture_pdf)},
                    fp,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError as err:
            _LOGGER.warning("Impossibile salvare cache Segnoverde: %s", err)

    async def _async_update_data(self) -> SegnoverdeData:
        try:
            q_session = await self._client.async_login()
            tokens = await self._client.async_get_tokens(q_session)
            fatture = await self._client.async_get_fatture(tokens["bollette"])
        except SegnoverdePwdExpiredError as err:
            raise UpdateFailed("Password scaduta: rivalidare le credenziali.") from err
        except SegnoverdeAuthError as err:
            raise UpdateFailed(f"Credenziali Segnoverde non valide: {err}") from err
        except SegnoverdeApiError as err:
            raise UpdateFailed(f"Errore portale Segnoverde: {err}") from err

        nuova_storico: dict[str, float] = dict(self._cached_storico)
        fatts_pdf_keys: set[str] = set(self._cached_fatture_pdf)
        storico_annuo: dict[str, Any] = {}

        if fatture:
            ult = fatture[0]  # più recente in cima
            if ult.download_token and ult.numero_fattura not in fatts_pdf_keys:
                try:
                    pdf_bytes = await self._client.async_download_pdf(
                        ult.download_token
                    )
                    fatts_pdf_keys.add(ult.numero_fattura)
                    parse_fattura_pdf(pdf_bytes, ult)
                    storico_annuo = parse_storico_annuo(pdf_bytes)
                    self._maybe_save_pdf(ult, pdf_bytes)
                except SegnoverdeApiError as err:
                    _LOGGER.warning("Download ultima fattura fallito: %s", err)

            if ult.kwh is not None and ult.mese_idx:
                chiave = f"{ult.mese_idx:02d}_{ult.anno}"
                nuova_storico[chiave] = ult.kwh

            # Popola kWh dalle fatture già scaricate in passato (cache)
            for f in fatture[1:]:
                if f.kwh is None and f.mese_idx:
                    chiave = f"{f.mese_idx:02d}_{f.anno}"
                    if chiave in nuova_storico:
                        f.kwh = nuova_storico[chiave]

        fatture_dict = [_fattura_to_dict(f) for f in fatture]
        non_pagate = [
            f for f in fatture_dict if f["stato"].upper() != STATO_PAGATA
        ]
        ultima = fatture_dict[0] if fatture_dict else {}
        spesa_annua = storico_annuo.get("spesa_annua")
        annuo = {
            "f1": storico_annuo.get("f1"),
            "f2": storico_annuo.get("f2"),
            "f3": storico_annuo.get("f3"),
            "periodo_dal": storico_annuo.get("periodo_dal"),
            "periodo_al": storico_annuo.get("periodo_al"),
            "spesa_periodo_dal": storico_annuo.get("spesa_periodo_dal"),
            "spesa_periodo_al": storico_annuo.get("spesa_periodo_al"),
        }

        self._cached_storico = nuova_storico
        self._cached_fatture_pdf = fatts_pdf_keys
        self._save_cache(nuova_storico, fatts_pdf_keys)

        return SegnoverdeData(
            fatture=fatture_dict,
            ultima_fattura=ultima,
            fatture_non_pagate=non_pagate,
            annuo=annuo,
            spesa_annua=spesa_annua,
            storico_kwh=dict(nuova_storico),
            codice_cliente=self._entry.data.get("codice_cliente", ""),
            login_ok=True,
            last_update=datetime.now().isoformat(),
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
        """Scarica tutti i PDF non ancora in cache per popolare lo storico kWh."""
        try:
            q_session = await self._client.async_login()
            tokens = await self._client.async_get_tokens(q_session)
            fatture = await self._client.async_get_fatture(tokens["bollette"])
        except (SegnoverdeAuthError, SegnoverdeApiError) as err:
            _LOGGER.error("Login fallito per storico: %s", err)
            return

        nuova_storico: dict[str, float] = dict(self._cached_storico)
        fatts_keys: set[str] = set(self._cached_fatture_pdf)
        for f in fatture:
            if f.numero_fattura in fatts_keys or not f.download_token:
                continue
            try:
                pdf = await self._client.async_download_pdf(f.download_token)
            except SegnoverdeApiError as err:
                _LOGGER.warning("Download %s fallito: %s", f.numero_fattura, err)
                continue
            fatts_keys.add(f.numero_fattura)
            parse_fattura_pdf(pdf, f)
            if f.kwh is not None and f.mese_idx:
                nuova_storico[f"{f.mese_idx:02d}_{f.anno}"] = f.kwh
            self._maybe_save_pdf(f, pdf)
            await asyncio.sleep(1.0)  # rate-limit cortese
        self._cached_storico = nuova_storico
        self._cached_fatture_pdf = fatts_keys
        self._save_cache(nuova_storico, fatts_keys)
        await self.async_request_refresh()

    async def async_scarica_pdf_fattura(self, numero_fattura: str | None) -> str | None:
        """Scarica il PDF di una fattura specifica (o l'ultima se None)."""
        try:
            q_session = await self._client.async_login()
            tokens = await self._client.async_get_tokens(q_session)
            fatture = await self._client.async_get_fatture(tokens["bollette"])
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
            pdf = await self._client.async_download_pdf(target.download_token)
        except SegnoverdeApiError as err:
            _LOGGER.warning("Download %s fallito: %s", target.numero_fattura, err)
            return None
        self._maybe_save_pdf(target, pdf)
        return target.numero_fattura