"""Coordinator and shared runtime state for Growatt Export Controller."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrowattApiClient, GrowattClientConfig, GrowattCommandResult, GrowattRequestError
from .const import DEFAULT_EXPORT_PERCENTAGE, DEFAULT_SERVICE_METER_ENABLED

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class GrowattControllerState:
    """Mutable controller state exposed to entities."""

    export_percentage: int = DEFAULT_EXPORT_PERCENTAGE
    meter_enabled: bool = DEFAULT_SERVICE_METER_ENABLED
    last_command: str = "idle"
    last_error: str | None = None
    last_http_status: int | None = None
    last_response: str | None = None
    last_login_status: int | None = None
    last_login_response: str | None = None
    last_endpoint: str | None = None
    authenticated: bool = False


class GrowattExportControllerCoordinator(DataUpdateCoordinator[GrowattControllerState]):
    """Shared controller state for all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GrowattApiClient,
        config: GrowattClientConfig,
        name: str,
    ) -> None:
        super().__init__(hass, _LOGGER, name=name, update_interval=timedelta(hours=12))
        self.client = client
        self.config = config
        self._state = GrowattControllerState()
        self.data = self._state

    def _publish_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        self.data = self._state
        self.async_set_updated_data(self._state)

    @staticmethod
    def _error_text(result: GrowattCommandResult) -> str:
        if result.body:
            body = result.body.strip()
            return body if len(body) <= 500 else body[:500] + "..."
        return f"HTTP {result.status}"

    async def _async_update_data(self) -> GrowattControllerState:
        try:
            await self.client.async_login()
            self._publish_state(
                authenticated=True,
                last_login_status=self.client.last_login_status,
                last_login_response=self.client.last_login_body,
                last_error=None,
                last_command="session_check",
            )
            return self._state
        except Exception as exc:  # noqa: BLE001
            self._publish_state(authenticated=False, last_error=str(exc), last_command="session_error")
            raise UpdateFailed(str(exc)) from exc

    async def async_set_export_limit(self, percentage: int, meter_enabled: bool) -> GrowattCommandResult:
        """Send a new export limit to Growatt and update local state."""

        _LOGGER.warning(
            "Coordinator set_export_limit called: percentage=%s meter_enabled=%s",
            percentage,
            meter_enabled,
        )
        try:
            result = await self.client.async_set_export_limit(percentage, meter_enabled)
        except GrowattRequestError as exc:
            self._publish_state(last_error=str(exc), last_command="set_export_limit_failed")
            raise
        except Exception as exc:  # noqa: BLE001
            self._publish_state(last_error=str(exc), last_command="set_export_limit_failed")
            raise

        self._publish_state(
            export_percentage=max(0, min(100, int(percentage))) if result.success else self._state.export_percentage,
            meter_enabled=bool(meter_enabled) if result.success else self._state.meter_enabled,
            last_http_status=result.status,
            last_response=result.body,
            last_endpoint=result.final_url or result.endpoint,
            last_login_status=self.client.last_login_status,
            last_login_response=self.client.last_login_body,
            last_error=None if result.success else self._error_text(result),
            last_command="set_export_limit" if result.success else "set_export_limit_failed",
            authenticated=self.client.authenticated,
        )

        _LOGGER.warning(
            "Coordinator updated local state: export_percentage=%s meter_enabled=%s status=%s endpoint=%s",
            self._state.export_percentage,
            self._state.meter_enabled,
            self._state.last_http_status,
            self._state.last_endpoint,
        )
        return result
