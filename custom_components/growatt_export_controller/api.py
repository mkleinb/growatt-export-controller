"""Growatt cloud API client for export control."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import aiohttp
from homeassistant.util import dt as dt_util
from yarl import URL

_LOGGER = logging.getLogger(__name__)


class GrowattAuthError(Exception):
    """Raised when authentication fails."""


class GrowattRequestError(Exception):
    """Raised when a Growatt request fails."""


@dataclass(slots=True)
class GrowattClientConfig:
    """Client configuration for Growatt cloud access."""

    username: str
    password: str
    serial_num: str
    device_password_prefix: str = "growatt"
    command_base_url: str = "https://server.growatt.com"
    login_base_url: str = "https://server.growatt.com"
    timeout: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: int = 2


@dataclass(slots=True)
class GrowattCommandResult:
    """Result of a Growatt command request."""

    success: bool
    status: int | None
    body: str
    endpoint: str
    relogin_attempted: bool = False
    final_url: str | None = None
    response_headers: dict[str, str] | None = None


@dataclass(slots=True)
class GrowattPvTelemetry:
    """Read-only production data reported by the configured inverter."""

    power_w: float
    energy_today_kwh: float
    energy_total_kwh: float
    device_status: str | None
    last_updated: str | None


@dataclass(slots=True)
class _HttpResult:
    """Internal HTTP response representation."""

    status: int | None
    body: str
    final_url: str | None
    history_count: int
    response_headers: dict[str, str]


class GrowattApiClient:
    """Async client for Growatt cloud control endpoints."""

    def __init__(self, session: aiohttp.ClientSession, config: GrowattClientConfig) -> None:
        self._session = session
        self._config = config
        self._authenticated = False
        self._lock = asyncio.Lock()
        self._last_login_body: str | None = None
        self._last_login_status: int | None = None
        self._last_login_url: str | None = None
        self._last_session_recovery_monotonic: float | None = None

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_login_body(self) -> str | None:
        return self._last_login_body

    @property
    def last_login_status(self) -> int | None:
        return self._last_login_status

    @property
    def last_login_url(self) -> str | None:
        return self._last_login_url

    def _command_base(self) -> str:
        return self._config.command_base_url.rstrip("/") + "/"

    def _login_base(self) -> str:
        return self._config.login_base_url.rstrip("/") + "/"

    def _command_url(self, path: str) -> str:
        return urljoin(self._command_base(), path.lstrip("/"))

    def _login_url(self, path: str) -> str:
        return urljoin(self._login_base(), path.lstrip("/"))

    def _password_crc(self) -> str:
        return hashlib.md5(self._config.password.encode("utf-8")).hexdigest()

    @staticmethod
    def _truncate(value: str | None, limit: int = 1200) -> str | None:
        if value is None:
            return None
        clean = " ".join(value.split())
        return clean if len(clean) <= limit else clean[:limit] + "..."

    def _cookie_snapshot(self) -> str:
        """Return a compact snapshot of cookie names for both domains."""

        try:
            cookie_names: set[str] = set()
            for base_url in (self._command_base(), self._login_base()):
                cookies = self._session.cookie_jar.filter_cookies(URL(base_url))
                cookie_names.update(cookie.key for cookie in cookies.values())
            return ", ".join(sorted(cookie_names)) if cookie_names else "(none)"
        except Exception:
            return "(unavailable)"

    @staticmethod
    def _payload_snapshot(payload: dict[str, str]) -> dict[str, str]:
        snapshot = dict(payload)
        for key in (
            "password",
            "passwordCrc",
            "devicePassword",
            "devicePasswordCrc",
            "account",
            "userName",
        ):
            if key in snapshot and snapshot[key]:
                snapshot[key] = "<md5:{} chars>".format(len(snapshot[key])) if key.lower().endswith("crc") else "<redacted>"
        return snapshot

    @staticmethod
    def _body_indicates_failure(body: str) -> bool:
        lowered = body.lower().replace(" ", "")
        failure_tokens = (
            '"success":false',
            "'success':false",
            '"result":-2',
            "result:-2",
            "inv_set_failure",
            "setparameterfailure",
            "logininvalid",
            "loginfailed",
            "sessioninvalid",
            "please-loginagain",
            "wrongpassword",
            "passworderror",
            "accounterror",
            "usernotexist",
            "unauthorized",
            "denied",
            "notallowed",
        )
        return any(token in lowered for token in failure_tokens)

    @staticmethod
    def _body_indicates_success(body: str) -> bool:
        lowered = body.lower().replace(" ", "")
        success_tokens = (
            '"success":true',
            "'success':true",
            '"result":0',
            "result:0",
            "inv_set_success",
            "saved",
            "done",
            "accepted",
            "ok",
        )
        return any(token in lowered for token in success_tokens)

    @staticmethod
    def _body_indicates_command_success(body: str) -> bool:
        """Return whether tcpSet.do explicitly accepted the command."""

        lowered = body.lower().replace(" ", "")
        return (
            '"success":true' in lowered
            or "'success':true" in lowered
            or "inv_set_success" in lowered
        )

    def _request_timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=self._config.timeout)

    async def _get_text(
        self,
        url: str,
        *,
        headers: dict[str, str],
        label: str,
        allow_redirects: bool = True,
    ) -> _HttpResult:
        _LOGGER.debug("Growatt %s GET start: url=%s cookies_before=%s", label, url, self._cookie_snapshot())
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=self._request_timeout(),
                allow_redirects=allow_redirects,
            ) as resp:
                body = await resp.text()
                result = _HttpResult(
                    status=resp.status,
                    body=body,
                    final_url=str(resp.url),
                    history_count=len(resp.history),
                    response_headers={
                        key: value
                        for key, value in resp.headers.items()
                        if key.lower() in {"content-type", "location", "server"}
                    },
                )
                _LOGGER.debug(
                    "Growatt %s GET result: status=%s final_url=%s history=%s cookies_after=%s content_type=%s body=%s",
                    label,
                    result.status,
                    result.final_url,
                    result.history_count,
                    self._cookie_snapshot(),
                    resp.headers.get("Content-Type"),
                    self._truncate(result.body),
                )
                return result
        except asyncio.TimeoutError as exc:
            raise GrowattRequestError(f"GET request timed out calling {url}") from exc
        except aiohttp.ClientError as exc:
            raise GrowattRequestError(f"GET request failed calling {url}: {exc}") from exc

    async def _post_text(
        self,
        url: str,
        payload: dict[str, str],
        *,
        headers: dict[str, str],
        label: str,
        allow_redirects: bool = True,
    ) -> _HttpResult:
        _LOGGER.debug(
            "Growatt %s POST start: endpoint=%s cookies_before=%s payload=%s",
            label,
            url,
            self._cookie_snapshot(),
            self._payload_snapshot(payload),
        )
        try:
            async with self._session.post(
                url,
                data=payload,
                headers=headers,
                timeout=self._request_timeout(),
                allow_redirects=allow_redirects,
            ) as resp:
                body = await resp.text()
                result = _HttpResult(
                    status=resp.status,
                    body=body,
                    final_url=str(resp.url),
                    history_count=len(resp.history),
                    response_headers={
                        key: value
                        for key, value in resp.headers.items()
                        if key.lower() in {"content-type", "location", "server"}
                    },
                )
                _LOGGER.debug(
                    "Growatt %s POST result: status=%s final_url=%s history=%s cookies_after=%s content_type=%s body=%s",
                    label,
                    result.status,
                    result.final_url,
                    result.history_count,
                    self._cookie_snapshot(),
                    resp.headers.get("Content-Type"),
                    self._truncate(result.body),
                )
                return result
        except asyncio.TimeoutError as exc:
            raise GrowattRequestError(f"POST request timed out calling {url}") from exc
        except aiohttp.ClientError as exc:
            raise GrowattRequestError(f"POST request failed calling {url}: {exc}") from exc

    async def async_login(self, force: bool = False) -> None:
        """Authenticate against the Growatt web flow.

        The browser flow warms up the server login page, performs one direct
        server login, and then reuses that authenticated session.  In
        particular, this integration does not use oss.growatt.com.
        """

        async with self._lock:
            if self._authenticated and not force:
                cookies = self._session.cookie_jar.filter_cookies(
                    URL(self._command_base())
                )
                plant_cookie = cookies.get("onePlantId")

                if (
                    plant_cookie is not None
                    and plant_cookie.value
                ):
                    self._last_session_recovery_monotonic = None
                    _LOGGER.debug(
                        "Growatt login skipped because session "
                        "is already authenticated"
                    )
                    return

                recovery_now = (
                    asyncio.get_running_loop().time()
                )
                last_recovery = (
                    self._last_session_recovery_monotonic
                )

                if (
                    last_recovery is not None
                    and recovery_now - last_recovery < 900
                ):
                    _LOGGER.debug(
                        "Growatt session recovery skipped "
                        "during 15-minute cooldown"
                    )
                    return

                self._last_session_recovery_monotonic = (
                    recovery_now
                )
                _LOGGER.warning(
                    "Growatt session has lost onePlantId; "
                    "rebuilding authenticated session"
                )
                force = True

            self._authenticated = False
            self._last_login_body = None
            self._last_login_status = None
            self._last_login_url = self._command_url("/login")

            server_login_url = self._command_url("/login")
            server_login_page_url = self._command_url("/login")
            command_index_url = self._command_url("/index")

            _LOGGER.debug(
                "Growatt login start: url=%s force=%s cookies_before=%s",
                server_login_url,
                force,
                self._cookie_snapshot(),
            )

            # Best-effort warm-up requests mirror the browser flow and seed cookies.
            warmup_requests = [
                (
                    server_login_page_url,
                    {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                        "Referer": self._command_base(),
                        "User-Agent": _USER_AGENT,
                    },
                    "login bootstrap",
                ),
                (
                    self._command_url("/login/getCustomerCase"),
                    {
                        "Accept": "*/*",
                        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                        "Referer": server_login_page_url,
                        "X-Requested-With": "XMLHttpRequest",
                        "User-Agent": _USER_AGENT,
                    },
                    "customer case",
                ),
                (
                    self._command_url("/v3/js/login/data.json"),
                    {
                        "Accept": "*/*",
                        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                        "Referer": server_login_page_url,
                        "X-Requested-With": "XMLHttpRequest",
                        "User-Agent": _USER_AGENT,
                    },
                    "login data",
                ),
                (
                    self._command_url("/lang/language_en.properties"),
                    {
                        "Accept": "text/plain, */*; q=0.01",
                        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                        "Referer": server_login_page_url,
                        "X-Requested-With": "XMLHttpRequest",
                        "User-Agent": _USER_AGENT,
                    },
                    "language pack",
                ),
            ]
            for url, headers, label in warmup_requests:
                try:
                    await self._get_text(url, headers=headers, label=label)
                except GrowattRequestError as exc:
                    _LOGGER.debug("Growatt warmup request failed for %s: %s", label, exc)

            login_time = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
            password_crc = self._password_crc()


            server_variants: list[tuple[str, dict[str, str]]] = [
                (
                    "server login",
                    {
                        "account": self._config.username,
                        "password": "",
                        "validateCode": "",
                        "isReadPact": "0",
                        "passwordCrc": password_crc,
                    },
                ),
            ]

            server_headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self._command_base().rstrip("/"),
                "Referer": server_login_page_url,
                "User-Agent": _USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            }

            last_server_result: _HttpResult | None = None
            for label, payload in server_variants:
                result = await self._post_text(server_login_url, payload, headers=server_headers, label=label)
                last_server_result = result
                self._last_login_status = result.status
                self._last_login_body = result.body
                if result.status is None or result.status >= 400:
                    continue
                if self._body_indicates_failure(result.body):
                    _LOGGER.debug("Growatt %s returned a failure body", label)
                    continue
                if result.final_url and result.final_url.rstrip("/") == server_login_url.rstrip("/"):
                    # A non-failing response on the server login URL is what we need.
                    self._authenticated = True
                    break
                self._authenticated = True
                break

            if not self._authenticated:
                snippet = self._truncate(last_server_result.body if last_server_result else None)
                raise GrowattAuthError(
                    f"Login response indicates failure (HTTP {self._last_login_status}): {snippet}"
                )

            # One final touch: load the index page after authentication to mirror the browser.
            try:
                await self._get_text(
                    command_index_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                        "Referer": server_login_page_url,
                        "User-Agent": _USER_AGENT,
                    },
                    label="index warmup",
                )
            except GrowattRequestError as exc:
                _LOGGER.warning("Growatt index warmup failed after login: %s", exc)

    @staticmethod
    def _numeric_value(value: object, field: str) -> float:
        """Convert a Growatt numeric field without silently accepting bad data."""

        if value is None:
            raise GrowattRequestError(f"Growatt response did not contain {field}")
        try:
            return float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise GrowattRequestError(
                f"Growatt response has an invalid {field} value"
            ) from exc

    async def async_get_pv_telemetry(self) -> GrowattPvTelemetry:
        """Read the freshest available PV telemetry without logging in again."""

        if not self._authenticated:
            raise GrowattAuthError(
                "No authenticated Growatt session is available"
            )

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
            "Referer": self._command_url("/index"),
            "User-Agent": _USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        }

        def find_value(
            value: object,
            *names: str,
        ) -> object | None:
            wanted = {
                "".join(
                    character
                    for character in name.casefold()
                    if character.isalnum()
                )
                for name in names
            }

            if isinstance(value, dict):
                for key, child in value.items():
                    normalized = "".join(
                        character
                        for character in str(key).casefold()
                        if character.isalnum()
                    )
                    if (
                        normalized in wanted
                        and child not in (None, "")
                    ):
                        return child

                for child in value.values():
                    found = find_value(child, *names)
                    if found not in (None, ""):
                        return found

            elif isinstance(value, list):
                for child in value:
                    found = find_value(child, *names)
                    if found not in (None, ""):
                        return found

            return None

        def numeric(
            value: object,
            field: str,
            *,
            power: bool = False,
        ) -> float:
            if isinstance(value, dict):
                value = value.get("value")

            text = str(value or "").strip().replace(",", ".")
            number_text = "".join(
                character
                for character in text
                if character in "0123456789.-"
            )

            if not number_text:
                raise GrowattRequestError(
                    f"Growatt live response did not contain {field}"
                )

            try:
                result = float(number_text)
            except ValueError as exc:
                raise GrowattRequestError(
                    f"Growatt live response has an invalid {field} value"
                ) from exc

            if (
                power
                and "kw" in text.casefold()
                and "kwh" not in text.casefold()
            ):
                result *= 1000.0

            return result

        live_requests = (
            (
                "TLX detail",
                str(
                    URL(
                        self._command_url("/newTlxApi.do")
                    ).with_query(
                        {
                            "op": "getTlxDetailData",
                            "id": self._config.serial_num,
                        }
                    )
                ),
            ),
            (
                "inverter detail",
                str(
                    URL(
                        self._command_url("/newInverterAPI.do")
                    ).with_query(
                        {
                            "op": "getInverterDetailData",
                            "inverterId": self._config.serial_num,
                        }
                    )
                ),
            ),
            (
                "inverter detail alternative",
                str(
                    URL(
                        self._command_url("/newInverterAPI.do")
                    ).with_query(
                        {
                            "op": "getInverterDetailData_two",
                            "inverterId": self._config.serial_num,
                        }
                    )
                ),
            ),
        )

        live_errors: list[str] = []

        for label, endpoint in live_requests:
            try:
                result = await self._get_text(
                    endpoint,
                    headers=headers,
                    label=f"PV telemetry {label}",
                )

                if (
                    result.status is None
                    or not 200 <= result.status < 300
                ):
                    raise GrowattRequestError(
                        f"HTTP {result.status}"
                    )

                if self._body_indicates_failure(result.body):
                    raise GrowattRequestError(
                        "request rejected"
                    )

                payload = json.loads(result.body)
                root = (
                    payload.get("obj", payload)
                    if isinstance(payload, dict)
                    else payload
                )

                power_value = find_value(
                    root,
                    "pac",
                    "pAc",
                    "outputPower",
                    "powerValue",
                )
                today_value = find_value(
                    root,
                    "eToday",
                    "todayEnergy",
                    "todayGenerateEnergy",
                )
                total_value = find_value(
                    root,
                    "eTotal",
                    "totalEnergy",
                    "totalGenerateEnergy",
                )

                power_w = numeric(
                    power_value,
                    "power",
                    power=True,
                )
                energy_today_kwh = numeric(
                    today_value,
                    "energy today",
                )
                energy_total_kwh = numeric(
                    total_value,
                    "energy total",
                )

                if (
                    power_w < 0
                    or energy_today_kwh < 0
                    or energy_total_kwh < energy_today_kwh
                ):
                    raise GrowattRequestError(
                        "implausible live telemetry values"
                    )

                status = find_value(
                    root,
                    "status",
                    "deviceStatus",
                    "runStatus",
                )
                updated = find_value(
                    root,
                    "lastUpdateTime",
                    "lastUpdated",
                    "updateTime",
                )

                _LOGGER.debug(
                    "Growatt PV telemetry source selected: %s",
                    label,
                )

                return GrowattPvTelemetry(
                    power_w=power_w,
                    energy_today_kwh=energy_today_kwh,
                    energy_total_kwh=energy_total_kwh,
                    device_status=(
                        str(status)
                        if status is not None
                        else None
                    ),
                    last_updated=(
                        str(updated)
                        if updated is not None
                        else None
                    ),
                )

            except (
                GrowattRequestError,
                TypeError,
                ValueError,
                KeyError,
                json.JSONDecodeError,
            ) as exc:
                live_errors.append(f"{label}: {exc}")

        _LOGGER.debug(
            "Growatt live PV endpoints unavailable; "
            "using device-list fallback: %s",
            "; ".join(live_errors),
        )

        cookies = self._session.cookie_jar.filter_cookies(
            URL(self._command_base())
        )
        plant_cookie = cookies.get("onePlantId")

        if plant_cookie is None or not plant_cookie.value:
            raise GrowattRequestError(
                "Growatt session does not contain a plant ID"
            )

        endpoint = self._command_url(
            "/panel/getDevicesByPlantList"
        )
        result = await self._post_text(
            endpoint,
            {
                "currPage": "1",
                "plantId": plant_cookie.value,
            },
            headers={
                **headers,
                "Content-Type": (
                    "application/x-www-form-urlencoded; "
                    "charset=UTF-8"
                ),
                "Origin": self._command_base().rstrip("/"),
            },
            label="PV telemetry fallback",
        )

        if (
            result.status is None
            or not 200 <= result.status < 300
        ):
            raise GrowattRequestError(
                f"Growatt PV telemetry returned HTTP "
                f"{result.status}"
            )

        if self._body_indicates_failure(result.body):
            raise GrowattRequestError(
                "Growatt rejected the PV telemetry request"
            )

        try:
            payload = json.loads(result.body)
            devices = payload["obj"]["datas"]
        except (
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            raise GrowattRequestError(
                "Growatt returned no readable PV telemetry"
            ) from exc

        matching_devices = [
            device
            for device in devices
            if str(
                device.get("deviceSn")
                or device.get("serialNum")
                or ""
            ) == self._config.serial_num
        ]

        if len(matching_devices) == 1:
            device = matching_devices[0]
        elif (
            len(devices) == 1
            and isinstance(devices[0], dict)
        ):
            device = devices[0]
        else:
            raise GrowattRequestError(
                "Growatt PV telemetry did not contain "
                "the configured inverter"
            )

        return GrowattPvTelemetry(
            power_w=self._numeric_value(
                device.get("pac"),
                "pac",
            ),
            energy_today_kwh=self._numeric_value(
                device.get("eToday"),
                "eToday",
            ),
            energy_total_kwh=self._numeric_value(
                device.get("eTotal"),
                "eTotal",
            ),
            device_status=(
                str(device["status"])
                if device.get("status") is not None
                else None
            ),
            last_updated=(
                str(device["lastUpdateTime"])
                if device.get("lastUpdateTime") is not None
                else None
            ),
        )


    async def async_set_export_limit(self, percentage: int, meter_enabled: bool) -> GrowattCommandResult:
        """Set the Growatt backflow/export limit."""

        percentage = max(0, min(100, int(percentage)))
        payload = {
            "action": "maxSet",
            "serialNum": self._config.serial_num,
            "type": "backflow_setting",
            "param1": "1" if meter_enabled else "0",
            "param2": str(percentage),
            "param3": "0",
        }
        _LOGGER.debug(
            "Preparing Growatt export limit payload: percentage=%s "
            "meter_enabled=%s payload=%s",
            percentage,
            meter_enabled,
            self._payload_snapshot(payload),
        )

        result = await self._request_with_retry("/tcpSet.do", payload)
        _LOGGER.info(
            "Growatt export limit request finished: success=%s status=%s relogin=%s final_url=%s",
            result.success,
            result.status,
            result.relogin_attempted,
            result.final_url,
        )
        return result

    async def _request_with_retry(self, path: str, payload: dict[str, str]) -> GrowattCommandResult:
        last_error: Exception | None = None
        endpoint = self._command_url(path)

        for attempt in range(1, self._config.retry_attempts + 1):
            try:
                if not self._authenticated:
                    await self.async_login()

                result = await self._post(endpoint, payload)
                if self._should_relogin(result):
                    _LOGGER.warning("Growatt session appears stale; relogging in and retrying once")
                    await self.async_login(force=True)
                    result = await self._post(endpoint, payload)
                    retry_result = GrowattCommandResult(
                        success=(
                            200 <= (result.status or 0) < 300
                            and self._body_indicates_command_success(result.body)
                        ),
                        status=result.status,
                        body=result.body,
                        endpoint=endpoint,
                        relogin_attempted=True,
                        final_url=result.final_url,
                        response_headers=result.response_headers,
                    )
                    if not retry_result.success:
                        raise GrowattRequestError(
                            "Growatt rejected the command after re-login "
                            f"(HTTP {retry_result.status}): {self._truncate(retry_result.body, 300)}"
                        )
                    return retry_result

                if not result.success:
                    raise GrowattRequestError(
                        f"Growatt returned HTTP {result.status} for {endpoint}: {self._truncate(result.body, 300)}"
                    )
                return result
            except (GrowattAuthError, GrowattRequestError, asyncio.TimeoutError, aiohttp.ClientError) as exc:
                last_error = exc
                _LOGGER.warning(
                    "Growatt request attempt %s/%s failed for %s: %s",
                    attempt,
                    self._config.retry_attempts,
                    endpoint,
                    exc,
                )
                if attempt < self._config.retry_attempts:
                    await asyncio.sleep(self._config.retry_backoff_seconds * attempt)

        raise GrowattRequestError(f"Failed to call {path}: {last_error}")

    async def _post(self, endpoint: str, payload: dict[str, str]) -> GrowattCommandResult:
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self._command_base().rstrip("/"),
            "Referer": self._command_base(),
            "User-Agent": _USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        }
        _LOGGER.debug(
            "Growatt POST start: endpoint=%s cookies_before=%s payload=%s",
            endpoint,
            self._cookie_snapshot(),
            self._payload_snapshot(payload),
        )
        try:
            async with self._session.post(
                endpoint,
                data=payload,
                headers=headers,
                timeout=self._request_timeout(),
                allow_redirects=True,
            ) as resp:
                body = await resp.text()
                body_snippet = self._truncate(body)
                _LOGGER.debug(
                    "Growatt POST result: endpoint=%s status=%s final_url=%s history=%s cookies_after=%s content_type=%s body=%s",
                    endpoint,
                    resp.status,
                    str(resp.url),
                    len(resp.history),
                    self._cookie_snapshot(),
                    resp.headers.get("Content-Type"),
                    body_snippet,
                )
                return GrowattCommandResult(
                    success=(
                        200 <= resp.status < 300
                        and self._body_indicates_command_success(body)
                    ),
                    status=resp.status,
                    body=body,
                    endpoint=endpoint,
                    final_url=str(resp.url),
                    response_headers={
                        key: value
                        for key, value in resp.headers.items()
                        if key.lower() in {"content-type", "location", "server"}
                    },
                )
        except asyncio.TimeoutError as exc:
            raise GrowattRequestError(f"Request timed out calling {endpoint}") from exc
        except aiohttp.ClientError as exc:
            raise GrowattRequestError(f"Request failed calling {endpoint}: {exc}") from exc

    @staticmethod
    def _should_relogin(result: GrowattCommandResult) -> bool:
        if result.status in (401, 403):
            return True
        body = (result.body or "").lower()
        return any(
            token in body
            for token in (
                "login invalid",
                "login",
                "session",
                "timeout",
                "expired",
                "please sign in",
                "unauthorized",
            )
        ) and not result.success


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
