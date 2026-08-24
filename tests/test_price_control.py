"""Tests for pure Growatt price-control logic."""

import pytest

from custom_components.growatt_export_controller.models import (
    GrowattControlSettings,
    PriceControlMode,
)
from custom_components.growatt_export_controller.price_control import (
    convert_tax_basis,
    evaluate_price,
    normalize_price_to_eur_per_kwh,
)


def _settings() -> GrowattControlSettings:
    return GrowattControlSettings(
        price_automation_enabled=True,
        activation_threshold=0.05,
        recovery_threshold=0.06,
        trigger_meter_enabled=True,
        trigger_export_percentage=100,
        normal_meter_enabled=False,
        normal_export_percentage=100,
    )


def test_activation_uses_requested_growatt_behavior() -> None:
    decision = evaluate_price(
        settings=_settings(),
        current_mode=PriceControlMode.NORMAL,
        effective_price=0.04,
    )

    assert decision.mode is PriceControlMode.TRIGGERED
    assert decision.changed is True
    assert decision.meter_enabled is True
    assert decision.export_percentage == 100


def test_hysteresis_holds_triggered_mode() -> None:
    decision = evaluate_price(
        settings=_settings(),
        current_mode=PriceControlMode.TRIGGERED,
        effective_price=0.055,
    )

    assert decision.mode is PriceControlMode.TRIGGERED
    assert decision.changed is False


def test_recovery_restores_normal_feed_in() -> None:
    decision = evaluate_price(
        settings=_settings(),
        current_mode=PriceControlMode.TRIGGERED,
        effective_price=0.061,
    )

    assert decision.mode is PriceControlMode.NORMAL
    assert decision.meter_enabled is False
    assert decision.export_percentage == 100


def test_unit_normalization() -> None:
    assert normalize_price_to_eur_per_kwh(5.0, "ct/kWh") == 0.05
    assert normalize_price_to_eur_per_kwh(50.0, "EUR/MWh") == 0.05
    assert normalize_price_to_eur_per_kwh(0.05, "EUR/kWh") == 0.05


def test_tax_basis_round_trip() -> None:
    including = convert_tax_basis(
        0.10,
        source_includes_tax=False,
        target_includes_tax=True,
        vat_percent=21.0,
        fixed_tax_eur_per_kwh=0.05,
    )
    excluding = convert_tax_basis(
        including,
        source_includes_tax=True,
        target_includes_tax=False,
        vat_percent=21.0,
        fixed_tax_eur_per_kwh=0.05,
    )

    assert including == pytest.approx(0.1815)
    assert excluding == pytest.approx(0.10)
