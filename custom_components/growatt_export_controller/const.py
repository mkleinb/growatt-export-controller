"""Constants for the Growatt Export Controller integration."""

from __future__ import annotations

DOMAIN = "growatt_export_controller"
DEFAULT_NAME = "Growatt Export Controller"

DEFAULT_COMMAND_BASE_URL = "https://server.growatt.com"
DEFAULT_LOGIN_BASE_URL = "https://oss.growatt.com"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2

DEFAULT_EXPORT_PERCENTAGE = 100
DEFAULT_METER_ENABLED = False
DEFAULT_TRIGGER_EXPORT_PERCENTAGE = 100
DEFAULT_TRIGGER_METER_ENABLED = True
DEFAULT_NORMAL_EXPORT_PERCENTAGE = 100
DEFAULT_NORMAL_METER_ENABLED = False

DEFAULT_PRICE_AUTOMATION_ENABLED = False
DEFAULT_PRICE_ACTIVATION_THRESHOLD = 0.05
DEFAULT_PRICE_RECOVERY_THRESHOLD = 0.06
DEFAULT_PRICE_SENSOR_INCLUDES_TAX = True
DEFAULT_PRICE_THRESHOLD_INCLUDES_TAX = True
DEFAULT_PRICE_VAT_PERCENT = 21.0
DEFAULT_PRICE_FIXED_TAX_EUR_PER_KWH = 0.0
DEFAULT_PRICE_POLL_INTERVAL_MINUTES = 5
DEFAULT_PRICE_REAPPLY_INTERVAL_MINUTES = 60

CONF_COMMAND_BASE_URL = "command_base_url"
CONF_LOGIN_BASE_URL = "login_base_url"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_RETRY_ATTEMPTS = "retry_attempts"
CONF_RETRY_BACKOFF_SECONDS = "retry_backoff_seconds"
CONF_DEFAULT_EXPORT_PERCENTAGE = "default_export_percentage"
CONF_DEFAULT_METER_ENABLED = "default_meter_enabled"
CONF_SERIAL_NUMBER = "serial_number"
CONF_DEVICE_PASSWORD_PREFIX = "device_password_prefix"  # Legacy, retained for compatibility.

CONF_PRICE_AUTOMATION_ENABLED = "price_automation_enabled"
CONF_PRICE_SENSOR = "price_sensor"
CONF_PRICE_ACTIVATION_THRESHOLD = "price_activation_threshold"
CONF_PRICE_RECOVERY_THRESHOLD = "price_recovery_threshold"
CONF_PRICE_TRIGGER_METER_ENABLED = "price_trigger_meter_enabled"
CONF_PRICE_TRIGGER_EXPORT_PERCENTAGE = "price_trigger_export_percentage"
CONF_PRICE_NORMAL_METER_ENABLED = "price_normal_meter_enabled"
CONF_PRICE_NORMAL_EXPORT_PERCENTAGE = "price_normal_export_percentage"
CONF_PRICE_SENSOR_INCLUDES_TAX = "price_sensor_includes_tax"
CONF_PRICE_THRESHOLD_INCLUDES_TAX = "price_threshold_includes_tax"
CONF_PRICE_VAT_PERCENT = "price_vat_percent"
CONF_PRICE_FIXED_TAX_EUR_PER_KWH = "price_fixed_tax_eur_per_kwh"
CONF_PRICE_POLL_INTERVAL_MINUTES = "price_poll_interval_minutes"
CONF_PRICE_REAPPLY_INTERVAL_MINUTES = "price_reapply_interval_minutes"

# Aliases created by early development builds. They are migrated/read for compatibility.
LEGACY_CONF_INVERTER_SERIAL = "inverter_serial"
LEGACY_CONF_COMMAND_SERVER_URL = "command_server_url"
LEGACY_CONF_AUTO_PRICE_CONTROL_ENABLED = "auto_price_control_enabled"
LEGACY_CONF_PRICE_SENSOR_ENTITY_ID = "price_sensor_entity_id"
LEGACY_CONF_PRICE_THRESHOLD = "price_threshold"
LEGACY_CONF_PRICE_DEACTIVATION_THRESHOLD = "price_deactivation_threshold"
LEGACY_CONF_PRICE_COMPARISON_INCLUDES_TAX = "price_comparison_includes_tax"
LEGACY_CONF_PRICE_TAX_RATE_PERCENT = "price_tax_rate_percent"

ATTR_PERCENTAGE = "percentage"
ATTR_METER_ENABLED = "meter_enabled"
ATTR_FORCE_APPLY = "force_apply"

SERVICE_SET_EXPORT_LIMIT = "set_export_limit"
SERVICE_EVALUATE_PRICE_CONTROL = "evaluate_price_control"

PLATFORMS = ["number", "switch", "sensor"]
