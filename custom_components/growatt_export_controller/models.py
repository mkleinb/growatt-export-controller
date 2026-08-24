"""Data models for Growatt Export Controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .const import (
    DEFAULT_EXPORT_PERCENTAGE,
    DEFAULT_METER_ENABLED,
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
    DEFAULT_TRIGGER_EXPORT_PERCENTAGE,
    DEFAULT_TRIGGER_METER_ENABLED,
)


class PriceControlMode(StrEnum):
    """Operating mode selected by price control."""

    DISABLED = "disabled"
    NORMAL = "normal"
    TRIGGERED = "triggered"
    ERROR = "error"


@dataclass(slots=True, frozen=True)
class GrowattControlSettings:
    """User-configurable controller settings."""

    default_export_percentage: int = DEFAULT_EXPORT_PERCENTAGE
    default_meter_enabled: bool = DEFAULT_METER_ENABLED

    price_automation_enabled: bool = DEFAULT_PRICE_AUTOMATION_ENABLED
    price_sensor: str | None = None
    activation_threshold: float = DEFAULT_PRICE_ACTIVATION_THRESHOLD
    recovery_threshold: float = DEFAULT_PRICE_RECOVERY_THRESHOLD

    trigger_meter_enabled: bool = DEFAULT_TRIGGER_METER_ENABLED
    trigger_export_percentage: int = DEFAULT_TRIGGER_EXPORT_PERCENTAGE
    normal_meter_enabled: bool = DEFAULT_NORMAL_METER_ENABLED
    normal_export_percentage: int = DEFAULT_NORMAL_EXPORT_PERCENTAGE

    sensor_includes_tax: bool = DEFAULT_PRICE_SENSOR_INCLUDES_TAX
    threshold_includes_tax: bool = DEFAULT_PRICE_THRESHOLD_INCLUDES_TAX
    vat_percent: float = DEFAULT_PRICE_VAT_PERCENT
    fixed_tax_eur_per_kwh: float = DEFAULT_PRICE_FIXED_TAX_EUR_PER_KWH

    poll_interval_minutes: int = DEFAULT_PRICE_POLL_INTERVAL_MINUTES
    reapply_interval_minutes: int = DEFAULT_PRICE_REAPPLY_INTERVAL_MINUTES


@dataclass(slots=True, frozen=True)
class PriceDecision:
    """Result of one price-control evaluation."""

    mode: PriceControlMode
    changed: bool
    meter_enabled: bool
    export_percentage: int
    reason: str


@dataclass(slots=True)
class GrowattControllerState:
    """Mutable runtime state exposed through Home Assistant entities."""

    export_percentage: int = DEFAULT_EXPORT_PERCENTAGE
    meter_enabled: bool = DEFAULT_METER_ENABLED
    authenticated: bool = False

    last_command: str = "idle"
    last_error: str | None = None
    last_http_status: int | None = None
    last_response: str | None = None
    last_login_status: int | None = None
    last_login_response: str | None = None
    last_endpoint: str | None = None
    last_command_at: datetime | None = None

    price_mode: PriceControlMode = PriceControlMode.DISABLED
    price_sensor: str | None = None
    source_price: float | None = None
    effective_price: float | None = None
    source_unit: str | None = None
    price_reason: str | None = None
    price_last_checked_at: datetime | None = None
    price_last_applied_at: datetime | None = None
    price_last_error: str | None = None
