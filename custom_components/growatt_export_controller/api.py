"""Growatt cloud API client for export control."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import aiohttp
from homeassistant.util import dt as dt_util

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
    login_base_url: str = "https://oss.growatt.com"
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
                cookies = self._session.cookie_jar.filter_cookies(base_url)
                cookie_names.update(cookie.key for cookie in cookies.values())
            return ", ".join(sorted(cookie_names)) if cookie_names else "(none)"
        except Exception:  # noqa: BLE001
            return "(unavailable)"

    @staticmethod
    def _payload_snapshot(payload: dict[str, str]) -> dict[str, str]:
        snapshot = dict(payload)
        for key in ("password", "passwordCrc", "devicePassword", "devicePasswordCrc"):
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
        if any(token in lowered for token in failure_tokens):
            return True
        return False

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
        _LOGGER.warning("Growatt %s GET start: url=%s cookies_before=%s", label, url, self._cookie_snapshot())
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
                _LOGGER.warning(
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
        _LOGGER.warning(
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
                _LOGGER.warning(
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

        The browser flow observed in the HAR is:
        1. warm up the server login page,
        2. post to OSS login,
        3. post to the server login endpoint,
        4. then use the authenticated session for tcpSet.do.
        """

        async with self._lock:
            if self._authenticated and not force:
                _LOGGER.debug("Growatt login skipped because session is already authenticated")
                return

            self._authenticated = False
            self._last_login_body = None
            self._last_login_status = None
            self._last_login_url = self._command_url("/login")

            server_login_url = self._command_url("/login")
            oss_login_url = self._login_url("/login")
            server_login_page_url = self._command_url("/login")
            command_index_url = self._command_url("/index")

            _LOGGER.warning(
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
                (
                    oss_login_url,
                    {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                        "Referer": server_login_page_url,
                        "User-Agent": _USER_AGENT,
                    },
                    "oss login page",
                ),
            ]
            for url, headers, label in warmup_requests:
                try:
                    await self._get_text(url, headers=headers, label=label)
                except GrowattRequestError as exc:
                    _LOGGER.warning("Growatt warmup request failed for %s: %s", label, exc)

            login_time = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
            password_crc = self._password_crc()

            oss_variants: list[tuple[str, dict[str, str]]] = [
                (
                    "oss login (noRecord)",
                    {
                        "userName": self._config.username,
                        "password": "",
                        "lang": "en",
                        "loginTime": login_time,
                        "type": "1",
                        "noRecord": "true",
                        "passwordCrc": password_crc,
                    },
                ),
                (
                    "oss login",
                    {
                        "userName": self._config.username,
                        "password": "",
                        "lang": "en",
                        "loginTime": login_time,
                        "type": "1",
                        "passwordCrc": password_crc,
                    },
                ),
            ]
            oss_headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self._login_base().rstrip("/"),
                "Referer": oss_login_url,
                "User-Agent": _USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            }

            for label, payload in oss_variants:
                result = await self._post_text(oss_login_url, payload, headers=oss_headers, label=label)
                self._last_login_status = result.status
                self._last_login_body = result.body
                if self._body_indicates_failure(result.body):
                    _LOGGER.warning("Growatt %s returned a failure body", label)
                else:
                    _LOGGER.warning("Growatt %s completed without a clear failure body", label)

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
                (
                    "server login alt",
                    {
                        "account": self._config.username,
                        "userName": self._config.username,
                        "password": "",
                        "validateCode": "",
                        "isReadPact": "0",
                        "lang": "en",
                        "loginTime": login_time,
                        "type": "1",
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
                    _LOGGER.warning("Growatt %s returned a failure body", label)
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
        _LOGGER.warning(
            "Preparing Growatt export limit payload: percentage=%s meter_enabled=%s payload=%s",
            percentage,
            meter_enabled,
            self._payload_snapshot(payload),
        )

        result = await self._request_with_retry("/tcpSet.do", payload)
        _LOGGER.warning(
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
                    return GrowattCommandResult(
                        success=200 <= (result.status or 0) < 300 and not self._body_indicates_failure(result.body),
                        status=result.status,
                        body=result.body,
                        endpoint=endpoint,
                        relogin_attempted=True,
                        final_url=result.final_url,
                        response_headers=result.response_headers,
                    )

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
        _LOGGER.warning(
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
                _LOGGER.warning(
                    "Growatt POST result: endpoint=%s status=%s final_url=%s history=%s cookies_after=%s content_type=%s body=%s",
                    endpoint,
                    resp.status,
                    str(resp.url),
                    len(resp.history),
                    self._cookie_snapshot(),
                    resp.headers.get("Content-Type"),
                    body_snippet,
                )
                body_failure = self._body_indicates_failure(body)
                return GrowattCommandResult(
                    success=200 <= resp.status < 300 and not body_failure,
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
