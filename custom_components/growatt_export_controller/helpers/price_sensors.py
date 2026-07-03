"""Helpers to discover likely price sensors."""

from __future__ import annotations

from typing import Iterable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State

PRICE_ID_HINTS = (
    "price",
    "tariff",
    "electricity",
    "energy_price",
    "spot",
    "zonneplan",
    "tibber",
    "nordpool",
    "kwh",
)

PRICE_NAME_HINTS = (
    "price",
    "electricity",
    "energy",
    "tariff",
    "spot",
)

PRICE_UNIT_HINTS = (
    "€/kwh",
    "eur/kwh",
    "eur / kwh",
    "euro/kwh",
)


def _is_numeric_state(state: State) -> bool:
    try:
        float(state.state)
    except (TypeError, ValueError):
        return False
    return True


def _contains_hint(value: str | None, hints: Iterable[str]) -> bool:
    if not value:
        return False
    text = value.lower()
    return any(hint in text for hint in hints)


def discover_price_sensors(hass: HomeAssistant) -> list[tuple[str, str]]:
    """Return candidate price sensors as (entity_id, label)."""
    candidates: list[tuple[str, str]] = []

    for state in hass.states.async_all("sensor"):
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            continue
        if not _is_numeric_state(state):
            continue

        entity_id = state.entity_id
        attrs = state.attributes
        friendly_name = attrs.get("friendly_name") or entity_id
        device_class = attrs.get("device_class")
        unit = attrs.get("unit_of_measurement")

        has_hint = (
            _contains_hint(entity_id, PRICE_ID_HINTS)
            or _contains_hint(friendly_name, PRICE_NAME_HINTS)
            or _contains_hint(unit, PRICE_UNIT_HINTS)
            or (device_class == "monetary")
        )

        if not has_hint:
            continue

        candidates.append((entity_id, str(friendly_name)))

    candidates.sort(key=lambda item: item[1].lower())
    return candidates
