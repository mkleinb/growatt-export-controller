"""Switch platform for Growatt Export Controller."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrowattExportControllerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: GrowattExportControllerCoordinator = runtime["coordinator"]
    async_add_entities([GrowattMeterEnableSwitch(coordinator, entry)])


class GrowattMeterEnableSwitch(CoordinatorEntity[GrowattExportControllerCoordinator], SwitchEntity):
    """Enable or disable the meter-based export limit."""

    _attr_has_entity_name = True
    _attr_name = "Meter Enable"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: GrowattExportControllerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_meter_enable"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Export Controller",
        }

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.meter_enabled)

    async def async_turn_on(self, **kwargs) -> None:
        percentage = self.coordinator.data.export_percentage
        _LOGGER.warning("Meter switch turn_on requested: percentage=%s", percentage)
        await self.coordinator.async_set_export_limit(percentage, True)

    async def async_turn_off(self, **kwargs) -> None:
        percentage = self.coordinator.data.export_percentage
        _LOGGER.warning("Meter switch turn_off requested: percentage=%s", percentage)
        await self.coordinator.async_set_export_limit(percentage, False)
