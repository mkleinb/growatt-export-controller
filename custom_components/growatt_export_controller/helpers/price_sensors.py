"""Discovery of likely current electricity-price sensors."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State

from ..price_control import parse_numeric_price

_PROVIDER_HINTS = (
    "zonneplan",
    "tibber",
    "nordpool",
    "nord_pool",
    "anwb",
    "easyenergy",
    "easy_energy",
    "energyzero",
    "enever",
    "essent",
    "frank_energie",
    "nextenergy",
    "next_energy",
    "powerpeers",
)
_PRICE_HINTS = (
    "electricity_price",
    "electricity_tariff",
    "energy_price",
    "stroomprijs",
    "stroom_prijs",
    "elektriciteitsprijs",
    "electricity price",
    "electricity tariff",
    "energy price",
    "current tariff",
    "huidig tarief",
    "actueel tarief",
    "spot price",
    "marktprijs",
    "market price",
    "tariff",
    "tarief",
    "price",
    "prijs",
)
_CURRENT_HINTS = ("current", "currently", "huidig", "actueel", "now", "nu")
_NON_CURRENT_HINTS = (
    "tomorrow",
    "morgen",
    "next",
    "volgend",
    "average",
    "gemiddeld",
    "lowest",
    "laagste",
    "highest",
    "hoogste",
    "forecast",
    "verwachting",
    "history",
    "historie",
    "gas",
)
_PRICE_UNIT_HINTS = (
    "€/kwh",
    "eur/kwh",
    "euro/kwh",
    "ct/kwh",
    "c/kwh",
    "cent/kwh",
    "€/mwh",
    "eur/mwh",
)


@dataclass(slots=True, frozen=True)
class PriceSensorCandidate:
    """Ranked electricity-price sensor candidate."""

    entity_id: str
    name: str
    score: int
    current_value: float
    unit: str | None
    reasons: tuple[str, ...]

    @property
    def label(self) -> str:
        """Return a compact, user-friendly dropdown label."""

        value = f"{self.current_value:g}"
        if self.unit:
            value = f"{value} {self.unit}"
        return f"{self.name} — {value}"


def _normalized(value: object) -> str:
    return str(value or "").strip().lower()


def _has_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def _score_state(state: State) -> PriceSensorCandidate | None:
    if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
        return None

    numeric_value = parse_numeric_price(state.state)
    if numeric_value is None:
        return None

    name = str(state.attributes.get("friendly_name") or state.entity_id)
    unit = state.attributes.get("unit_of_measurement")
    device_class = _normalized(state.attributes.get("device_class"))

    searchable = f"{state.entity_id} {name}".lower()
    normalized_unit = _normalized(unit).replace(" ", "")

    unit_match = _has_any(normalized_unit, _PRICE_UNIT_HINTS)
    price_match = _has_any(searchable, _PRICE_HINTS)
    provider_match = _has_any(searchable, _PROVIDER_HINTS)

    # Monetary sensors without an electricity-price hint can be bank balances,
    # cost totals or other unrelated values. Do not include those.
    if not unit_match and not price_match:
        return None

    score = 0
    reasons: list[str] = []

    if unit_match:
        score += 70
        reasons.append("electricity price unit")
    if price_match:
        score += 45
        reasons.append("price or tariff name")
    if provider_match:
        score += 20
        reasons.append("known energy provider")
    if device_class == "monetary":
        score += 10
        reasons.append("monetary device class")
    if _has_any(searchable, _CURRENT_HINTS):
        score += 15
        reasons.append("current-price name")
    if _has_any(searchable, _NON_CURRENT_HINTS):
        score -= 35
        reasons.append("non-current price name")

    if score < 40:
        return None

    return PriceSensorCandidate(
        entity_id=state.entity_id,
        name=name,
        score=score,
        current_value=numeric_value,
        unit=str(unit) if unit is not None else None,
        reasons=tuple(reasons),
    )


def discover_price_sensor_candidates(hass: HomeAssistant) -> list[PriceSensorCandidate]:
    """Return likely price sensors, best match first."""

    candidates = [
        candidate
        for state in hass.states.async_all("sensor")
        if (candidate := _score_state(state)) is not None
    ]
    candidates.sort(key=lambda item: (-item.score, item.name.casefold(), item.entity_id))
    return candidates
