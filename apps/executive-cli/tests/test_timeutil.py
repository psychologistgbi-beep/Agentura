from datetime import datetime, time

from executive_cli.timeutil import MOSCOW_TZ, db_to_dt, dt_to_db, parse_time_hhmm


def test_datetime_roundtrip_preserves_value() -> None:
    original = datetime(2024, 5, 17, 9, 30, tzinfo=MOSCOW_TZ)

    as_db = dt_to_db(original)
    restored = db_to_dt(as_db)

    assert restored == original
    assert restored.isoformat() == original.isoformat()


def test_parse_time_hhmm_allows_single_digit_hours() -> None:
    assert parse_time_hhmm("07:00") == time(7, 0)
    assert parse_time_hhmm("7:00") == time(7, 0)
