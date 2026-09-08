"""The Growatt Export Controller integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType

from .api import GrowattApiClient, GrowattClientConfig
from .const import (
    ATTR_FORCE_APPLY,
    ATTR_METER_ENABLED,
    ATTR_PERCENTAGE,
    CONF_COMMAND_BASE_URL,
    CONF_DEFAULT_EXPORT_PERCENTAGE,
    CONF_DEFAULT_METER_ENABLED,
    CONF_ECONOMIC_2026_WITHIN_SALDERING,
    CONF_ECONOMIC_RECOVERY_MARGIN,
    CONF_DEVICE_PASSWORD_PREFIX,
    CONF_PRICE_ACTIVATION_THRESHOLD,
    CONF_PRICE_AUTOMATION_ENABLED,
    CONF_PRICE_FIXED_TAX_EUR_PER_KWH,
    CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
    CONF_PRICE_NORMAL_METER_ENABLED,
    CONF_PRICE_POLL_INTERVAL_MINUTES,
    CONF_PRICE_REAPPLY_INTERVAL_MINUTES,
    CONF_PRICE_RECOVERY_THRESHOLD,
    CONF_PRICE_SENSOR,
    CONF_PRICE_STRATEGY,
    CONF_PRICE_SENSOR_INCLUDES_TAX,
    CONF_PRICE_THRESHOLD_INCLUDES_TAX,
    CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
    CONF_PRICE_TRIGGER_METER_ENABLED,
    CONF_PRICE_VAT_PERCENT,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_ATTEMPTS,
    CONF_RETRY_BACKOFF_SECONDS,
    CONF_SERIAL_NUMBER,
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_COMMAND_BASE_URL,
    DEFAULT_ECONOMIC_2026_WITHIN_SALDERING,
    DEFAULT_ECONOMIC_RECOVERY_MARGIN,
    DEFAULT_EXPORT_PERCENTAGE,
    DEFAULT_METER_ENABLED,
    DEFAULT_NAME,
    DEFAULT_NORMAL_EXPORT_PERCENTAGE,
    DEFAULT_NORMAL_METER_ENABLED,
    DEFAULT_PRICE_ACTIVATION_THRESHOLD,
    DEFAULT_PRICE_AUTOMATION_ENABLED,
    DEFAULT_PRICE_FIXED_TAX_EUR_PER_KWH,
    DEFAULT_PRICE_POLL_INTERVAL_MINUTES,
    DEFAULT_PRICE_REAPPLY_INTERVAL_MINUTES,
    DEFAULT_PRICE_RECOVERY_THRESHOLD,
    DEFAULT_PRICE_SENSOR_INCLUDES_TAX,
    DEFAULT_PRICE_STRATEGY,
    DEFAULT_PRICE_THRESHOLD_INCLUDES_TAX,
    DEFAULT_PRICE_VAT_PERCENT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_TRIGGER_EXPORT_PERCENTAGE,
    DEFAULT_TRIGGER_METER_ENABLED,
    DOMAIN,
    LEGACY_CONF_AUTO_PRICE_CONTROL_ENABLED,
    LEGACY_CONF_COMMAND_SERVER_URL,
    LEGACY_CONF_INVERTER_SERIAL,
    LEGACY_CONF_PRICE_COMPARISON_INCLUDES_TAX,
    LEGACY_CONF_PRICE_DEACTIVATION_THRESHOLD,
    LEGACY_CONF_PRICE_SENSOR_ENTITY_ID,
    LEGACY_CONF_PRICE_TAX_RATE_PERCENT,
    LEGACY_CONF_PRICE_THRESHOLD,
    PLATFORMS,
    SERVICE_EVALUATE_PRICE_CONTROL,
    SERVICE_SET_EXPORT_LIMIT,
)
from .coordinator import GrowattExportControllerCoordinator
from .models import GrowattControlSettings, PriceStrategy

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class GrowattRuntimeData:
    """Runtime objects associated with one config entry."""

    client: GrowattApiClient
    coordinator: GrowattExportControllerCoordinator
    client_config: GrowattClientConfig
    settings: GrowattControlSettings


GrowattConfigEntry = ConfigEntry[GrowattRuntimeData]

_SET_EXPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERCENTAGE): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_METER_ENABLED, default=DEFAULT_METER_ENABLED): cv.boolean,
    }
)
_EVALUATE_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_FORCE_APPLY, default=False): cv.boolean}
)


def _loaded_runtimes(hass: HomeAssistant) -> list[GrowattRuntimeData]:
    runtimes: list[GrowattRuntimeData] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        runtime = entry.runtime_data
        if isinstance(runtime, GrowattRuntimeData):
            runtimes.append(runtime)
    return runtimes


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services."""

    del config

    async def handle_set_export_limit(call: ServiceCall) -> None:
        runtimes = _loaded_runtimes(hass)
        if not runtimes:
            raise ServiceValidationError(
                "No loaded Growatt Export Controller entry is available"
            )
        for runtime in runtimes:
            await runtime.coordinator.async_set_export_limit(
                call.data[ATTR_PERCENTAGE],
                call.data[ATTR_METER_ENABLED],
                source="service_set_export_limit",
            )

    async def handle_evaluate_price_control(call: ServiceCall) -> None:
        runtimes = _loaded_runtimes(hass)
        if not runtimes:
            raise ServiceValidationError(
                "No loaded Growatt Export Controller entry is available"
            )
        for runtime in runtimes:
            await runtime.coordinator.async_refresh_price_control(
                reason="service_evaluation",
                force_apply=call.data[ATTR_FORCE_APPLY],
            )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SET_EXPORT_LIMIT,
        handle_set_export_limit,
        schema=_SET_EXPORT_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EVALUATE_PRICE_CONTROL,
        handle_evaluate_price_control,
        schema=_EVALUATE_SCHEMA,
    )
    return True


