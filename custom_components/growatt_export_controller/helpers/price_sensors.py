"""Helpers to discover likely price sensors."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

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
    "ct/kwh",
    "c/kwh",
)

DEVICE_CLASS_HINTS = {"monetary"}

WEIGHT_DEVICE_CLASS = 50
WEIGHT_UNIT = 40
WEIGHT_ENTITY_ID = 30
WEIGHT_FRIENDLY_NAME = 20
WEIGHT_STATE_CLASS = 10


@dataclass(slots=True, frozen=True)
class PriceSensorCandidate:
    """A ranked candidate for a likely electricity price sensor."""

    entity_id: str
    friendly_name: str
    score: int
    reasons: tuple[str, ...]


def _normalize(value: str | None) -> str:
    return value.lower().strip() if value else ""


def _contains_hint(value: str | None, hints: Iterable[str]) -> bool:
    text = _normalize(value)
    return bool(text) and any(hint in text for hint in hints)


def _is_numeric_state(state: State) -> bool:
    try:
        float(state.state)
    except (TypeError, ValueError):
        return False
    return True


def _score_state(state: State) -> PriceSensorCandidate | None:
    """Score a sensor and return a candidate if it looks like a price sensor."""
    if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    if not _is_numeric_state(state):
        return None

    entity_id = state.entity_id
    attrs = state.attributes
    friendly_name = str(attrs.get("friendly_name") or entity_id)
    device_class = _normalize(attrs.get("device_class"))
    unit = attrs.get("unit_of_measurement")
    state_class = _normalize(attrs.get("state_class"))

    score = 0
    reasons: list[str] = []

    if device_class in DEVICE_CLASS_HINTS:
        score += WEIGHT_DEVICE_CLASS
        reasons.append(f"device_class={device_class}")

    if _contains_hint(unit, PRICE_UNIT_HINTS):
        score += WEIGHT_UNIT
        reasons.append(f"unit={unit}")

    if _contains_hint(entity_id, PRICE_ID_HINTS):
        score += WEIGHT_ENTITY_ID
        reasons.append("entity_id_hint")

    if _contains_hint(friendly_name, PRICE_NAME_HINTS):
        score += WEIGHT_FRIENDLY_NAME
        reasons.append("friendly_name_hint")

    if state_class:
        score += WEIGHT_STATE_CLASS
        reasons.append(f"state_class={state_class}")

    if score <= 0:
        return None

    return PriceSensorCandidate(
        entity_id=entity_id,
        friendly_name=friendly_name,
        score=score,
        reasons=tuple(reasons),
    )


def discover_price_sensor_candidates(
    hass: HomeAssistant,
) -> list[PriceSensorCandidate]:
    """Return ranked candidates for likely price sensors."""
    candidates: list[PriceSensorCandidate] = []

    for state in hass.states.async_all("sensor"):
        candidate = _score_state(state)
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (-item.score, item.friendly_name.lower(), item.entity_id)
    )
    return candidates


def discover_price_sensors(hass: HomeAssistant) -> list[tuple[str, str]]:
    """Return candidate price sensors as (entity_id, label)."""
    candidates = discover_price_sensor_candidates(hass)
    return [
        (candidate.entity_id, f"{candidate.friendly_name} ({candidate.score})")
        for candidate in candidates
    ]
