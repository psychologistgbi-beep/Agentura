from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from executive_cli.db import DEFAULT_SETTINGS, PRIMARY_CALENDAR_NAME, PRIMARY_CALENDAR_SLUG
from executive_cli.models import (
    Area,
    Calendar,
    Commitment,
    Project,
    Settings,
    Task,
    TaskPriority,
    TaskStatus,
    WeeklyReview,
)
from executive_cli.review import (
    build_and_persist_weekly_review,
    generate_weekly_review,
    validate_week,
)
from executive_cli.timeutil import MOSCOW_TZ, dt_to_db


def _create_engine(tmp_path):
    db_path = tmp_path / "review_test.sqlite"
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


# Fixed "now" for deterministic tests: 2026-02-16 10:00 MSK (Monday of W08)
_FIXED_NOW = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)  # 10:00 MSK


def test_week_format_validation() -> None:
    # Valid
    assert validate_week("2026-W07") == "2026-W07"
    assert validate_week("2026-W01") == "2026-W01"
    assert validate_week("2026-W53") == "2026-W53"

    # Invalid
    with pytest.raises(ValueError):
        validate_week("2026-07")
    with pytest.raises(ValueError):
        validate_week("2026-W7")
    with pytest.raises(ValueError):
        validate_week("abcd-W01")
    with pytest.raises(ValueError):
        validate_week("2026-W00")
    with pytest.raises(ValueError):
        validate_week("2026-W54")


def test_review_includes_only_now_waiting_in_action_list(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        _seed_defaults(session)
        session.add(Task(
            title="NOW task", status=TaskStatus.NOW,
            priority=TaskPriority.P1, estimate_min=30,
        ))
        session.add(Task(
            title="WAITING task", status=TaskStatus.WAITING,
            priority=TaskPriority.P2, estimate_min=60,
            waiting_on="Bob", ping_at=dt_to_db(_FIXED_NOW),
        ))
        session.add(Task(
            title="NEXT task", status=TaskStatus.NEXT,
            priority=TaskPriority.P1, estimate_min=45,
        ))
        session.add(Task(
            title="DONE task", status=TaskStatus.DONE,
            priority=TaskPriority.P1, estimate_min=15,
        ))
        session.commit()

    with Session(engine) as session:
        body = generate_weekly_review(session, week="2026-W08", now=_FIXED_NOW)

    # Extract the action list section (between header and next ##)
    lines = body.split("\n")
    action_section: list[str] = []
    in_action = False
    for line in lines:
        if line.startswith("## Action list"):
            in_action = True
            continue
        if in_action and line.startswith("## "):
            break
        if in_action and line.startswith("- ["):
            action_section.append(line)

    statuses_in_action = []
    for line in action_section:
        # Extract [STATUS] from line
        start = line.index("[") + 1
        end = line.index("]")
        statuses_in_action.append(line[start:end])

    assert set(statuses_in_action) <= {"NOW", "WAITING"}
    assert "NOW" in statuses_in_action
    assert "WAITING" in statuses_in_action

    # NEXT and DONE must NOT be in action list
    for line in action_section:
        assert "[NEXT]" not in line
        assert "[DONE]" not in line


def test_proposals_include_next(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        _seed_defaults(session)
        for i in range(7):
            session.add(Task(
                title=f"Next task {i}",
                status=TaskStatus.NEXT,
                priority=TaskPriority.P2,
                estimate_min=30,
            ))
        session.commit()

    with Session(engine) as session:
        body = generate_weekly_review(
            session, week="2026-W08", now=_FIXED_NOW, proposals=3,
        )

    lines = body.split("\n")
    proposal_lines: list[str] = []
    in_proposals = False
    for line in lines:
        if line.startswith("## Proposals:"):
            in_proposals = True
            continue
        if in_proposals and line.startswith("## "):
            break
        if in_proposals and line.startswith("- "):
            proposal_lines.append(line)

    # Limit respected
    assert len(proposal_lines) == 3
    # All are NEXT tasks
    for line in proposal_lines:
        assert "Next task" in line


def test_determinism_same_db_same_output(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        _seed_defaults(session)
        session.add(Task(
            title="Alpha", status=TaskStatus.NOW,
            priority=TaskPriority.P1, estimate_min=30,
            due_date=date(2026, 2, 20),
        ))
        session.add(Task(
            title="Beta", status=TaskStatus.NOW,
            priority=TaskPriority.P2, estimate_min=60,
        ))
        session.add(Task(
            title="Gamma", status=TaskStatus.NEXT,
            priority=TaskPriority.P3, estimate_min=45,
        ))
        session.commit()

    with Session(engine) as session:
        body1 = generate_weekly_review(session, week="2026-W08", now=_FIXED_NOW)
    with Session(engine) as session:
        body2 = generate_weekly_review(session, week="2026-W08", now=_FIXED_NOW)

    assert body1 == body2


def test_replace_on_rerun_unique_week(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        _seed_defaults(session)
        session.add(Task(
            title="First task", status=TaskStatus.NOW,
            priority=TaskPriority.P1, estimate_min=30,
        ))
        session.commit()

    # First run
    with Session(engine) as session:
        body1 = build_and_persist_weekly_review(
            session, week="2026-W08", now=_FIXED_NOW,
        )

    # Add another task between runs
    with Session(engine) as session:
        session.add(Task(
            title="Second task", status=TaskStatus.NOW,
            priority=TaskPriority.P2, estimate_min=45,
        ))
        session.commit()

    # Second run (same week)
    with Session(engine) as session:
        body2 = build_and_persist_weekly_review(
            session, week="2026-W08", now=_FIXED_NOW,
        )

    # Exactly 1 row in DB
    with Session(engine) as session:
        reviews = session.exec(
            select(WeeklyReview).where(WeeklyReview.week == "2026-W08")
        ).all()
        assert len(reviews) == 1
        # Content updated (second task now present)
        assert "Second task" in reviews[0].body_md

    # Content differs between runs
    assert body1 != body2
    assert "Second task" not in body1
    assert "Second task" in body2


def test_commitment_off_track_detection(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        _seed_defaults(session)
        # Commitment with NO recent tasks -> off-track
        session.add(Commitment(
            id="YC-1",
            title="Raise investments",
            metric="raise 25M",
            due_date=date(2026, 12, 31),
            difficulty="D3",
        ))
        # Commitment WITH a recent task -> on-track
        session.add(Commitment(
            id="YC-2",
            title="Create art series",
            metric="create and commercialize",
            due_date=date(2026, 12, 31),
            difficulty="D5",
        ))
        session.flush()
        # Task for YC-2 created "now" (within 7 days)
        session.add(Task(
            title="Art sketch",
            status=TaskStatus.NOW,
            priority=TaskPriority.P2,
            estimate_min=60,
            commitment_id="YC-2",
            created_at=dt_to_db(_FIXED_NOW),
        ))
        session.commit()

    with Session(engine) as session:
        body = generate_weekly_review(session, week="2026-W08", now=_FIXED_NOW)

    # YC-1 should appear as off-track
    assert "YC-1" in body
    assert "off-track" in body

    # YC-2 should NOT appear as off-track
    lines = body.split("\n")
    nudge_lines: list[str] = []
    in_nudge = False
    for line in lines:
        if line.startswith("## Commitment nudge"):
            in_nudge = True
            continue
        if in_nudge and line.startswith("## "):
            break
        if in_nudge and line.startswith("- "):
            nudge_lines.append(line)

    nudge_text = "\n".join(nudge_lines)
    assert "YC-1" in nudge_text
    assert "YC-2" not in nudge_text