def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _build_settings(merged: dict[str, Any]) -> GrowattControlSettings:
    return GrowattControlSettings(
        default_export_percentage=int(
            merged.get(CONF_DEFAULT_EXPORT_PERCENTAGE, DEFAULT_EXPORT_PERCENTAGE)
        ),
        default_meter_enabled=bool(
            merged.get(CONF_DEFAULT_METER_ENABLED, DEFAULT_METER_ENABLED)
        ),
        price_automation_enabled=bool(
            _first(
                merged,
                CONF_PRICE_AUTOMATION_ENABLED,
                LEGACY_CONF_AUTO_PRICE_CONTROL_ENABLED,
                default=DEFAULT_PRICE_AUTOMATION_ENABLED,
            )
        ),
        price_strategy=PriceStrategy(
            str(merged.get(CONF_PRICE_STRATEGY, DEFAULT_PRICE_STRATEGY))
        ),
        economic_2026_within_saldering=bool(
            merged.get(
                CONF_ECONOMIC_2026_WITHIN_SALDERING,
                DEFAULT_ECONOMIC_2026_WITHIN_SALDERING,
            )
        ),
        economic_recovery_margin=float(
            merged.get(
                CONF_ECONOMIC_RECOVERY_MARGIN,
                DEFAULT_ECONOMIC_RECOVERY_MARGIN,
            )
        ),
        price_sensor=(
            str(
                _first(
                    merged,
                    CONF_PRICE_SENSOR,
                    LEGACY_CONF_PRICE_SENSOR_ENTITY_ID,
                    default="",
                )
            ).strip()
            or None
        ),
        activation_threshold=float(
            _first(
                merged,
                CONF_PRICE_ACTIVATION_THRESHOLD,
                LEGACY_CONF_PRICE_THRESHOLD,
                default=DEFAULT_PRICE_ACTIVATION_THRESHOLD,
            )
        ),
        recovery_threshold=float(
            _first(
                merged,
                CONF_PRICE_RECOVERY_THRESHOLD,
                LEGACY_CONF_PRICE_DEACTIVATION_THRESHOLD,
                default=DEFAULT_PRICE_RECOVERY_THRESHOLD,
            )
        ),
        trigger_meter_enabled=bool(
            merged.get(CONF_PRICE_TRIGGER_METER_ENABLED, DEFAULT_TRIGGER_METER_ENABLED)
        ),
        trigger_export_percentage=int(
            merged.get(
                CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
                DEFAULT_TRIGGER_EXPORT_PERCENTAGE,
            )
        ),
        normal_meter_enabled=bool(
            merged.get(CONF_PRICE_NORMAL_METER_ENABLED, DEFAULT_NORMAL_METER_ENABLED)
        ),
        normal_export_percentage=int(
            merged.get(
                CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
                DEFAULT_NORMAL_EXPORT_PERCENTAGE,
            )
        ),
        sensor_includes_tax=bool(
            merged.get(
                CONF_PRICE_SENSOR_INCLUDES_TAX,
                DEFAULT_PRICE_SENSOR_INCLUDES_TAX,
            )
        ),
        threshold_includes_tax=bool(
            _first(
                merged,
                CONF_PRICE_THRESHOLD_INCLUDES_TAX,
                LEGACY_CONF_PRICE_COMPARISON_INCLUDES_TAX,
                default=DEFAULT_PRICE_THRESHOLD_INCLUDES_TAX,
            )
        ),
        vat_percent=float(
            _first(
                merged,
                CONF_PRICE_VAT_PERCENT,
                LEGACY_CONF_PRICE_TAX_RATE_PERCENT,
                default=DEFAULT_PRICE_VAT_PERCENT,
            )
        ),
        fixed_tax_eur_per_kwh=float(
            merged.get(
                CONF_PRICE_FIXED_TAX_EUR_PER_KWH,
                DEFAULT_PRICE_FIXED_TAX_EUR_PER_KWH,
            )
        ),
        poll_interval_minutes=int(
            merged.get(
                CONF_PRICE_POLL_INTERVAL_MINUTES,
                DEFAULT_PRICE_POLL_INTERVAL_MINUTES,
            )
        ),
        reapply_interval_minutes=int(
            merged.get(
                CONF_PRICE_REAPPLY_INTERVAL_MINUTES,
                DEFAULT_PRICE_REAPPLY_INTERVAL_MINUTES,
            )
        ),
    )


