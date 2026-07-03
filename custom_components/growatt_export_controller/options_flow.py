"""Options flow for Growatt Export Controller."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_PRICE_INCLUDE_TAX,
    CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
    CONF_PRICE_NORMAL_METER_ENABLED,
    CONF_PRICE_RECOVERY_THRESHOLD,
    CONF_PRICE_SENSOR,
    CONF_PRICE_THRESHOLD,
    CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
    CONF_PRICE_TRIGGER_METER_ENABLED,
    DEFAULT_PRICE_INCLUDE_TAX,
    DEFAULT_PRICE_NORMAL_EXPORT_PERCENTAGE,
    DEFAULT_PRICE_NORMAL_METER_ENABLED,
    DEFAULT_PRICE_RECOVERY_THRESHOLD,
    DEFAULT_PRICE_THRESHOLD,
    DEFAULT_PRICE_TRIGGER_EXPORT_PERCENTAGE,
    DEFAULT_PRICE_TRIGGER_METER_ENABLED,
)


class GrowattExportControllerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Growatt Export Controller options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PRICE_SENSOR,
                    default=options.get(CONF_PRICE_SENSOR, ""),
                ): str,
                vol.Optional(
                    CONF_PRICE_THRESHOLD,
                    default=options.get(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_PRICE_RECOVERY_THRESHOLD,
                    default=options.get(
                        CONF_PRICE_RECOVERY_THRESHOLD,
                        DEFAULT_PRICE_RECOVERY_THRESHOLD,
                    ),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_PRICE_INCLUDE_TAX,
                    default=options.get(
                        CONF_PRICE_INCLUDE_TAX,
                        DEFAULT_PRICE_INCLUDE_TAX,
                    ),
                ): bool,
                vol.Optional(
                    CONF_PRICE_TRIGGER_METER_ENABLED,
                    default=options.get(
                        CONF_PRICE_TRIGGER_METER_ENABLED,
                        DEFAULT_PRICE_TRIGGER_METER_ENABLED,
                    ),
                ): bool,
                vol.Optional(
                    CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
                    default=options.get(
                        CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE,
                        DEFAULT_PRICE_TRIGGER_EXPORT_PERCENTAGE,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_PRICE_NORMAL_METER_ENABLED,
                    default=options.get(
                        CONF_PRICE_NORMAL_METER_ENABLED,
                        DEFAULT_PRICE_NORMAL_METER_ENABLED,
                    ),
                ): bool,
                vol.Optional(
                    CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
                    default=options.get(
                        CONF_PRICE_NORMAL_EXPORT_PERCENTAGE,
                        DEFAULT_PRICE_NORMAL_EXPORT_PERCENTAGE,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return GrowattExportControllerOptionsFlowHandler(config_entry)
