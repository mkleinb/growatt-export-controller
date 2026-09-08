"""Pure price conversion and decision logic."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

from .models import GrowattControlSettings, PriceControlMode, PriceDecision, PriceStrategy

_CENT_UNITS = {
    "c/kwh",
    "ct/kwh",
    "cent/kwh",
    "cents/kwh",
    "€ct/kwh",
    "eurcent/kwh",
}
_MWH_UNITS = {"eur/mwh", "€/mwh", "euro/mwh"}
_SALDERING_END = date(2027, 1, 1)
_ZONNEPLAN_AMOUNT_SCALE = 10_000_000.0


class EconomicPriceUnavailable(ValueError):
    """Raised when automatic economic mode lacks the required price basis."""


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


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _money_value(value: object, *, scaled_api_amount: bool = False) -> float | None:
    """Extract a monetary value from common Zonneplan/HA structures."""

    if isinstance(value, Mapping):
        if "amount" not in value:
            return None
        return _money_value(value.get("amount"), scaled_api_amount=True)

    parsed = parse_numeric_price(value)
    if parsed is None:
        return None
    return parsed / _ZONNEPLAN_AMOUNT_SCALE if scaled_api_amount else parsed


def _tax_excluded_from_item(item: Mapping[str, Any]) -> float | None:
    """Extract an excl-tax EUR/kWh price from one sensor/forecast mapping."""

    for key in (
        "price_tax_excluded",
        "electricity_price_excl_tax",
        "price_excl_tax",
        "price_excluding_tax",
    ):
        if key not in item:
            continue
        # Zonneplan's nested ``price_tax_excluded.amount`` and legacy
        # ``electricity_price_excl_tax`` forecast fields use 1e-7 EUR units.
        scaled = key == "electricity_price_excl_tax" and not isinstance(item[key], Mapping)
        value = _money_value(item[key], scaled_api_amount=scaled)
        if value is not None:
            return value
    return None


def extract_current_tax_excluded_price(
    attributes: Mapping[str, Any],
    *,
    now: datetime,
) -> float | None:
    """Return the current tax-excluded EUR/kWh price when the sensor exposes it.

    Supports the current and legacy forecast structures used by Zonneplan One,
    plus direct excl-tax attributes used by other integrations.
    """

    direct = _tax_excluded_from_item(attributes)
    if direct is not None:
        return direct

    forecast = attributes.get("forecast")
    if not isinstance(forecast, Sequence) or isinstance(forecast, (str, bytes)):
        return None

    now_cmp = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    candidates: list[tuple[datetime | None, datetime | None, Mapping[str, Any]]] = []
    for raw_item in forecast:
        if not isinstance(raw_item, Mapping):
            continue
        start = _parse_datetime(
            raw_item.get("start_date")
            or raw_item.get("start_datetime")
            or raw_item.get("datetime")
        )
        end = _parse_datetime(raw_item.get("end_date") or raw_item.get("end_datetime"))
        candidates.append((start, end, raw_item))

    # Prefer an interval that contains 'now'.
    for start, end, item in candidates:
        if start is None:
            continue
        if start <= now_cmp and (end is None or now_cmp < end):
            value = _tax_excluded_from_item(item)
            if value is not None:
                return value

    # Some older integrations expose only a start time. Use the latest started
    # forecast row in that case.
    started = [entry for entry in candidates if entry[0] is not None and entry[0] <= now_cmp]
    started.sort(key=lambda entry: entry[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for _, _, item in started:
        value = _tax_excluded_from_item(item)
        if value is not None:
            return value

    return None


def economic_effective_price(
    *,
    source_price: float,
    source_includes_tax: bool,
    tax_excluded_price: float | None,
    within_saldering_2026: bool,
    today: date,
) -> tuple[float, str]:
    """Choose the economically relevant return value around the 2027 rule change.

    Through 31 December 2026, users whose annual grid export stays within their
    annual grid consumption can still value a returned kWh on the tax-included
    saldered basis. From 1 January 2027, or for a 2026 surplus outside that
    saldering room, the tax-excluded return value is used.
    """

    if today < _SALDERING_END and within_saldering_2026:
        if not source_includes_tax:
            raise EconomicPriceUnavailable(
                "Automatic economic mode needs a tax-included source price for "
                "2026 saldering. Select an incl-tax tariff sensor or use manual mode."
            )
        return source_price, "2026_saldered_tax_included"

    if not source_includes_tax:
        return source_price, "tax_excluded_source"

    if tax_excluded_price is None:
        period = "from 2027" if today >= _SALDERING_END else "outside 2026 saldering"
        raise EconomicPriceUnavailable(
            "Automatic economic mode needs a tax-excluded price "
            f"{period}. The selected sensor does not expose a current excl-tax value."
        )

    return tax_excluded_price, "tax_excluded_return_value"


def decision_thresholds(settings: GrowattControlSettings) -> tuple[float, float]:
    """Return activation/recovery thresholds for the configured strategy."""

    if settings.price_strategy is PriceStrategy.ECONOMIC_AUTO:
        return 0.0, settings.economic_recovery_margin
    return settings.activation_threshold, settings.recovery_threshold


def validate_settings(settings: GrowattControlSettings) -> None:
    """Raise ``ValueError`` when price-control settings are inconsistent."""

    if not 0 <= settings.trigger_export_percentage <= 100:
        raise ValueError("Trigger export percentage must be between 0 and 100")
    if not 0 <= settings.normal_export_percentage <= 100:
        raise ValueError("Normal export percentage must be between 0 and 100")
    if settings.price_strategy is PriceStrategy.ECONOMIC_AUTO:
        if settings.economic_recovery_margin < 0:
            raise ValueError("Economic recovery margin cannot be negative")
    elif settings.recovery_threshold < settings.activation_threshold:
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
    activation_threshold, recovery_threshold = decision_thresholds(settings)

    if current_mode is PriceControlMode.TRIGGERED:
        if effective_price >= recovery_threshold:
            next_mode = PriceControlMode.NORMAL
            reason = (
                f"Price {effective_price:.5f} EUR/kWh reached the recovery threshold "
                f"{recovery_threshold:.5f}"
            )
        else:
            next_mode = PriceControlMode.TRIGGERED
            reason = (
                f"Price {effective_price:.5f} EUR/kWh remains below the recovery threshold "
                f"{recovery_threshold:.5f}"
            )
    elif effective_price <= activation_threshold:
        next_mode = PriceControlMode.TRIGGERED
        reason = (
            f"Price {effective_price:.5f} EUR/kWh is at or below the activation threshold "
            f"{activation_threshold:.5f}"
        )
    else:
        next_mode = PriceControlMode.NORMAL
        reason = (
            f"Price {effective_price:.5f} EUR/kWh is above the activation threshold "
            f"{activation_threshold:.5f}"
        )

    if settings.price_strategy is PriceStrategy.ECONOMIC_AUTO:
        # Automatic economic mode has one fixed safety policy:
        # when exporting has no positive economic value, keep the inverter
        # available for self-consumption but prevent grid export. Growatt's
        # meter-based export control does that with Meter Enable ON and a
        # 0% export limit. When feed-in is economic again, disable the meter
        # limit and restore 100% export.
        if next_mode is PriceControlMode.TRIGGERED:
            meter_enabled = True
            export_percentage = 0
        else:
            meter_enabled = False
            export_percentage = 100
    elif next_mode is PriceControlMode.TRIGGERED:
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
