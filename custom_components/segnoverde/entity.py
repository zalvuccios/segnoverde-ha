"""Entità base per Segnoverde."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_IDENTIFIERS
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SegnoverdeCoordinator


class SegnoverdeEntity(CoordinatorEntity[SegnoverdeCoordinator]):
    """Classe base per entità Segnoverde."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SegnoverdeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=f"Segnoverde {entry.data.get('codice_cliente', '')}",
            manufacturer="Segnoverde S.p.A.",
            model="Area Clienti",
            configuration_url="https://segnoverde-webcli.serviceict.it/PortaleClienti",
        )