async def async_setup_entry(hass: HomeAssistant, entry: GrowattConfigEntry) -> bool:
    """Set up Growatt Export Controller from a config entry."""

    merged = {**entry.data, **entry.options}

    # RC1-RC3 used 100% as the low-price export target. Live P1 testing
    # confirmed Growatt interprets 0% (with Meter Enable ON) as zero export.
    # Migrate existing automatic-economic entries so the UI and stored
    # options also reflect the proven zero-export policy.
    if str(merged.get(CONF_PRICE_STRATEGY, DEFAULT_PRICE_STRATEGY)) == PriceStrategy.ECONOMIC_AUTO.value:
        economic_targets = {
            CONF_PRICE_TRIGGER_METER_ENABLED: True,
            CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE: 0,
            CONF_PRICE_NORMAL_METER_ENABLED: False,
            CONF_PRICE_NORMAL_EXPORT_PERCENTAGE: 100,
        }
        if any(merged.get(key) != value for key, value in economic_targets.items()):
            options = dict(entry.options)
            options.update(economic_targets)
            hass.config_entries.async_update_entry(entry, options=options)
            merged = {**entry.data, **options}
            _LOGGER.info(
                "Migrated automatic economic targets to zero-export: "
                "trigger meter=on export=0%%; normal meter=off export=100%%"
            )
    serial_number = str(
        _first(
            merged,
            CONF_SERIAL_NUMBER,
            LEGACY_CONF_INVERTER_SERIAL,
            default="",
        )
    ).strip()
    command_base_url = str(
        _first(
            merged,
            CONF_COMMAND_BASE_URL,
            LEGACY_CONF_COMMAND_SERVER_URL,
            default=DEFAULT_COMMAND_BASE_URL,
        )
    ).rstrip("/")

    client_config = GrowattClientConfig(
        username=str(merged[CONF_USERNAME]),
        password=str(merged[CONF_PASSWORD]),
        serial_num=serial_number,
        device_password_prefix=str(merged.get(CONF_DEVICE_PASSWORD_PREFIX, "growatt")),
        command_base_url=command_base_url,
        login_base_url=command_base_url,
        timeout=int(merged.get(CONF_REQUEST_TIMEOUT, DEFAULT_TIMEOUT)),
        retry_attempts=int(merged.get(CONF_RETRY_ATTEMPTS, DEFAULT_RETRIES)),
        retry_backoff_seconds=int(
            merged.get(CONF_RETRY_BACKOFF_SECONDS, DEFAULT_BACKOFF_SECONDS)
        ),
    )
    settings = _build_settings(merged)
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    client = GrowattApiClient(session, client_config)
    coordinator = GrowattExportControllerCoordinator(
        hass,
        client,
        client_config,
        settings,
        entry.title or DEFAULT_NAME,
        entry,
    )
    entry.runtime_data = GrowattRuntimeData(
        client=client,
        coordinator=coordinator,
        client_config=client_config,
        settings=settings,
    )

    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start_price_watch()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GrowattConfigEntry) -> bool:
    """Unload a config entry."""

    entry.runtime_data.coordinator.async_stop_price_watch()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate settings written by early development versions."""

    data = dict(entry.data)
    options = dict(entry.options)

    if CONF_SERIAL_NUMBER not in data and LEGACY_CONF_INVERTER_SERIAL in data:
        data[CONF_SERIAL_NUMBER] = data.pop(LEGACY_CONF_INVERTER_SERIAL)
    if CONF_COMMAND_BASE_URL not in data and LEGACY_CONF_COMMAND_SERVER_URL in data:
        data[CONF_COMMAND_BASE_URL] = data.pop(LEGACY_CONF_COMMAND_SERVER_URL)

    option_aliases = {
        LEGACY_CONF_AUTO_PRICE_CONTROL_ENABLED: CONF_PRICE_AUTOMATION_ENABLED,
        LEGACY_CONF_PRICE_SENSOR_ENTITY_ID: CONF_PRICE_SENSOR,
        LEGACY_CONF_PRICE_THRESHOLD: CONF_PRICE_ACTIVATION_THRESHOLD,
        LEGACY_CONF_PRICE_DEACTIVATION_THRESHOLD: CONF_PRICE_RECOVERY_THRESHOLD,
        LEGACY_CONF_PRICE_COMPARISON_INCLUDES_TAX: CONF_PRICE_THRESHOLD_INCLUDES_TAX,
        LEGACY_CONF_PRICE_TAX_RATE_PERCENT: CONF_PRICE_VAT_PERCENT,
    }
    for old_key, new_key in option_aliases.items():
        if new_key not in options and old_key in options:
            options[new_key] = options.pop(old_key)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=2,
        minor_version=0,
    )
    return True
