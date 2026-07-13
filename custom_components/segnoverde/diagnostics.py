"""Diagnostica scaricabile dalla UI di Home Assistant, con dati sensibili rimossi."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CODICE_CLIENTE, CONF_PASSWORD, DOMAIN
from .coordinator import SegnoverdeCoordinator

TO_REDACT = {
    CONF_CODICE_CLIENTE,
    CONF_PASSWORD,
    "codice_cliente",
    "download_token",
    "numero_fattura",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Restituisce diagnostica utile per le issue senza credenziali o token."""
    coordinator: SegnoverdeCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator_data = asdict(coordinator.data) if coordinator.data else {}
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": async_redact_data(coordinator_data, TO_REDACT),
        "update_interval_seconds": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
    }
