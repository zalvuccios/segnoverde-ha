"""Button entità Segnoverde (cliccabili dalla card Lovelace)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SegnoverdeCoordinator
from .entity import SegnoverdeEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SegnoverdeButtonDescription(ButtonEntityDescription):
    """Descrizione button Segnoverde."""
    press_fn: Callable[[SegnoverdeCoordinator], Awaitable[None]]


async def _press_scarica_storico(coord: SegnoverdeCoordinator) -> None:
    """Esegue lo scarico storico in background; se già in corso, evita duplicazione."""
    if getattr(coord, "_scarico_storico_in_corso", False):
        _LOGGER.info("Scarico storico già in corso, ignoro pressione button")
        return
    setattr(coord, "_scarico_storico_in_corso", True)
    try:
        await coord.async_scarica_storico()
    finally:
        setattr(coord, "_scarico_storico_in_corso", False)


async def _press_forza_aggiornamento(coord: SegnoverdeCoordinator) -> None:
    await coord.async_request_refresh()


async def _press_scarica_pdf_ultima(coord: SegnoverdeCoordinator) -> None:
    await coord.async_scarica_pdf_fattura(None)


BUTTONS: tuple[SegnoverdeButtonDescription, ...] = (
    SegnoverdeButtonDescription(
        key="scarica_storico",
        translation_key="scarica_storico",
        press_fn=_press_scarica_storico,
    ),
    SegnoverdeButtonDescription(
        key="forza_aggiornamento",
        translation_key="forza_aggiornamento",
        press_fn=_press_forza_aggiornamento,
    ),
    SegnoverdeButtonDescription(
        key="scarica_pdf_ultima",
        translation_key="scarica_pdf_ultima",
        press_fn=_press_scarica_pdf_ultima,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup button Segnoverde."""
    coordinator: SegnoverdeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SegnoverdeButton(coordinator, entry, desc) for desc in BUTTONS
    )


class SegnoverdeButton(SegnoverdeEntity, ButtonEntity):
    """Button Segnoverde."""

    entity_description: SegnoverdeButtonDescription

    def __init__(
        self,
        coordinator: SegnoverdeCoordinator,
        entry: ConfigEntry,
        description: SegnoverdeButtonDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}-{description.key}"

    async def async_press(self) -> None:
        """Azione associata al button."""
        await self.entity_description.press_fn(self.coordinator)