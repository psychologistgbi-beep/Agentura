from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, select

from executive_cli.models import Settings

ALLOWED_SETTING_KEYS: set[str] = {
    "timezone",
    "planning_start",
    "planning_end",
    "lunch_start",
    "lunch_duration_min",
    "min_focus_block_min",
    "buffer_min",
}

_HHMM_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_TIME_KEYS: set[str] = {"planning_start", "planning_end", "lunch_start"}
_NON_NEGATIVE_INT_KEYS: set[str] = {"lunch_duration_min", "buffer_min"}
_POSITIVE_INT_KEYS: set[str] = {"min_focus_block_min"}


def validate_setting(key: str, value: str) -> None:
    if key not in ALLOWED_SETTING_KEYS:
        allowed = ", ".join(sorted(ALLOWED_SETTING_KEYS))
        raise ValueError(f"Unknown setting key: {key}. Allowed keys: {allowed}.")

    if key == "timezone":
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid timezone '{value}'. Expected a valid IANA timezone.") from exc
        return

    if key in _TIME_KEYS:
        if not _HHMM_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid HH:MM value for {key}: '{value}'.")
        return

    if key in _NON_NEGATIVE_INT_KEYS:
        parsed = _parse_int(value, key)
        if parsed < 0:
            raise ValueError(f"Invalid value for {key}: must be an integer >= 0.")
        return

    if key in _POSITIVE_INT_KEYS:
        parsed = _parse_int(value, key)
        if parsed < 1:
            raise ValueError(f"Invalid value for {key}: must be an integer >= 1.")


def _parse_int(value: str, key: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid value for {key}: must be an integer.") from exc


def list_settings(session: Session) -> list[Settings]:
    return session.exec(select(Settings).order_by(Settings.key)).all()


def upsert_setting(session: Session, key: str, value: str) -> Settings:
    validate_setting(key, value)

    setting = session.get(Settings, key)
    if setting is None:
        setting = Settings(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value

    session.commit()
    session.refresh(setting)
    return setting
