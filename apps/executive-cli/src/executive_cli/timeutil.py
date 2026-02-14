from __future__ import annotations

from datetime import date, datetime, time
import re
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def parse_date_ymd(s: str) -> date:
    """Parse strict YYYY-MM-DD string into a date. Raises ValueError."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_time_hhmm(s: str) -> time:
    """Parse strict HH:MM string into a time. Raises ValueError."""
    if not re.fullmatch(r"\d{2}:\d{2}", s):
        raise ValueError("Time must match HH:MM")

    hour = int(s[0:2])
    minute = int(s[3:5])

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Hour/minute out of range")

    return time(hour=hour, minute=minute)


def parse_local_dt(s: str, tz: ZoneInfo = MOSCOW_TZ) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' in the provided timezone. Raises ValueError."""
    naive = datetime.strptime(s, "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=tz)


def dt_to_db(dt: datetime) -> str:
    """Convert tz-aware datetime to ISO-8601 string for DB storage."""
    if dt.tzinfo is None:
        raise ValueError("dt_to_db requires a tz-aware datetime")
    return dt.isoformat()


def db_to_dt(s: str) -> datetime:
    """Parse ISO-8601 string from DB into a datetime."""
    return datetime.fromisoformat(s)
