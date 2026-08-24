"""Config and options flows for Growatt Export Controller."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import GrowattApiClient, GrowattAuthError, GrowattClientConfig
from .const import (
    CONF_COMMAND_BASE_URL,
    CONF_DEFAULT_EXPORT_PERCENTAGE,
    CONF_DEFAULT_METER_ENABLED,
    CONF_PRICE_ACTIVATION_THRESHOLD,
    CONF_PRICE_AUTOMATION_ENABLED,
    CONF_PRICE_FIXED_TAX_EUR_PER_KWH,
    CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
    CONF_PRICE_NORMAL_METER_ENABLED,
    CONF_PRICE_POLL_INTERVAL_MINUTES,
    CONF_PRICE_REAPPLY_INTERVAL_MINUTES,
    CONF_PRICE_RECOVERY_THRESHOLD,
    CONF_PRICE_SENSOR,
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
    DEFAULT_PRICE_THRESHOLD_INCLUDES_TAX,
    DEFAULT_PRICE_VAT_PERCENT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_TRIGGER_EXPORT_PERCENTAGE,
    DEFAULT_TRIGGER_METER_ENABLED,
    DOMAIN,
)
from .helpers.price_sensors import discover_price_sensor_candidates
from .price_control import parse_numeric_price

_LOGGER = logging.getLogger(__name__)


def _user_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
            vol.Required(CONF_USERNAME): selector.TextSelector(),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SERIAL_NUMBER): selector.TextSelector(),
            vol.Optional(
                CONF_COMMAND_BASE_URL,
                default=DEFAULT_COMMAND_BASE_URL,
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            ),
            vol.Optional(
                CONF_DEFAULT_EXPORT_PERCENTAGE,
                default=DEFAULT_EXPORT_PERCENTAGE,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="%",
                )
            ),
            vol.Optional(
                CONF_DEFAULT_METER_ENABLED,
                default=DEFAULT_METER_ENABLED,
            ): selector.BooleanSelector(),
        }
    )


async def _validate_login(hass, data: dict[str, Any]) -> None:
    session = async_create_clientsession(
        hass,
        auto_cleanup=False,
        cookie_jar=aiohttp.CookieJar(),
    )
    client = GrowattApiClient(
        session,
        GrowattClientConfig(
            username=str(data[CONF_USERNAME]).strip(),
            password=str(data[CONF_PASSWORD]),
            serial_num=str(data[CONF_SERIAL_NUMBER]).strip(),
            command_base_url=str(data.get(CONF_COMMAND_BASE_URL, DEFAULT_COMMAND_BASE_URL)).rstrip("/"),
            login_base_url="https://oss.growatt.com",
            timeout=DEFAULT_TIMEOUT,
            retry_attempts=DEFAULT_RETRIES,
            retry_backoff_seconds=DEFAULT_BACKOFF_SECONDS,
        ),
    )
    try:
        await client.async_login(force=True)
    finally:
        session.detach()


class GrowattExportControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Growatt Export Controller configuration."""

    VERSION = 2
    MINOR_VERSION = 0

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_USERNAME] = str(user_input[CONF_USERNAME]).strip()
            user_input[CONF_SERIAL_NUMBER] = str(user_input[CONF_SERIAL_NUMBER]).strip().upper()
            user_input[CONF_COMMAND_BASE_URL] = str(
                user_input.get(CONF_COMMAND_BASE_URL, DEFAULT_COMMAND_BASE_URL)
            ).rstrip("/")

            if not user_input[CONF_SERIAL_NUMBER]:
                errors[CONF_SERIAL_NUMBER] = "serial_required"
            else:
                try:
                    await _validate_login(self.hass, user_input)
                except GrowattAuthError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Could not validate Growatt login")
                    errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME].casefold()}:{user_input[CONF_SERIAL_NUMBER]}"
                )
                self._abort_if_unique_id_configured()
                title = str(user_input.pop(CONF_NAME, DEFAULT_NAME) or DEFAULT_NAME)
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""

        del config_entry
        return GrowattExportControllerOptionsFlow()


