"""Binary sensor 'fatture non pagate' per Segnoverde."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SegnoverdeCoordinator, SegnoverdeData
from .entity import SegnoverdeEntity


@dataclass(frozen=True, kw_only=True)
class SegnoverdeBinarySensorDescription(BinarySensorEntityDescription):
    """Descrizione binary sensor Segnoverde."""
    value_fn: Any  # Callable[[SegnoverdeData], bool]


BINARY_SENSORS: tuple[SegnoverdeBinarySensorDescription, ...] = (
    SegnoverdeBinarySensorDescription(
        key="fatture_non_pagate",
        translation_key="fatture_non_pagate",
        value_fn=lambda d: bool(d.fatture_non_pagate),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup binary sensor Segnoverde."""
    coordinator: SegnoverdeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SegnoverdeBinarySensor(coordinator, entry, desc)
        for desc in BINARY_SENSORS
    )


class SegnoverdeBinarySensor(SegnoverdeEntity, BinarySensorEntity):
    """Binary sensor Segnoverde."""

    entity_description: SegnoverdeBinarySensorDescription

    def __init__(
        self,
        coordinator: SegnoverdeCoordinator,
        entry: ConfigEntry,
        description: SegnoverdeBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}-{description.key}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return bool(self.entity_description.value_fn(data))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        non_pagate = data.fatture_non_pagate
        return {
            "numero_fatture_non_pagate": len(non_pagate),
            "elenco": [
                {
                    "numero_fattura": f["numero_fattura"],
                    "importo": f["importo"],
                    "scadenza": f["scadenza"],
                    "stato": f["stato"],
                }
                for f in non_pagate
            ],
        }