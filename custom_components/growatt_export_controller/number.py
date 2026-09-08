"""Number entities for Growatt Export Controller."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GrowattConfigEntry
from .coordinator import GrowattExportControllerCoordinator

_LOGGER = logging.getLogger(__name__)

_DESCRIPTION = NumberEntityDescription(
    key="export_percentage",
    translation_key="export_percentage",
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement="%",
    mode=NumberMode.SLIDER,
    icon="mdi:percent",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the export percentage entity."""

    del hass
    async_add_entities(
        [GrowattExportPercentageNumber(entry.runtime_data.coordinator, entry)]
    )


class GrowattExportPercentageNumber(
    CoordinatorEntity[GrowattExportControllerCoordinator], NumberEntity
):
    """Control the last commanded Growatt export percentage."""

    _attr_has_entity_name = True
    entity_description = _DESCRIPTION

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_export_percentage"
        self._attr_device_info = {
            "identifiers": {(entry.domain, entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Cloud Export Controller",
            "serial_number": coordinator.config.serial_num,
        }

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data.export_percentage)

    async def async_set_native_value(self, value: float) -> None:
        percentage = int(round(value))
        meter_enabled = self.coordinator.data.meter_enabled
        _LOGGER.info(
            "Manual export percentage requested: percentage=%s meter_enabled=%s",
            percentage,
            meter_enabled,
        )
        await self.coordinator.async_set_export_limit(
            percentage,
            meter_enabled,
            source="manual_percentage",
        )
