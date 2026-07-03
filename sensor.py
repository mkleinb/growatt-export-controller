"""Sensor platform for Growatt Export Controller."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_LAST_COMMAND,
    ATTR_LAST_ENDPOINT,
    ATTR_LAST_ERROR,
    ATTR_LAST_HTTP_STATUS,
    ATTR_LAST_LOGIN_RESPONSE,
    ATTR_LAST_LOGIN_STATUS,
    ATTR_RESPONSE,
    DOMAIN,
)
from .coordinator import GrowattExportControllerCoordinator

SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="controller_status",
        name="Controller Status",
        icon="mdi:cloud-check",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: GrowattExportControllerCoordinator = runtime["coordinator"]
    async_add_entities([GrowattControllerStatusSensor(coordinator, entry)])


class GrowattControllerStatusSensor(CoordinatorEntity[GrowattExportControllerCoordinator], SensorEntity):
    """Expose controller health and last result."""

    _attr_has_entity_name = True
    entity_description = SENSOR_DESCRIPTIONS[0]

    def __init__(self, coordinator: GrowattExportControllerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_controller_status"
        self._attr_name = self.entity_description.name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Export Controller",
        }

    @property
    def native_value(self) -> str:
        state = self.coordinator.data
        if state.last_error:
            return "error"
        if state.authenticated:
            return "connected"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        state = self.coordinator.data
        response = state.last_response
        login_response = state.last_login_response
        if response and len(response) > 500:
            response = response[:500] + "..."
        if login_response and len(login_response) > 500:
            login_response = login_response[:500] + "..."
        return {
            ATTR_LAST_COMMAND: state.last_command,
            ATTR_LAST_ERROR: state.last_error,
            ATTR_LAST_HTTP_STATUS: state.last_http_status,
            ATTR_LAST_LOGIN_STATUS: state.last_login_status,
            ATTR_LAST_ENDPOINT: state.last_endpoint,
            ATTR_LAST_LOGIN_RESPONSE: login_response,
            ATTR_RESPONSE: response,
        }
