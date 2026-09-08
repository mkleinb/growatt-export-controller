"""Diagnostics support for Growatt Export Controller."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GrowattConfigEntry

_TO_REDACT = {
    "username",
    "password",
    "serial_number",
    "inverter_serial",
    "last_login_response",
    "last_response",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""

    del hass
    runtime = entry.runtime_data
    state = runtime.coordinator.data
    settings = runtime.settings

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), _TO_REDACT),
            "options": async_redact_data(dict(entry.options), _TO_REDACT),
        },
        "client": {
            "authenticated": runtime.client.authenticated,
            "last_login_status": runtime.client.last_login_status,
            "last_login_url": runtime.client.last_login_url,
        },
        "controller": {
            "export_percentage": state.export_percentage,
            "meter_enabled": state.meter_enabled,
            "last_command": state.last_command,
            "last_command_at": state.last_command_at,
            "last_error": state.last_error,
            "last_http_status": state.last_http_status,
            "price_mode": state.price_mode.value,
            "price_sensor": state.price_sensor,
            "source_price": state.source_price,
            "effective_price": state.effective_price,
            "tax_excluded_price": state.tax_excluded_price,
            "price_basis": state.price_basis,
            "source_unit": state.source_unit,
            "price_reason": state.price_reason,
            "price_last_checked_at": state.price_last_checked_at,
            "price_last_applied_at": state.price_last_applied_at,
            "price_last_error": state.price_last_error,
            "solar_power_w": state.solar_power_w,
            "solar_energy_today_kwh": state.solar_energy_today_kwh,
            "solar_energy_total_kwh": state.solar_energy_total_kwh,
            "solar_device_status": state.solar_device_status,
            "solar_last_updated": state.solar_last_updated,
            "telemetry_last_checked_at": state.telemetry_last_checked_at,
            "telemetry_last_error": state.telemetry_last_error,
        },
        "settings": {
            "price_automation_enabled": settings.price_automation_enabled,
            "price_strategy": settings.price_strategy.value,
            "economic_2026_within_saldering": settings.economic_2026_within_saldering,
            "economic_recovery_margin": settings.economic_recovery_margin,
            "activation_threshold": settings.activation_threshold,
            "recovery_threshold": settings.recovery_threshold,
            "trigger_meter_enabled": settings.trigger_meter_enabled,
            "trigger_export_percentage": settings.trigger_export_percentage,
            "normal_meter_enabled": settings.normal_meter_enabled,
            "normal_export_percentage": settings.normal_export_percentage,
            "sensor_includes_tax": settings.sensor_includes_tax,
            "threshold_includes_tax": settings.threshold_includes_tax,
            "vat_percent": settings.vat_percent,
            "fixed_tax_eur_per_kwh": settings.fixed_tax_eur_per_kwh,
            "poll_interval_minutes": settings.poll_interval_minutes,
            "reapply_interval_minutes": settings.reapply_interval_minutes,
        },
    }
