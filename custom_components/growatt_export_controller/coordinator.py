"""Coordinator and price automation for Growatt Export Controller."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    GrowattApiClient,
    GrowattAuthError,
    GrowattClientConfig,
    GrowattCommandResult,
    GrowattRequestError,
)
from .models import (
    GrowattControllerState,
    GrowattControlSettings,
    PriceControlMode,
    PriceStrategy,
)
from .price_control import (
    EconomicPriceUnavailable,
    convert_tax_basis,
    economic_effective_price,
    evaluate_price,
    extract_current_tax_excluded_price,
    normalize_price_to_eur_per_kwh,
    parse_numeric_price,
)

_LOGGER = logging.getLogger(__name__)


class GrowattExportControllerCoordinator(DataUpdateCoordinator[GrowattControllerState]):
    """Coordinate Growatt commands, entities and price-based automation."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GrowattApiClient,
        config: GrowattClientConfig,
        settings: GrowattControlSettings,
        name: str,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=name,
            # The read-only inverter telemetry is refreshed every five minutes.
            # async_login() reuses the existing session and makes no login
            # request while it remains authenticated.
            update_interval=timedelta(minutes=5),
        )
        self.client = client
        self.config = config
        self.settings = settings
        self._state = GrowattControllerState(
            export_percentage=settings.default_export_percentage,
            meter_enabled=settings.default_meter_enabled,
            price_mode=(
                PriceControlMode.NORMAL
                if settings.price_automation_enabled
                else PriceControlMode.DISABLED
            ),
            price_sensor=settings.price_sensor,
        )
        self.data = self._state

        self._command_lock = asyncio.Lock()
        self._price_lock = asyncio.Lock()

        # Beperk geforceerde Growatt-logins tijdens een langdurige cloudstoring.
        self._telemetry_recovery_not_before = 0.0
        self._price_mode = (
            PriceControlMode.NORMAL
            if settings.price_automation_enabled
            else PriceControlMode.DISABLED
        )
        self._price_state_unsub: Any = None
        self._price_time_unsub: Any = None

    def _publish_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        self.data = self._state
        self.async_set_updated_data(self._state)

    @staticmethod
    def _response_text(result: GrowattCommandResult) -> str:
        body = (result.body or "").strip()
        if not body:
            return f"HTTP {result.status}"
        return body if len(body) <= 500 else body[:500] + "..."

    async def _async_update_data(self) -> GrowattControllerState:
        try:
            await self.client.async_login()
        except GrowattAuthError as exc:
            self._publish_state(
                authenticated=False,
                last_error=str(exc),
                last_command="login_failed",
                last_command_at=dt_util.now(),
            )
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except Exception as exc:
            self._publish_state(
                authenticated=False,
                last_error=str(exc),
                last_command="session_error",
                last_command_at=dt_util.now(),
            )
            raise UpdateFailed(str(exc)) from exc

        self._publish_state(
            authenticated=True,
            last_login_status=self.client.last_login_status,
            last_login_response=self.client.last_login_body,
            last_error=None,
            last_command="session_check",
            last_command_at=dt_util.now(),
        )

        # Lees de telemetrie. Bij een sessieprobleem wordt maximaal
        # eenmaal per 15 minuten een nieuwe login plus directe retry gedaan.
        try:
            telemetry = await self.client.async_get_pv_telemetry()
        except (GrowattAuthError, GrowattRequestError) as first_exc:
            recovery_now = asyncio.get_running_loop().time()

            if recovery_now >= self._telemetry_recovery_not_before:
                self._telemetry_recovery_not_before = recovery_now + 900

                _LOGGER.warning(
                    "Growatt PV telemetry read failed; "
                    "rebuilding the session and retrying once: %s",
                    first_exc,
                )

                try:
                    await self.client.async_login(force=True)
                    telemetry = await self.client.async_get_pv_telemetry()
                except (
                    GrowattAuthError,
                    GrowattRequestError,
                ) as retry_exc:
                    error = (
                        f"{first_exc}; retry after fresh login failed: "
                        f"{retry_exc}"
                    )
                    checked_at = dt_util.now()

                    self._publish_state(
                        authenticated=self.client.authenticated,
                        last_error=error,
                        last_command="telemetry_failed",
                        last_command_at=checked_at,
                        telemetry_last_checked_at=checked_at,
                        telemetry_last_error=error,
                    )

                    _LOGGER.error(
                        "Growatt PV telemetry remains unavailable: %s",
                        error,
                    )
                    return self._state
                else:
                    self._telemetry_recovery_not_before = 0.0
                    _LOGGER.info(
                        "Growatt PV telemetry recovered after a fresh login"
                    )
            else:
                error = (
                    f"{first_exc}; automatic session recovery is "
                    "temporarily in cooldown"
                )
                checked_at = dt_util.now()

                self._publish_state(
                    authenticated=self.client.authenticated,
                    last_error=error,
                    last_command="telemetry_failed",
                    last_command_at=checked_at,
                    telemetry_last_checked_at=checked_at,
                    telemetry_last_error=error,
                )

                _LOGGER.warning(
                    "Growatt PV telemetry unavailable: %s",
                    error,
                )
                return self._state

        total_energy = telemetry.energy_total_kwh
        previous_total = self._state.solar_energy_total_kwh
        if previous_total is not None and total_energy < previous_total:
            # Do not publish a backward jump for the Energy dashboard.  Growatt's
            # cumulative eTotal normally only grows; retaining the last good
            # value is safer than corrupting long-term energy statistics.
            _LOGGER.warning(
                "Growatt PV total decreased from %s to %s kWh; keeping last value",
                previous_total,
                total_energy,
            )
            total_energy = previous_total

        self._publish_state(
            solar_power_w=telemetry.power_w,
            solar_energy_today_kwh=telemetry.energy_today_kwh,
            solar_energy_total_kwh=total_energy,
            solar_device_status=telemetry.device_status,
            solar_last_updated=telemetry.last_updated,
            telemetry_last_checked_at=dt_util.now(),
            telemetry_last_error=None,
        )
        return self._state

    async def async_set_export_limit(
        self,
        percentage: int,
        meter_enabled: bool,
        *,
        source: str = "manual",
    ) -> GrowattCommandResult:
        """Send an export-limit command and update optimistic local state."""

        percentage = max(0, min(100, int(percentage)))
        async with self._command_lock:
            _LOGGER.info(
                "Setting Growatt export control from %s: meter_enabled=%s percentage=%s",
                source,
                meter_enabled,
                percentage,
            )
            try:
                result = await self.client.async_set_export_limit(percentage, meter_enabled)
            except Exception as exc:
                self._publish_state(
                    last_error=str(exc),
                    last_command=f"{source}_failed",
                    last_command_at=dt_util.now(),
                    authenticated=self.client.authenticated,
                )
                raise

            if not result.success:
                error = self._response_text(result)
                self._publish_state(
                    last_http_status=result.status,
                    last_response=result.body,
                    last_endpoint=result.final_url or result.endpoint,
                    last_error=error,
                    last_command=f"{source}_failed",
                    last_command_at=dt_util.now(),
                    authenticated=self.client.authenticated,
                )
                raise GrowattRequestError(error)

            self._publish_state(
                export_percentage=percentage,
                meter_enabled=bool(meter_enabled),
                last_http_status=result.status,
                last_response=result.body,
                last_endpoint=result.final_url or result.endpoint,
                last_login_status=self.client.last_login_status,
                last_login_response=self.client.last_login_body,
                last_error=None,
                last_command=source,
                last_command_at=dt_util.now(),
                authenticated=self.client.authenticated,
            )
            return result

    async def async_start_price_watch(self) -> None:
        """Start monitoring the configured electricity-price sensor."""

        self.async_stop_price_watch()

        if not self.settings.price_automation_enabled:
            self._price_mode = PriceControlMode.DISABLED
            self._publish_state(
                price_mode=PriceControlMode.DISABLED,
                price_sensor=self.settings.price_sensor,
                price_reason="Price automation is disabled",
                price_last_error=None,
            )
            return

        if not self.settings.price_sensor:
            self._publish_state(
                price_mode=PriceControlMode.ERROR,
                price_reason="No price sensor configured",
                price_last_error="No price sensor configured",
            )
            return

        entity_id = self.settings.price_sensor
        self._price_mode = PriceControlMode.NORMAL
        self._price_state_unsub = async_track_state_change_event(
            self.hass,
            [entity_id],
            self._async_price_state_changed,
        )
        self._price_time_unsub = async_track_time_interval(
            self.hass,
            self._async_periodic_price_check,
            timedelta(minutes=max(1, self.settings.poll_interval_minutes)),
        )
        _LOGGER.info("Price automation started with %s", entity_id)

        # There is no Growatt readback endpoint in this integration. Applying the
        # desired state once at startup reconciles the inverter with Home Assistant.
        await self.async_refresh_price_control(reason="startup", force_apply=True)

    @callback
    def async_stop_price_watch(self) -> None:
        """Stop price sensor and periodic listeners."""

        if self._price_state_unsub is not None:
            self._price_state_unsub()
            self._price_state_unsub = None
        if self._price_time_unsub is not None:
            self._price_time_unsub()
            self._price_time_unsub = None

    @callback
    def _async_price_state_changed(self, event: Event) -> None:
        """Schedule evaluation when the selected sensor changes."""

        del event
        self.hass.async_create_task(
            self.async_refresh_price_control(reason="price_state_change"),
            "Growatt price state change",
        )

    @callback
    def _async_periodic_price_check(self, now: Any) -> None:
        """Schedule a fallback evaluation at a fixed interval."""

        del now
        self.hass.async_create_task(
            self.async_refresh_price_control(reason="periodic"),
            "Growatt periodic price check",
        )

    def _reapply_due(self) -> bool:
        interval = self.settings.reapply_interval_minutes
        last_applied = self._state.price_last_applied_at
        if interval <= 0 or last_applied is None:
            return False
        return dt_util.now() - last_applied >= timedelta(minutes=interval)

    async def async_refresh_price_control(
        self,
        *,
        reason: str = "manual_evaluation",
        force_apply: bool = False,
    ) -> None:
        """Evaluate the selected sensor and apply the desired Growatt state."""

        async with self._price_lock:
            checked_at = dt_util.now()
            settings = self.settings

            # A Growatt MOD inverter can already be asleep/standby around
            # sunset. Writing tcpSet.do in that state returns
            # inv_set_failure even though nothing is actually wrong.
            #
            # Automatic price-control writes are therefore deferred during
            # twilight/night. The next periodic evaluation after sunrise
            # will automatically apply the then-current desired state.
            sun_state = self.hass.states.get("sun.sun")
            sun_elevation = None

            if sun_state is not None:
                try:
                    sun_elevation = float(
                        sun_state.attributes.get("elevation")
                    )
                except (TypeError, ValueError):
                    pass

            inverter_sleep_window = (
                sun_state is not None
                and (
                    sun_state.state == "below_horizon"
                    or (
                        sun_elevation is not None
                        and sun_elevation <= 2.0
                    )
                )
            )

            if inverter_sleep_window:
                detail = (
                    f"sun elevation {sun_elevation:.1f} deg"
                    if sun_elevation is not None
                    else f"sun state {sun_state.state}"
                )

                self._publish_state(
                    price_mode=PriceControlMode.SLEEPING,
                    price_reason=(
                        f"Deferred ({reason}): "
                        f"inverter sleeping/standby ({detail})"
                    ),
                    price_last_checked_at=checked_at,
                    price_last_error=None,
                    last_error=None,
                )

                _LOGGER.info(
                    "Price control deferred (%s): "
                    "inverter sleeping/standby (%s)",
                    reason,
                    detail,
                )
                return

            if not settings.price_automation_enabled:
                self._price_mode = PriceControlMode.DISABLED
                self._publish_state(
                    price_mode=PriceControlMode.DISABLED,
                    price_reason="Price automation is disabled",
                    price_last_checked_at=checked_at,
                    price_last_error=None,
                )
                return

            entity_id = settings.price_sensor
            if not entity_id:
                self._publish_state(
                    price_mode=PriceControlMode.ERROR,
                    price_reason="No price sensor configured",
                    price_last_checked_at=checked_at,
                    price_last_error="No price sensor configured",
                )
                return

            sensor_state = self.hass.states.get(entity_id)
            if sensor_state is None:
                error = f"Price sensor not found: {entity_id}"
                self._publish_state(
                    price_mode=PriceControlMode.ERROR,
                    price_sensor=entity_id,
                    price_reason=error,
                    price_last_checked_at=checked_at,
                    price_last_error=error,
                )
                return

            raw_price = parse_numeric_price(sensor_state.state)
            if raw_price is None:
                error = f"Price sensor {entity_id} is not numeric: {sensor_state.state}"
                temporarily_unavailable = str(sensor_state.state).strip().lower() in {
                    "", "none", "unknown", "unavailable"
                }
                self._publish_state(
                    price_mode=(PriceControlMode.WAITING if temporarily_unavailable else PriceControlMode.ERROR),
                    price_sensor=entity_id,
                    price_reason=error,
                    price_last_checked_at=checked_at,
                    price_last_error=(None if temporarily_unavailable else error),
                )
                return

            source_unit_value = sensor_state.attributes.get("unit_of_measurement")
            source_unit = str(source_unit_value) if source_unit_value is not None else None
            source_price = normalize_price_to_eur_per_kwh(raw_price, source_unit)
            tax_excluded_price = extract_current_tax_excluded_price(
                sensor_state.attributes,
                now=checked_at,
            )

            try:
                if settings.price_strategy is PriceStrategy.ECONOMIC_AUTO:
                    effective_price, price_basis = economic_effective_price(
                        source_price=source_price,
                        source_includes_tax=settings.sensor_includes_tax,
                        tax_excluded_price=tax_excluded_price,
                        within_saldering_2026=settings.economic_2026_within_saldering,
                        today=checked_at.date(),
                    )
                else:
                    effective_price = convert_tax_basis(
                        source_price,
                        source_includes_tax=settings.sensor_includes_tax,
                        target_includes_tax=settings.threshold_includes_tax,
                        vat_percent=settings.vat_percent,
                        fixed_tax_eur_per_kwh=settings.fixed_tax_eur_per_kwh,
                    )
                    price_basis = (
                        "manual_tax_included"
                        if settings.threshold_includes_tax
                        else "manual_tax_excluded"
                    )
            except EconomicPriceUnavailable as exc:
                error = str(exc)
                waiting_for_price_basis = (
                    settings.sensor_includes_tax
                    and tax_excluded_price is None
                )
                self._publish_state(
                    price_mode=(PriceControlMode.WAITING if waiting_for_price_basis else PriceControlMode.ERROR),
                    price_sensor=entity_id,
                    source_price=source_price,
                    effective_price=None,
                    source_unit=source_unit,
                    tax_excluded_price=tax_excluded_price,
                    price_basis="economic_auto_unavailable",
                    price_reason=error,
                    price_last_checked_at=checked_at,
                    price_last_error=(None if waiting_for_price_basis else error),
                )
                if waiting_for_price_basis:
                    _LOGGER.info("Price control waiting (%s): %s", reason, error)
                else:
                    _LOGGER.warning(
                        "Price automation cannot evaluate (%s): %s", reason, error
                    )
                return

            decision = evaluate_price(
                settings=settings,
                current_mode=self._price_mode,
                effective_price=effective_price,
            )

            local_target_differs = (
                self._state.meter_enabled != decision.meter_enabled
                or self._state.export_percentage != decision.export_percentage
            )
            should_apply = (
                force_apply
                or decision.changed
                or local_target_differs
                or self._reapply_due()
            )

            if not should_apply:
                self._price_mode = decision.mode
                self._publish_state(
                    price_mode=decision.mode,
                    price_sensor=entity_id,
                    source_price=source_price,
                    effective_price=effective_price,
                    source_unit=source_unit,
                    tax_excluded_price=tax_excluded_price,
                    price_basis=price_basis,
                    price_reason=decision.reason,
                    price_last_checked_at=checked_at,
                    price_last_error=None,
                )
                _LOGGER.debug("Price control hold (%s): %s", reason, decision.reason)
                return

            try:
                await self.async_set_export_limit(
                    decision.export_percentage,
                    decision.meter_enabled,
                    source=f"price_control_{decision.mode.value}",
                )
            except Exception as exc:
                self._publish_state(
                    price_mode=PriceControlMode.ERROR,
                    price_sensor=entity_id,
                    source_price=source_price,
                    effective_price=effective_price,
                    source_unit=source_unit,
                    tax_excluded_price=tax_excluded_price,
                    price_basis=price_basis,
                    price_reason=decision.reason,
                    price_last_checked_at=checked_at,
                    price_last_error=str(exc),
                )
                _LOGGER.exception("Price automation failed (%s)", reason)
                return

            self._price_mode = decision.mode
            self._publish_state(
                price_mode=decision.mode,
                price_sensor=entity_id,
                source_price=source_price,
                effective_price=effective_price,
                source_unit=source_unit,
                tax_excluded_price=tax_excluded_price,
                price_basis=price_basis,
                price_reason=decision.reason,
                price_last_checked_at=checked_at,
                price_last_applied_at=dt_util.now(),
                price_last_error=None,
            )
            _LOGGER.info(
                "Price automation applied (%s): mode=%s price=%.5f meter_enabled=%s percentage=%s",
                reason,
                decision.mode.value,
                effective_price,
                decision.meter_enabled,
                decision.export_percentage,
            )
