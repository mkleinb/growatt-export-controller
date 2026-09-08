"""Switch entities for Growatt Export Controller."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GrowattConfigEntry
from .const import CONF_PRICE_AUTOMATION_ENABLED
from .coordinator import GrowattExportControllerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Growatt switches."""

    del hass
    async_add_entities(
        [
            GrowattMeterEnableSwitch(entry.runtime_data.coordinator, entry),
            GrowattPriceAutomationSwitch(entry.runtime_data.coordinator, entry),
        ]
    )


class GrowattMeterEnableSwitch(
    CoordinatorEntity[GrowattExportControllerCoordinator], SwitchEntity
):
    """Enable or disable meter-based export control."""

    _attr_has_entity_name = True
    _attr_translation_key = "meter_enable"
    _attr_icon = "mdi:transmission-tower"

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_meter_enable"
        self._attr_device_info = {
            "identifiers": {(entry.domain, entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Cloud Export Controller",
            "serial_number": coordinator.config.serial_num,
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.meter_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        del kwargs
        _LOGGER.info("Manual meter enable requested")
        await self.coordinator.async_set_export_limit(
            self.coordinator.data.export_percentage,
            True,
            source="manual_meter_enable",
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        del kwargs
        _LOGGER.info("Manual meter disable requested")
        await self.coordinator.async_set_export_limit(
            self.coordinator.data.export_percentage,
            False,
            source="manual_meter_disable",
        )


class GrowattPriceAutomationSwitch(
    CoordinatorEntity[GrowattExportControllerCoordinator], SwitchEntity
):
    """Enable or disable automatic price control from the dashboard."""

    _attr_has_entity_name = True
    _attr_translation_key = "price_automation"
    _attr_icon = "mdi:cash-sync"

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_price_automation"
        self._attr_device_info = {
            "identifiers": {(entry.domain, entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Cloud Export Controller",
            "serial_number": coordinator.config.serial_num,
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.settings.price_automation_enabled

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Persist the option and reload the entry so listeners are rebuilt cleanly."""

        options = dict(self._entry.options)
        if self.coordinator.settings.price_automation_enabled == enabled:
            return

        options[CONF_PRICE_AUTOMATION_ENABLED] = enabled
        _LOGGER.info(
            "Dashboard price automation requested: enabled=%s",
            enabled,
        )
        self.hass.config_entries.async_update_entry(self._entry, options=options)
        await self.hass.config_entries.async_reload(self._entry.entry_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        del kwargs
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        del kwargs
        await self._async_set_enabled(False)
