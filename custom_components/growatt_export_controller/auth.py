"""Auth helpers for Growatt Export Controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import md5


def md5_hex(value: str) -> str:
    """Return an MD5 hex digest."""
    return md5(value.encode("utf-8")).hexdigest()


def build_device_password(prefix: str, on_date: date | None = None) -> str:
    """Build the daily inverter password."""
    on_date = on_date or date.today()
    return f"{prefix}{on_date:%Y%m%d}"


@dataclass(slots=True, frozen=True)
class GrowattLoginConfig:
    """Normalized login config used by the API layer."""

    username: str
    password: str
    login_url: str
    command_url: str
    inverter_serial: str
    device_password_prefix: str
