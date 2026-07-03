"""The Growatt Export Controller integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_admin_service

from .api import GrowattApiClient, GrowattClientConfig
from .const import (
    ATTR_METER_ENABLED,
    ATTR_PERCENTAGE,
    CONF_COMMAND_BASE_URL,
    CONF_DEFAULT_EXPORT_PERCENTAGE,
    CONF_DEFAULT_METER_ENABLED,
    CONF_DEVICE_PASSWORD_PREFIX,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_ATTEMPTS,
    CONF_RETRY_BACKOFF_SECONDS,
    CONF_SERIAL_NUMBER,
    DEFAULT_COMMAND_BASE_URL,
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_NAME,
    DEFAULT_RETRIES,
    DEFAULT_SERVICE_METER_ENABLED,
    DEFAULT_TIMEOUT,
    DOMAIN,
    PLATFORMS,
    SERVICE_SET_EXPORT_LIMIT,
)
from .coordinator import GrowattExportControllerCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERCENTAGE): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_METER_ENABLED, default=DEFAULT_SERVICE_METER_ENABLED): vol.Coerce(bool),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration and register domain services."""

    async def handle_set_export_limit(call: ServiceCall) -> None:
        percentage = call.data[ATTR_PERCENTAGE]
        meter_enabled = call.data[ATTR_METER_ENABLED]
        _LOGGER.warning("Growatt service call received: percentage=%s meter_enabled=%s", percentage, meter_enabled)

        domain_data = hass.data.get(DOMAIN, {})
        coordinators = [
            runtime["coordinator"] for runtime in domain_data.values() if isinstance(runtime, dict) and "coordinator" in runtime
        ]

        if not coordinators:
            _LOGGER.warning("No Growatt Export Controller entries are loaded")
            return

        for coordinator in coordinators:
            _LOGGER.warning("Forwarding set_export_limit to coordinator %s", getattr(coordinator, "name", "unknown"))
            await coordinator.async_set_export_limit(percentage, meter_enabled)
        _LOGGER.warning("Growatt service call completed")

    async_register_admin_service(hass, DOMAIN, SERVICE_SET_EXPORT_LIMIT, handle_set_export_limit, schema=SERVICE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Growatt Export Controller from a config entry."""

    merged = {**entry.data, **entry.options}
    username = merged[CONF_USERNAME]
    password = merged[CONF_PASSWORD]
    command_base_url = merged.get(CONF_COMMAND_BASE_URL, DEFAULT_COMMAND_BASE_URL)
    serial_num = merged.get(CONF_SERIAL_NUMBER, "").strip()
    device_password_prefix = merged.get(CONF_DEVICE_PASSWORD_PREFIX, "growatt")
    timeout = merged.get(CONF_REQUEST_TIMEOUT, DEFAULT_TIMEOUT)
    retries = merged.get(CONF_RETRY_ATTEMPTS, DEFAULT_RETRIES)
    backoff = merged.get(CONF_RETRY_BACKOFF_SECONDS, DEFAULT_BACKOFF_SECONDS)

    client_config = GrowattClientConfig(
        username=username,
        password=password,
        serial_num=serial_num,
        device_password_prefix=device_password_prefix,
        command_base_url=command_base_url,
        login_base_url="https://oss.growatt.com",
        timeout=timeout,
        retry_attempts=retries,
        retry_backoff_seconds=backoff,
    )
    session = async_get_clientsession(hass)
    client = GrowattApiClient(session, client_config)
    coordinator = GrowattExportControllerCoordinator(hass, client, client_config, name=entry.title or DEFAULT_NAME)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "config": client_config,
    }

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok
