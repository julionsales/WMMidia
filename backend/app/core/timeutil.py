"""Datas: tudo é armazenado em UTC; a apresentação usa America/Sao_Paulo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_local(value: datetime | None) -> datetime | None:
    value = ensure_utc(value)
    return value.astimezone(SAO_PAULO) if value else None


def fmt_local(value: datetime | None, with_time: bool = True) -> str:
    local = to_local(value)
    if local is None:
        return "—"
    return local.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def period_bounds(days: int, end: datetime | None = None) -> tuple[datetime, datetime]:
    end = ensure_utc(end) or utcnow()
    return end - timedelta(days=days), end


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
