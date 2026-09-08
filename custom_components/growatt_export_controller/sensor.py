"""Sensor entities for Growatt Export Controller."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GrowattConfigEntry
from .coordinator import GrowattExportControllerCoordinator
from .models import PriceControlMode
from .price_control import decision_thresholds

_DESCRIPTIONS = (
    SensorEntityDescription(
        key="controller_status",
        translation_key="controller_status",
        icon="mdi:cloud-check",
    ),
    SensorEntityDescription(
        key="price_control_status",
        translation_key="price_control_status",
        icon="mdi:cash-sync",
    ),
    SensorEntityDescription(
        key="current_price",
        translation_key="current_price",
        icon="mdi:currency-eur",
        native_unit_of_measurement="€/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
    ),
    SensorEntityDescription(
        key="solar_power",
        translation_key="solar_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="solar_energy_today",
        translation_key="solar_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="solar_energy_total",
        translation_key="solar_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up status and price-control sensors."""

    del hass
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            GrowattControllerStatusSensor(coordinator, entry),
            GrowattPriceControlStatusSensor(coordinator, entry),
            GrowattCurrentPriceSensor(coordinator, entry),
            GrowattSolarPowerSensor(coordinator, entry),
            GrowattSolarEnergyTodaySensor(coordinator, entry),
            GrowattSolarEnergyTotalSensor(coordinator, entry),
        ]
    )


class _GrowattSensorBase(
    CoordinatorEntity[GrowattExportControllerCoordinator], SensorEntity
):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(entry.domain, entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Growatt",
            "model": "Cloud Export Controller",
            "serial_number": coordinator.config.serial_num,
        }


class GrowattControllerStatusSensor(_GrowattSensorBase):
    """Expose cloud/session and latest command status."""

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, _DESCRIPTIONS[0])

    @property
    def native_value(self) -> str:
        state = self.coordinator.data
        if state.last_error or state.telemetry_last_error:
            return "error"
        return "connected" if state.authenticated else "idle"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        state = self.coordinator.data
        response = state.last_response
        if response and len(response) > 500:
            response = response[:500] + "..."
        return {
            "last_command": state.last_command,
            "last_command_at": state.last_command_at,
            "last_error": state.last_error,
            "last_http_status": state.last_http_status,
            "last_login_status": state.last_login_status,
            "last_endpoint": state.last_endpoint,
            "last_response": response,
            "authenticated": state.authenticated,
            "telemetry_last_checked_at": state.telemetry_last_checked_at,
            "telemetry_last_error": state.telemetry_last_error,
        }


class GrowattPriceControlStatusSensor(_GrowattSensorBase):
    """Expose price automation mode and its last decision."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = [mode.value for mode in PriceControlMode]

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, _DESCRIPTIONS[1])

    @property
    def native_value(self) -> str:
        return self.coordinator.data.price_mode.value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        state = self.coordinator.data
        settings = self.coordinator.settings
        activation_threshold, recovery_threshold = decision_thresholds(settings)
        return {
            "enabled": settings.price_automation_enabled,
            "strategy": settings.price_strategy.value,
            "price_sensor": state.price_sensor,
            "source_price_eur_per_kwh": state.source_price,
            "tax_excluded_price_eur_per_kwh": state.tax_excluded_price,
            "effective_price_eur_per_kwh": state.effective_price,
            "price_basis": state.price_basis,
            "source_unit": state.source_unit,
            "activation_threshold_eur_per_kwh": activation_threshold,
            "recovery_threshold_eur_per_kwh": recovery_threshold,
            "economic_2026_within_saldering": settings.economic_2026_within_saldering,
            "economic_recovery_margin_eur_per_kwh": settings.economic_recovery_margin,
            "reason": state.price_reason,
            "last_checked_at": state.price_last_checked_at,
            "last_applied_at": state.price_last_applied_at,
            "last_error": state.price_last_error,
            "trigger_meter_enabled": settings.trigger_meter_enabled,
            "trigger_export_percentage": settings.trigger_export_percentage,
            "normal_meter_enabled": settings.normal_meter_enabled,
            "normal_export_percentage": settings.normal_export_percentage,
            "sensor_includes_tax": settings.sensor_includes_tax,
            "threshold_includes_tax": settings.threshold_includes_tax,
        }


class GrowattCurrentPriceSensor(_GrowattSensorBase):
    """Expose the effective price used for the decision."""

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, _DESCRIPTIONS[2])

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data.price_mode is PriceControlMode.DISABLED:
            return None
        return self.coordinator.data.effective_price

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        state = self.coordinator.data
        return {
            "source_entity_id": state.price_sensor,
            "source_price_eur_per_kwh": state.source_price,
            "tax_excluded_price_eur_per_kwh": state.tax_excluded_price,
            "price_basis": state.price_basis,
            "strategy": self.coordinator.settings.price_strategy.value,
            "source_unit": state.source_unit,
        }


class _GrowattSolarSensorBase(_GrowattSensorBase):
    """Common metadata for read-only PV sensors."""

    @property
    def available(self) -> bool:
        """Mark only the PV sensors unavailable after telemetry failure."""
        return (
            super().available
            and self.coordinator.data.telemetry_last_error is None
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        state = self.coordinator.data
        return {
            "inverter_status": state.solar_device_status,
            "inverter_last_update": state.solar_last_updated,
            "last_checked_at": state.telemetry_last_checked_at,
            "last_error": state.telemetry_last_error,
        }


class GrowattSolarPowerSensor(_GrowattSolarSensorBase):
    """Expose current PV power from the configured inverter."""

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, _DESCRIPTIONS[3])

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.solar_power_w


class GrowattSolarEnergyTodaySensor(_GrowattSolarSensorBase):
    """Expose inverter PV production for the current day."""

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, _DESCRIPTIONS[4])

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.solar_energy_today_kwh


class GrowattSolarEnergyTotalSensor(_GrowattSolarSensorBase):
    """Expose cumulative inverter PV production for the Energy dashboard."""

    def __init__(
        self,
        coordinator: GrowattExportControllerCoordinator,
        entry: GrowattConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, _DESCRIPTIONS[5])

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.solar_energy_total_kwh
