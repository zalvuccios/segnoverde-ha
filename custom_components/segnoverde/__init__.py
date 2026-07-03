"""Integrazione Home Assistant per Segnoverde (area clienti)."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SegnoverdeApiClient,
    SegnoverdeAuthError,
    SegnoverdePwdExpiredError,
)
from .const import (
    CONF_CODICE_CLIENTE,
    CONF_DOWNLOAD_FOLDER,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import SegnoverdeCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SCARICA_PDF = "scarica_pdf"
SERVICE_FORZA_AGGIORNAMENTO = "forza_aggiornamento"
SERVICE_SCARICA_STORICO = "scarica_storico"

SCHEMA_SCARICA_PDF = vol.Schema(
    {
        vol.Optional("numero_fattura"): cv.string,
    }
)


def _compute_scan_interval(entry: ConfigEntry) -> timedelta:
    """Ricava il scan_interval (timedelta) dalle options del config entry."""
    hours = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, 12)
    )
    try:
        scan_interval = timedelta(hours=int(hours))
    except (TypeError, ValueError):
        scan_interval = DEFAULT_SCAN_INTERVAL
    if scan_interval < MIN_SCAN_INTERVAL:
        scan_interval = MIN_SCAN_INTERVAL
    return scan_interval


def _compute_download_folder(entry: ConfigEntry) -> str | None:
    """Cartella di download PDF (None per disabilitare)."""
    folder = entry.options.get(
        CONF_DOWNLOAD_FOLDER, entry.data.get(CONF_DOWNLOAD_FOLDER, "segnoverde_pdfs")
    )
    if not folder:
        return None
    return str(folder)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup di un'istanza Segnoverde da config entry."""
    codice_cliente = entry.data[CONF_CODICE_CLIENTE]
    password = entry.data[CONF_PASSWORD]
    scan_interval = _compute_scan_interval(entry)
    download_folder = _compute_download_folder(entry)

    session = async_get_clientsession(hass)
    client = SegnoverdeApiClient(codice_cliente, password, session)

    # Prova login iniziale
    try:
        await client.async_login()
    except SegnoverdePwdExpiredError as err:
        raise ConfigEntryAuthFailed("Password scaduta sul portale Segnoverde") from err
    except SegnoverdeAuthError as err:
        raise ConfigEntryAuthFailed(f"Credenziali non valide: {err}") from err
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Portale Segnoverde non raggiungibile: {err}") from err

    coordinator = SegnoverdeCoordinator(
        hass, client, entry, scan_interval, download_folder
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_services(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rimuovi un'istanza Segnoverde."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: SegnoverdeCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()
    return unload_ok


async def async_update_options(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Aggiorna le options senza reinstallare."""
    # HA richiama async_setup_entry dopo un reload automatico
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Registra i servizi dell'integrazione."""

    def _get_coordinator() -> SegnoverdeCoordinator | None:
        return hass.data.get(DOMAIN, {}).get(entry.entry_id)

    async def _scarica_pdf(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        if coordinator is None:
            _LOGGER.warning("Coordinator Segnoverde non disponibile per il servizio")
            return
        numero = call.data.get("numero_fattura")
        await coordinator.async_scarica_pdf_fattura(numero)

    async def _forza_aggiornamento(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        if coordinator is None:
            return
        await coordinator.async_request_refresh()

    async def _scarica_storico(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        if coordinator is None:
            return
        await coordinator.async_scarica_storico()

    if not hass.services.has_service(DOMAIN, SERVICE_SCARICA_PDF):
        hass.services.async_register(
            DOMAIN, SERVICE_SCARICA_PDF, _scarica_pdf, schema=SCHEMA_SCARICA_PDF
        )
    if not hass.services.has_service(DOMAIN, SERVICE_FORZA_AGGIORNAMENTO):
        hass.services.async_register(
            DOMAIN, SERVICE_FORZA_AGGIORNAMENTO, _forza_aggiornamento
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SCARICA_STORICO):
        hass.services.async_register(DOMAIN, SERVICE_SCARICA_STORICO, _scarica_storico)