class GrowattExportControllerOptionsFlow(OptionsFlowWithReload):
    """Configure price automation and request behavior."""

    def _price_selector(self, current: str | None):
        candidates = discover_price_sensor_candidates(self.hass)
        options = [
            selector.SelectOptionDict(value=item.entity_id, label=item.label)
            for item in candidates
        ]

        if current and all(item["value"] != current for item in options):
            state = self.hass.states.get(current)
            label = state.name if state is not None else current
            options.insert(
                0,
                selector.SelectOptionDict(
                    value=current,
                    label=f"{label} — current selection",
                ),
            )

        if options:
            return selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ), candidates

        # Fallback remains a UI entity picker; no entity ID has to be typed.
        return selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ), candidates

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = self.config_entry.options
        data = {**self.config_entry.data, **options}
        current_sensor = data.get(CONF_PRICE_SENSOR)
        price_selector, candidates = self._price_selector(current_sensor)
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = bool(user_input.get(CONF_PRICE_AUTOMATION_ENABLED, False))
            sensor_entity = user_input.get(CONF_PRICE_SENSOR)
            activation = float(user_input[CONF_PRICE_ACTIVATION_THRESHOLD])
            recovery = float(user_input[CONF_PRICE_RECOVERY_THRESHOLD])

            if enabled and not sensor_entity:
                errors[CONF_PRICE_SENSOR] = "price_sensor_required"
            elif enabled:
                state = self.hass.states.get(str(sensor_entity))
                if state is None:
                    errors[CONF_PRICE_SENSOR] = "price_sensor_not_found"
                elif parse_numeric_price(state.state) is None:
                    errors[CONF_PRICE_SENSOR] = "price_sensor_not_numeric"

            if recovery < activation:
                errors[CONF_PRICE_RECOVERY_THRESHOLD] = "recovery_below_activation"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        default_sensor = current_sensor
        if not default_sensor and candidates:
            default_sensor = candidates[0].entity_id

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PRICE_AUTOMATION_ENABLED,
                    default=data.get(
                        CONF_PRICE_AUTOMATION_ENABLED,
                        DEFAULT_PRICE_AUTOMATION_ENABLED,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_PRICE_SENSOR,
                    default=default_sensor,
                ): price_selector,
                vol.Optional(
                    CONF_PRICE_ACTIVATION_THRESHOLD,
                    default=data.get(
                        CONF_PRICE_ACTIVATION_THRESHOLD,
                        DEFAULT_PRICE_ACTIVATION_THRESHOLD,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-2.0,
                        max=2.0,
                        step=0.001,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="EUR/kWh",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_RECOVERY_THRESHOLD,
                    default=data.get(
                        CONF_PRICE_RECOVERY_THRESHOLD,
                        DEFAULT_PRICE_RECOVERY_THRESHOLD,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-2.0,
                        max=2.0,
                        step=0.001,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="EUR/kWh",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_TRIGGER_METER_ENABLED,
                    default=data.get(
                        CONF_PRICE_TRIGGER_METER_ENABLED,
                        DEFAULT_TRIGGER_METER_ENABLED,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
                    default=data.get(
                        CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
                        DEFAULT_TRIGGER_EXPORT_PERCENTAGE,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_NORMAL_METER_ENABLED,
                    default=data.get(
                        CONF_PRICE_NORMAL_METER_ENABLED,
                        DEFAULT_NORMAL_METER_ENABLED,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
                    default=data.get(
                        CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
                        DEFAULT_NORMAL_EXPORT_PERCENTAGE,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_SENSOR_INCLUDES_TAX,
                    default=data.get(
                        CONF_PRICE_SENSOR_INCLUDES_TAX,
                        DEFAULT_PRICE_SENSOR_INCLUDES_TAX,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_PRICE_THRESHOLD_INCLUDES_TAX,
                    default=data.get(
                        CONF_PRICE_THRESHOLD_INCLUDES_TAX,
                        DEFAULT_PRICE_THRESHOLD_INCLUDES_TAX,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_PRICE_VAT_PERCENT,
                    default=data.get(
                        CONF_PRICE_VAT_PERCENT,
                        DEFAULT_PRICE_VAT_PERCENT,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_FIXED_TAX_EUR_PER_KWH,
                    default=data.get(
                        CONF_PRICE_FIXED_TAX_EUR_PER_KWH,
                        DEFAULT_PRICE_FIXED_TAX_EUR_PER_KWH,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-2.0,
                        max=2.0,
                        step=0.001,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="EUR/kWh",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_POLL_INTERVAL_MINUTES,
                    default=data.get(
                        CONF_PRICE_POLL_INTERVAL_MINUTES,
                        DEFAULT_PRICE_POLL_INTERVAL_MINUTES,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Optional(
                    CONF_PRICE_REAPPLY_INTERVAL_MINUTES,
                    default=data.get(
                        CONF_PRICE_REAPPLY_INTERVAL_MINUTES,
                        DEFAULT_PRICE_REAPPLY_INTERVAL_MINUTES,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=1440,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Optional(
                    CONF_DEFAULT_EXPORT_PERCENTAGE,
                    default=data.get(
                        CONF_DEFAULT_EXPORT_PERCENTAGE,
                        DEFAULT_EXPORT_PERCENTAGE,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_DEFAULT_METER_ENABLED,
                    default=data.get(CONF_DEFAULT_METER_ENABLED, DEFAULT_METER_ENABLED),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_REQUEST_TIMEOUT,
                    default=data.get(CONF_REQUEST_TIMEOUT, DEFAULT_TIMEOUT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=120, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_RETRY_ATTEMPTS,
                    default=data.get(CONF_RETRY_ATTEMPTS, DEFAULT_RETRIES),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_RETRY_BACKOFF_SECONDS,
                    default=data.get(
                        CONF_RETRY_BACKOFF_SECONDS,
                        DEFAULT_BACKOFF_SECONDS,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=30, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
