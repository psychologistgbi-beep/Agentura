from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def parse_date_ymd(s: str) -> date:
    """Parse strict YYYY-MM-DD string into a date. Raises ValueError."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_time_hhmm(s: str) -> time:
    """Parse strict HH:MM string into a time. Raises ValueError."""
    return datetime.strptime(s, "%H:%M").time()


def parse_local_dt(s: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' as Europe/Moscow tz-aware datetime. Raises ValueError."""
    naive = datetime.strptime(s, "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=MOSCOW_TZ)


def dt_to_db(dt: datetime) -> str:
    """Convert tz-aware datetime to ISO-8601 string for DB storage."""
    if dt.tzinfo is None:
        raise ValueError("dt_to_db requires a tz-aware datetime")
    return dt.isoformat()


def db_to_dt(s: str) -> datetime:
    """Parse ISO-8601 string from DB into a datetime."""
    return datetime.fromisoformat(s)
