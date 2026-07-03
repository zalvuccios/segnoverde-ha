"""Sensori Segnoverde."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .coordinator import SegnoverdeCoordinator, SegnoverdeData
from .entity import SegnoverdeEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SegnoverdeSensorDescription(SensorEntityDescription):
    """Descrive un sensore Segnoverde."""
    value_fn: Callable[[SegnoverdeData], StateType] = lambda d: None
    attr_fn: Callable[[SegnoverdeData], dict[str, Any]] = lambda d: {}
    exists_fn: Callable[[SegnoverdeData], bool] = lambda d: True


SENSORS: tuple[SegnoverdeSensorDescription, ...] = (
    SegnoverdeSensorDescription(
        key="ultima_fattura_importo",
        translation_key="ultima_fattura_importo",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EURO,
        value_fn=lambda d: d.ultima_fattura.get("importo"),
        attr_fn=lambda d: {
            "numero_fattura": d.ultima_fattura.get("numero_fattura"),
            "scadenza": d.ultima_fattura.get("scadenza"),
            "stato": d.ultima_fattura.get("stato"),
            "periodo": d.ultima_fattura.get("periodo"),
            "kwh": d.ultima_fattura.get("kwh"),
            "prezzo_medio": d.ultima_fattura.get("prezzo_medio"),
            "f1": d.ultima_fattura.get("f1"),
            "f2": d.ultima_fattura.get("f2"),
            "f3": d.ultima_fattura.get("f3"),
            "potenza_max": d.ultima_fattura.get("potenza_max"),
            "anno": d.ultima_fattura.get("anno"),
            "mese": d.ultima_fattura.get("mese"),
            "totale_fatture": len(d.fatture),
            "fatture_non_pagate": len(d.fatture_non_pagate),
            "ultimo_aggiornamento": d.last_update,
        },
        exists_fn=lambda d: bool(d.ultima_fattura),
    ),
    SegnoverdeSensorDescription(
        key="ultimo_consumo_kwh",
        translation_key="ultimo_consumo_kwh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.ultima_fattura.get("kwh"),
        attr_fn=lambda d: {
            "periodo": d.ultima_fattura.get("periodo"),
            "numero_fattura": d.ultima_fattura.get("numero_fattura"),
            "prezzo_medio": d.ultima_fattura.get("prezzo_medio"),
            "f1": d.ultima_fattura.get("f1"),
            "f2": d.ultima_fattura.get("f2"),
            "f3": d.ultima_fattura.get("f3"),
            "potenza_max": d.ultima_fattura.get("potenza_max"),
            "storico_kwh": dict(sorted(d.storico_kwh.items())),
        },
        exists_fn=lambda d: d.ultima_fattura.get("kwh") is not None,
    ),
    SegnoverdeSensorDescription(
        key="spesa_annua",
        translation_key="spesa_annua",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EURO,
        value_fn=lambda d: d.spesa_annua,
        attr_fn=lambda d: {
            "periodo_dal": d.annuo.get("periodo_dal"),
            "periodo_al": d.annuo.get("periodo_al"),
            "spesa_periodo_dal": d.annuo.get("spesa_periodo_dal"),
            "spesa_periodo_al": d.annuo.get("spesa_periodo_al"),
        },
        exists_fn=lambda d: d.spesa_annua is not None,
    ),
    SegnoverdeSensorDescription(
        key="consumo_annuo_f1",
        translation_key="consumo_annuo_f1",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.annuo.get("f1"),
        attr_fn=lambda d: {
            "periodo_dal": d.annuo.get("periodo_dal"),
            "periodo_al": d.annuo.get("periodo_al"),
        },
        exists_fn=lambda d: d.annuo.get("f1") is not None,
    ),
    SegnoverdeSensorDescription(
        key="consumo_annuo_f2",
        translation_key="consumo_annuo_f2",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.annuo.get("f2"),
        attr_fn=lambda d: {
            "periodo_dal": d.annuo.get("periodo_dal"),
            "periodo_al": d.annuo.get("periodo_al"),
        },
        exists_fn=lambda d: d.annuo.get("f2") is not None,
    ),
    SegnoverdeSensorDescription(
        key="consumo_annuo_f3",
        translation_key="consumo_annuo_f3",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.annuo.get("f3"),
        attr_fn=lambda d: {
            "periodo_dal": d.annuo.get("periodo_dal"),
            "periodo_al": d.annuo.get("periodo_al"),
        },
        exists_fn=lambda d: d.annuo.get("f3") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup sensori Segnoverde."""
    coordinator: SegnoverdeCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    entities = [
        SegnoverdeSensor(coordinator, entry, desc)
        for desc in SENSORS
        if data is None or desc.exists_fn(data)
    ]
    async_add_entities(entities)


class SegnoverdeSensor(SegnoverdeEntity, SensorEntity):
    """Sensore Segnoverde."""

    entity_description: SegnoverdeSensorDescription

    def __init__(
        self,
        coordinator: SegnoverdeCoordinator,
        entry: ConfigEntry,
        description: SegnoverdeSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}-{description.key}"

    @property
    def native_value(self) -> StateType:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.attr_fn(data)

    def _handle_coordinator_update(self) -> None:
        # Ricalcola disponibilità in base ad exists_fn
        data = self.coordinator.data
        if data is not None and not self.entity_description.exists_fn(data):
            self._attr_available = False
        else:
            self._attr_available = True
        super()._handle_coordinator_update()