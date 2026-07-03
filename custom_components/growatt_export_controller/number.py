"""Number platform for Growatt Export Controller."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrowattExportControllerCoordinator

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTION = NumberEntityDescription(
    key="export_percentage",
    name="Export Percentage",
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    icon="mdi:percent",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: GrowattExportControllerCoordinator = runtime["coordinator"]
    async_add_entities([GrowattExportPercentageNumber(coordinator, entry)])


class GrowattExportPercentageNumber(CoordinatorEntity[GrowattExportControllerCoordinator], NumberEntity):
    """Control the export percentage."""

    _attr_has_entity_name = True
    entity_description = NUMBER_DESCRIPTION

    def __init__(self, coordinator: GrowattExportControllerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_export_percentage"
        self._attr_name = self.entity_description.name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Export Controller",
        }

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data.export_percentage)

    async def async_set_native_value(self, value: float) -> None:
        percentage = int(round(value))
        meter_enabled = self.coordinator.data.meter_enabled
        _LOGGER.warning("Export percentage set requested: percentage=%s meter_enabled=%s", percentage, meter_enabled)
        await self.coordinator.async_set_export_limit(percentage, meter_enabled)
