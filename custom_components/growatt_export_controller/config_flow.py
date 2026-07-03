"""Config flow for Growatt Export Controller."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GrowattApiClient, GrowattAuthError, GrowattClientConfig
from .const import (
    CONF_COMMAND_BASE_URL,
    CONF_DEFAULT_EXPORT_PERCENTAGE,
    CONF_DEFAULT_METER_ENABLED,
    CONF_DEVICE_PASSWORD_PREFIX,
    CONF_SERIAL_NUMBER,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_ATTEMPTS,
    CONF_RETRY_BACKOFF_SECONDS,
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_COMMAND_BASE_URL,
    DEFAULT_DEVICE_PASSWORD_PREFIX,
    DEFAULT_EXPORT_PERCENTAGE,
    DEFAULT_NAME,
    DEFAULT_RETRIES,
    DEFAULT_SERVICE_METER_ENABLED,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("name", default=DEFAULT_NAME): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERIAL_NUMBER): str,
        vol.Optional(CONF_DEVICE_PASSWORD_PREFIX, default=DEFAULT_DEVICE_PASSWORD_PREFIX): str,
        vol.Optional(CONF_COMMAND_BASE_URL, default=DEFAULT_COMMAND_BASE_URL): str,
        vol.Optional(CONF_DEFAULT_EXPORT_PERCENTAGE, default=DEFAULT_EXPORT_PERCENTAGE): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(CONF_DEFAULT_METER_ENABLED, default=DEFAULT_SERVICE_METER_ENABLED): bool,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_REQUEST_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
        vol.Optional(CONF_RETRY_ATTEMPTS, default=DEFAULT_RETRIES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional(CONF_RETRY_BACKOFF_SECONDS, default=DEFAULT_BACKOFF_SECONDS): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
        vol.Optional(CONF_SERIAL_NUMBER): str,
        vol.Optional(CONF_DEVICE_PASSWORD_PREFIX, default=DEFAULT_DEVICE_PASSWORD_PREFIX): str,
        vol.Optional(CONF_COMMAND_BASE_URL, default=DEFAULT_COMMAND_BASE_URL): str,
    }
)


class GrowattExportControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Growatt Export Controller."""

    VERSION = 1

    async def async_set_unique_id(self, unique_id: str) -> None:
        await super().async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            command_base_url = user_input[CONF_COMMAND_BASE_URL].rstrip("/")
            client_config = GrowattClientConfig(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                serial_num=user_input[CONF_SERIAL_NUMBER],
                device_password_prefix=user_input[CONF_DEVICE_PASSWORD_PREFIX],
                command_base_url=command_base_url,
                login_base_url="https://oss.growatt.com",
                timeout=DEFAULT_TIMEOUT,
                retry_attempts=DEFAULT_RETRIES,
                retry_backoff_seconds=DEFAULT_BACKOFF_SECONDS,
            )
            session = async_get_clientsession(self.hass)
            client = GrowattApiClient(session, client_config)
            try:
                await client.async_login(force=True)
            except GrowattAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while verifying Growatt login")
                errors["base"] = "cannot_connect"
            else:
                title = user_input.get("name") or DEFAULT_NAME
                await self.async_set_unique_id(f"{user_input[CONF_USERNAME]}@{command_base_url}")
                self._abort_if_unique_id_configured()
                data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_SERIAL_NUMBER: user_input[CONF_SERIAL_NUMBER],
                    CONF_DEVICE_PASSWORD_PREFIX: user_input[CONF_DEVICE_PASSWORD_PREFIX],
                    CONF_COMMAND_BASE_URL: command_base_url,
                    CONF_DEFAULT_EXPORT_PERCENTAGE: user_input[CONF_DEFAULT_EXPORT_PERCENTAGE],
                    CONF_DEFAULT_METER_ENABLED: user_input[CONF_DEFAULT_METER_ENABLED],
                }
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return GrowattExportControllerOptionsFlow(config_entry)


class GrowattExportControllerOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Growatt Export Controller."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(CONF_REQUEST_TIMEOUT, default=defaults.get(CONF_REQUEST_TIMEOUT, DEFAULT_TIMEOUT)): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                vol.Optional(CONF_RETRY_ATTEMPTS, default=defaults.get(CONF_RETRY_ATTEMPTS, DEFAULT_RETRIES)): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                vol.Optional(CONF_RETRY_BACKOFF_SECONDS, default=defaults.get(CONF_RETRY_BACKOFF_SECONDS, DEFAULT_BACKOFF_SECONDS)): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
                vol.Optional(CONF_SERIAL_NUMBER, default=defaults.get(CONF_SERIAL_NUMBER, "")): str,
                vol.Optional(CONF_DEVICE_PASSWORD_PREFIX, default=defaults.get(CONF_DEVICE_PASSWORD_PREFIX, DEFAULT_DEVICE_PASSWORD_PREFIX)): str,
                vol.Optional(CONF_COMMAND_BASE_URL, default=defaults.get(CONF_COMMAND_BASE_URL, DEFAULT_COMMAND_BASE_URL)): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


async def async_get_options_flow(config_entry):
    return GrowattExportControllerOptionsFlowHandler(config_entry)
