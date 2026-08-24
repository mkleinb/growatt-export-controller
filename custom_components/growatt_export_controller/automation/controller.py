"""Automation controller for Growatt export control."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .decision_engine import DecisionResult, PriceAutomationConfig, PriceDecisionEngine

_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class GrowattExportApi(Protocol):
    """Protocol for the Growatt API client used by the automation controller."""

    async def async_set_export_limit(
        self, *, meter_enabled: bool, percentage: int
    ) -> None:
        """Apply an export limit change."""


@dataclass(slots=True)
class AutomationRuntimeState:
    """Runtime state used for diagnostics and change detection."""

    last_price: float | None = None
    last_decision: DecisionResult | None = None
    last_applied_meter_enabled: bool | None = None
    last_applied_export_percentage: int | None = None
    last_error: str | None = None
    update_count: int = 0
    applied_count: int = 0


@dataclass(slots=True)
class AutomationApplyResult:
    """Structured result of a controller update."""

    decision: DecisionResult
    applied: bool
    changed: bool
    error: str | None = None


@dataclass(slots=True)
class PriceAutomationController:
    """Coordinate price evaluation and Growatt export limit updates."""

    api: GrowattExportApi
    config: PriceAutomationConfig
    engine: PriceDecisionEngine = field(init=False)
    state: AutomationRuntimeState = field(default_factory=AutomationRuntimeState)

    def __post_init__(self) -> None:
        """Initialize the stateful decision engine."""
        self.engine = PriceDecisionEngine(self.config)

    async def async_update(
        self,
        *,
        current_price: float | None,
        force_apply: bool = False,
    ) -> AutomationApplyResult:
        """Evaluate the current price and apply the matching Growatt settings."""
        self.state.update_count += 1
        self.state.last_price = current_price
        self.state.last_error = None

        decision = self.engine.evaluate(current_price)
        self.state.last_decision = decision

        if not self.config.enabled:
            _LOGGER.debug("Price automation disabled; no action taken")
            return AutomationApplyResult(
                decision=decision,
                applied=False,
                changed=decision.changed,
            )

        if not decision.changed and not force_apply:
            _LOGGER.debug(
                "No Growatt action needed: price=%s mode=%s reason=%s",
                current_price,
                decision.mode,
                decision.reason,
            )
            return AutomationApplyResult(
                decision=decision,
                applied=False,
                changed=False,
            )

        try:
            await self.api.async_set_export_limit(
                meter_enabled=decision.target_meter_enabled,
                percentage=decision.target_export_percentage,
            )
        except Exception as exc:
            error = str(exc)
            self.state.last_error = error
            _LOGGER.exception(
                "Failed to apply Growatt export limit: price=%s mode=%s",
                current_price,
                decision.mode,
            )
            return AutomationApplyResult(
                decision=decision,
                applied=False,
                changed=decision.changed,
                error=error,
            )

        self.state.applied_count += 1
        self.state.last_applied_meter_enabled = decision.target_meter_enabled
        self.state.last_applied_export_percentage = decision.target_export_percentage

        _LOGGER.info(
            "Applied Growatt export limit: price=%s mode=%s meter_enabled=%s percentage=%s reason=%s",
            current_price,
            decision.mode,
            decision.target_meter_enabled,
            decision.target_export_percentage,
            decision.reason,
        )

        return AutomationApplyResult(
            decision=decision,
            applied=True,
            changed=decision.changed,
        )

    async def async_force_apply(
        self, *, current_price: float | None = None
    ) -> AutomationApplyResult:
        """Force application of the current target state."""
        return await self.async_update(current_price=current_price, force_apply=True)
