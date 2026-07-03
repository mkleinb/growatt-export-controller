"""Constants for Growatt Export Controller."""

from __future__ import annotations

DOMAIN = "growatt_export_controller"
DEFAULT_NAME = "Growatt Export Controller"
DEFAULT_COMMAND_BASE_URL = "https://server.growatt.com"
DEFAULT_LOGIN_BASE_URL = "https://oss.growatt.com"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2
DEFAULT_SERVICE_METER_ENABLED = False
DEFAULT_EXPORT_PERCENTAGE = 100
DEFAULT_DEVICE_PASSWORD_PREFIX = "growatt"

CONF_COMMAND_BASE_URL = "command_base_url"
CONF_LOGIN_BASE_URL = "login_base_url"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_RETRY_ATTEMPTS = "retry_attempts"
CONF_RETRY_BACKOFF_SECONDS = "retry_backoff_seconds"
CONF_DEFAULT_EXPORT_PERCENTAGE = "default_export_percentage"
CONF_DEFAULT_METER_ENABLED = "default_meter_enabled"
CONF_SERIAL_NUMBER = "serial_number"
CONF_DEVICE_PASSWORD_PREFIX = "device_password_prefix"

ATTR_PERCENTAGE = "percentage"
ATTR_METER_ENABLED = "meter_enabled"
ATTR_RESPONSE = "response"
ATTR_STATUS = "status"
ATTR_LAST_COMMAND = "last_command"
ATTR_LAST_ERROR = "last_error"
ATTR_LAST_HTTP_STATUS = "last_http_status"
ATTR_LAST_LOGIN_STATUS = "last_login_status"
ATTR_LAST_LOGIN_RESPONSE = "last_login_response"
ATTR_LAST_ENDPOINT = "last_endpoint"

PLATFORMS = ["number", "switch", "sensor"]

SERVICE_SET_EXPORT_LIMIT = "set_export_limit"
