from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from executive_cli.models import BusyBlock, Calendar
from executive_cli.timeutil import dt_to_db


def _create_engine(tmp_path):
    db_path = tmp_path / "busy_blocks.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _create_calendar(session: Session) -> Calendar:
    calendar = Calendar(slug="primary", name="Primary", timezone="Europe/Moscow")
    session.add(calendar)
    session.commit()
    session.refresh(calendar)
    return calendar


def test_busy_block_interval_constraint_rejects_non_positive_interval(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    tz_plus_3 = timezone(timedelta(hours=3))

    with Session(engine) as session:
        calendar = _create_calendar(session)
        start_dt = datetime(2026, 2, 20, 10, 0, tzinfo=tz_plus_3)
        end_dt = datetime(2026, 2, 20, 10, 0, tzinfo=tz_plus_3)
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(start_dt),
                end_dt=dt_to_db(end_dt),
                title="Invalid block",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_busy_block_interval_constraint_accepts_positive_interval(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    tz_plus_3 = timezone(timedelta(hours=3))
    tz_plus_2 = timezone(timedelta(hours=2))

    with Session(engine) as session:
        calendar = _create_calendar(session)
        start_dt = datetime(2026, 2, 20, 10, 0, tzinfo=tz_plus_3)
        end_dt = datetime(2026, 2, 20, 9, 30, tzinfo=tz_plus_2)
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(start_dt),
                end_dt=dt_to_db(end_dt),
                title="Valid block",
            )
        )
        session.commit()

        blocks = session.exec(select(BusyBlock)).all()
        assert len(blocks) == 1
