from datetime import date, datetime

from sqlmodel import Session, SQLModel, create_engine, select

from executive_cli.db import DEFAULT_SETTINGS, PRIMARY_CALENDAR_NAME, PRIMARY_CALENDAR_SLUG
from executive_cli.models import BusyBlock, Calendar, DayPlan, Settings, Task, TaskPriority, TaskStatus, TimeBlock
from executive_cli.planner import build_and_persist_day_plan
from executive_cli.timeutil import MOSCOW_TZ, dt_to_db


def _create_engine(tmp_path):
    db_path = tmp_path / "planner.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_defaults(session: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        session.add(Settings(key=key, value=value))

    session.add(
        Calendar(
            slug=PRIMARY_CALENDAR_SLUG,
            name=PRIMARY_CALENDAR_NAME,
            timezone=DEFAULT_SETTINGS["timezone"],
        )
    )
    session.commit()


def _signature(result) -> list[tuple[str, str, str, str, int | None]]:
    return [
        (
            block.start_dt.isoformat(),
            block.end_dt.isoformat(),
            block.type,
            block.label,
            block.task_id,
        )
        for block in result.blocks
    ]


def test_day_plan_is_deterministic_and_replaces_existing(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    plan_date = date(2026, 2, 20)

    with Session(engine) as session:
        _seed_defaults(session)
        calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).first()
        assert calendar is not None

        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 10, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 11, 0, tzinfo=MOSCOW_TZ)),
                title="Meet A",
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 10, 30, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 12, 0, tzinfo=MOSCOW_TZ)),
                title="Meet B",
            )
        )
        session.add(
            Task(
                title="Task A",
                status=TaskStatus.NOW,
                priority=TaskPriority.P2,
                estimate_min=30,
            )
        )
        session.add(
            Task(
                title="Task B",
                status=TaskStatus.NOW,
                priority=TaskPriority.P1,
                estimate_min=60,
                due_date=date(2026, 3, 1),
            )
        )
        session.commit()

    with Session(engine) as session:
        first_result = build_and_persist_day_plan(session, plan_date=plan_date, variant="realistic")
    with Session(engine) as session:
        second_result = build_and_persist_day_plan(session, plan_date=plan_date, variant="realistic")

        plans = session.exec(
            select(DayPlan).where(DayPlan.date == plan_date).where(DayPlan.variant == "realistic")
        ).all()
        blocks = session.exec(select(TimeBlock)).all()

    assert _signature(first_result) == _signature(second_result)
    assert len(plans) == 1
    assert len(blocks) == len(second_result.blocks)


def test_lunch_picks_earlier_slot_on_equal_distance(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    plan_date = date(2026, 2, 20)

    with Session(engine) as session:
        _seed_defaults(session)
        session.get(Settings, "planning_start").value = "09:00"
        session.get(Settings, "planning_end").value = "17:00"
        session.get(Settings, "lunch_start").value = "12:00"
        session.get(Settings, "lunch_duration_min").value = "60"
        session.get(Settings, "buffer_min").value = "0"

        calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).first()
        assert calendar is not None
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 11, 30, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 13, 30, tzinfo=MOSCOW_TZ)),
                title="Middle busy",
            )
        )
        session.commit()

    with Session(engine) as session:
        result = build_and_persist_day_plan(session, plan_date=plan_date, variant="minimal")

    lunch_blocks = [block for block in result.blocks if block.type == "lunch"]
    assert len(lunch_blocks) == 1
    assert lunch_blocks[0].start_dt.strftime("%H:%M") == "10:30"
    assert lunch_blocks[0].end_dt.strftime("%H:%M") == "11:30"


def test_plan_uses_only_now(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    plan_date = date(2026, 2, 20)

    with Session(engine) as session:
        _seed_defaults(session)
        session.add(
            Task(
                title="NEXT only task",
                status=TaskStatus.NEXT,
                priority=TaskPriority.P1,
                estimate_min=30,
            )
        )
        session.commit()

    with Session(engine) as session:
        result = build_and_persist_day_plan(session, plan_date=plan_date, variant="realistic")

    assert result.selected_tasks == []
    assert result.didnt_fit_tasks == []
    assert [block for block in result.blocks if block.type == "focus"] == []
    assert result.no_now_hint_text == "No NOW tasks. Move NEXT -> NOW via execas task move <id> --status NOW."


def test_plan_with_now_picks_now(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    plan_date = date(2026, 2, 20)

    with Session(engine) as session:
        _seed_defaults(session)
        session.add(
            Task(
                title="NOW task",
                status=TaskStatus.NOW,
                priority=TaskPriority.P1,
                estimate_min=30,
            )
        )
        session.commit()

    with Session(engine) as session:
        result = build_and_persist_day_plan(session, plan_date=plan_date, variant="realistic")

    assert [task.title for task in result.selected_tasks] == ["NOW task"]
    assert result.no_now_hint_text is None


def test_no_now_prints_hint(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    plan_date = date(2026, 2, 20)

    with Session(engine) as session:
        _seed_defaults(session)

    with Session(engine) as session:
        result = build_and_persist_day_plan(session, plan_date=plan_date, variant="realistic")

    assert result.selected_tasks == []
    assert result.didnt_fit_tasks == []
    assert result.no_now_hint_text == "No NOW tasks. Move NEXT -> NOW via execas task move <id> --status NOW."
