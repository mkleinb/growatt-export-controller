"""Decision engine for Growatt price automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AutomationMode = Literal["normal", "triggered"]


@dataclass(slots=True, frozen=True)
class PriceAutomationConfig:
    """Configuration for price-based Growatt export automation."""

    enabled: bool = False
    threshold: float = 0.0
    recovery_threshold: float = 0.0
    trigger_meter_enabled: bool = True
    trigger_export_percentage: int = 100
    normal_meter_enabled: bool = False
    normal_export_percentage: int = 100

    def validate(self) -> None:
        """Validate configuration values."""
        if self.trigger_export_percentage < 0 or self.trigger_export_percentage > 100:
            raise ValueError("trigger_export_percentage must be between 0 and 100")

        if self.normal_export_percentage < 0 or self.normal_export_percentage > 100:
            raise ValueError("normal_export_percentage must be between 0 and 100")

        if self.recovery_threshold < self.threshold:
            raise ValueError(
                "recovery_threshold must be greater than or equal to threshold"
            )


@dataclass(slots=True, frozen=True)
class DecisionResult:
    """Result of evaluating the current electricity price."""

    mode: AutomationMode
    changed: bool
    target_meter_enabled: bool
    target_export_percentage: int
    reason: str
    current_price: float | None
    threshold: float
    recovery_threshold: float


class PriceDecisionEngine:
    """Stateful hysteresis decision engine for Growatt export automation."""

    def __init__(
        self,
        config: PriceAutomationConfig,
        initial_mode: AutomationMode = "normal",
    ) -> None:
        config.validate()
        self._config = config
        self._mode: AutomationMode = initial_mode

    @property
    def mode(self) -> AutomationMode:
        """Return the current internal mode."""
        return self._mode

    def reset(self) -> None:
        """Reset the engine to the normal mode."""
        self._mode = "normal"

    def evaluate(self, current_price: float | None) -> DecisionResult:
        """Evaluate the current price and return the desired Growatt state."""
        if not self._config.enabled:
            return self._build_result(
                mode=self._mode,
                changed=False,
                reason="Price automation is disabled",
                current_price=current_price,
            )

        if current_price is None:
            return self._build_result(
                mode=self._mode,
                changed=False,
                reason="No price available",
                current_price=None,
            )

        if self._mode == "triggered":
            if current_price >= self._config.recovery_threshold:
                self._mode = "normal"
                return self._build_result(
                    mode=self._mode,
                    changed=True,
                    reason=(
                        f"Price {current_price:.5f} is above recovery threshold "
                        f"{self._config.recovery_threshold:.5f}"
                    ),
                    current_price=current_price,
                )

            return self._build_result(
                mode=self._mode,
                changed=False,
                reason=(
                    f"Price {current_price:.5f} is still below recovery threshold "
                    f"{self._config.recovery_threshold:.5f}"
                ),
                current_price=current_price,
            )

        if current_price <= self._config.threshold:
            self._mode = "triggered"
            return self._build_result(
                mode=self._mode,
                changed=True,
                reason=(
                    f"Price {current_price:.5f} is at or below threshold "
                    f"{self._config.threshold:.5f}"
                ),
                current_price=current_price,
            )

        return self._build_result(
            mode=self._mode,
            changed=False,
            reason=(
                f"Price {current_price:.5f} is above threshold "
                f"{self._config.threshold:.5f}"
            ),
            current_price=current_price,
        )

    def _build_result(
        self,
        *,
        mode: AutomationMode,
        changed: bool,
        reason: str,
        current_price: float | None,
    ) -> DecisionResult:
        """Build a structured decision result."""
        target_meter_enabled, target_export_percentage = self._targets_for_mode(mode)

        return DecisionResult(
            mode=mode,
            changed=changed,
            target_meter_enabled=target_meter_enabled,
            target_export_percentage=target_export_percentage,
            reason=reason,
            current_price=current_price,
            threshold=self._config.threshold,
            recovery_threshold=self._config.recovery_threshold,
        )

    def _targets_for_mode(self, mode: AutomationMode) -> tuple[bool, int]:
        """Return the target Growatt settings for a given mode."""
        if mode == "triggered":
            return (
                self._config.trigger_meter_enabled,
                self._config.trigger_export_percentage,
            )

        return (
            self._config.normal_meter_enabled,
            self._config.normal_export_percentage,
        )
