"""Pure price conversion and decision logic."""

from __future__ import annotations

import math

from .models import GrowattControlSettings, PriceControlMode, PriceDecision

_CENT_UNITS = {
    "c/kwh",
    "ct/kwh",
    "cent/kwh",
    "cents/kwh",
    "€ct/kwh",
    "eurcent/kwh",
}
_MWH_UNITS = {"eur/mwh", "€/mwh", "euro/mwh"}


def parse_numeric_price(raw_value: object) -> float | None:
    """Parse a Home Assistant sensor state as a finite float."""

    if raw_value is None:
        return None
    text = str(raw_value).strip().replace(",", ".")
    if text.lower() in {"", "none", "unknown", "unavailable", "nan", "inf", "-inf"}:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def normalize_price_to_eur_per_kwh(value: float, unit: str | None) -> float:
    """Normalize common electricity-price units to EUR/kWh."""

    normalized = (unit or "").strip().lower().replace(" ", "")
    normalized = normalized.replace("euro", "eur")

    if normalized in _CENT_UNITS or normalized.endswith("ct/kwh"):
        return value / 100.0
    if normalized in _MWH_UNITS or normalized.endswith("/mwh"):
        return value / 1000.0
    return value


def convert_tax_basis(
    price_eur_per_kwh: float,
    *,
    source_includes_tax: bool,
    target_includes_tax: bool,
    vat_percent: float,
    fixed_tax_eur_per_kwh: float,
) -> float:
    """Convert a price between excluding- and including-tax bases.

    ``fixed_tax_eur_per_kwh`` is interpreted as a fixed amount excluding VAT.
    It can also be used for other fixed per-kWh additions, such as supplier fees.
    No conversion is applied when source and target already use the same basis.
    """

    if source_includes_tax == target_includes_tax:
        return price_eur_per_kwh

    vat_factor = 1.0 + (max(0.0, vat_percent) / 100.0)
    fixed_tax = fixed_tax_eur_per_kwh

    if target_includes_tax:
        return (price_eur_per_kwh + fixed_tax) * vat_factor

    return (price_eur_per_kwh / vat_factor) - fixed_tax


def validate_settings(settings: GrowattControlSettings) -> None:
    """Raise ``ValueError`` when price-control settings are inconsistent."""

    if not 0 <= settings.trigger_export_percentage <= 100:
        raise ValueError("Trigger export percentage must be between 0 and 100")
    if not 0 <= settings.normal_export_percentage <= 100:
        raise ValueError("Normal export percentage must be between 0 and 100")
    if settings.recovery_threshold < settings.activation_threshold:
        raise ValueError("Recovery threshold must be at least the activation threshold")
    if settings.poll_interval_minutes < 1:
        raise ValueError("Poll interval must be at least one minute")
    if settings.reapply_interval_minutes < 0:
        raise ValueError("Reapply interval cannot be negative")


def evaluate_price(
    *,
    settings: GrowattControlSettings,
    current_mode: PriceControlMode,
    effective_price: float,
) -> PriceDecision:
    """Evaluate the effective electricity price with hysteresis."""

    validate_settings(settings)

    if current_mode is PriceControlMode.TRIGGERED:
        if effective_price >= settings.recovery_threshold:
            next_mode = PriceControlMode.NORMAL
            reason = (
                f"Price {effective_price:.5f} EUR/kWh reached the recovery threshold "
                f"{settings.recovery_threshold:.5f}"
            )
        else:
            next_mode = PriceControlMode.TRIGGERED
            reason = (
                f"Price {effective_price:.5f} EUR/kWh remains below the recovery threshold "
                f"{settings.recovery_threshold:.5f}"
            )
    elif effective_price <= settings.activation_threshold:
        next_mode = PriceControlMode.TRIGGERED
        reason = (
            f"Price {effective_price:.5f} EUR/kWh is at or below the activation threshold "
            f"{settings.activation_threshold:.5f}"
        )
    else:
        next_mode = PriceControlMode.NORMAL
        reason = (
            f"Price {effective_price:.5f} EUR/kWh is above the activation threshold "
            f"{settings.activation_threshold:.5f}"
        )

    if next_mode is PriceControlMode.TRIGGERED:
        meter_enabled = settings.trigger_meter_enabled
        export_percentage = settings.trigger_export_percentage
    else:
        meter_enabled = settings.normal_meter_enabled
        export_percentage = settings.normal_export_percentage

    return PriceDecision(
        mode=next_mode,
        changed=next_mode is not current_mode,
        meter_enabled=meter_enabled,
        export_percentage=export_percentage,
        reason=reason,
    )
