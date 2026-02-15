from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timezone

from sqlmodel import SQLModel, Session, create_engine
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.db import get_engine
from executive_cli.models import Task, TaskPriority, TaskStatus
from executive_cli.scrum_metrics import collect_code_quality_snapshot, compute_scrum_metrics
from executive_cli.timeutil import dt_to_db


def _create_engine(tmp_path):
    db_path = tmp_path / "scrum_metrics.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_compute_scrum_metrics_snapshot(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    start_date = date(2026, 2, 17)
    end_date = date(2026, 2, 23)

    with Session(engine) as session:
        # Created before window, still open -> carry-over
        session.add(
            Task(
                title="Carry-over task",
                status=TaskStatus.NEXT,
                priority=TaskPriority.P2,
                estimate_min=45,
                created_at=dt_to_db(datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc)),
                updated_at=dt_to_db(datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc)),
            )
        )
        # Created before window, finished in window
        session.add(
            Task(
                title="Old done task",
                status=TaskStatus.DONE,
                priority=TaskPriority.P1,
                estimate_min=30,
                created_at=dt_to_db(datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc)),
                updated_at=dt_to_db(datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)),
            )
        )
        # Created and finished in window
        session.add(
            Task(
                title="New done task",
                status=TaskStatus.DONE,
                priority=TaskPriority.P2,
                estimate_min=60,
                created_at=dt_to_db(datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)),
                updated_at=dt_to_db(datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc)),
            )
        )
        # Canceled before window (excluded from carry-over denominator)
        session.add(
            Task(
                title="Canceled task",
                status=TaskStatus.CANCELED,
                priority=TaskPriority.P3,
                estimate_min=15,
                created_at=dt_to_db(datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc)),
                updated_at=dt_to_db(datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc)),
            )
        )
        session.commit()

    with Session(engine) as session:
        metrics = compute_scrum_metrics(session, start_date=start_date, end_date=end_date)

    assert metrics.throughput_done_count == 2
    assert metrics.throughput_done_estimate_min == 90
    assert metrics.backlog_at_start_count == 2
    assert metrics.carry_over_count == 1
    assert metrics.carry_over_rate == 0.5
    assert metrics.lead_time_avg_hours is not None
    assert round(metrics.lead_time_avg_hours, 2) == 156.0
    assert metrics.lead_time_p85_hours is not None
    assert 200.0 < metrics.lead_time_p85_hours < 220.0


def test_collect_code_quality_snapshot_parses_coverage(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def _fake_run(command, cwd, capture_output, text, check):
        del cwd, capture_output, text, check
        calls.append(command)
        if "--cov=executive_cli" in command:
            return subprocess.CompletedProcess(command, 0, stdout="Total coverage: 91.23%", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="78 passed", stderr="")

    monkeypatch.setattr("executive_cli.scrum_metrics.subprocess.run", _fake_run)

    snapshot = collect_code_quality_snapshot(project_root=tmp_path)

    assert snapshot.tests_passed is True
    assert snapshot.coverage_gate_passed is True
    assert snapshot.coverage_percent == 91.23
    assert len(calls) == 2


def test_review_scrum_metrics_cli_saves_history(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "metrics_cli.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        session.add(
            Task(
                title="DONE in window",
                status=TaskStatus.DONE,
                priority=TaskPriority.P1,
                estimate_min=40,
                created_at=dt_to_db(datetime(2026, 2, 18, 9, 0, tzinfo=timezone.utc)),
                updated_at=dt_to_db(datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)),
            )
        )
        session.commit()

    result = runner.invoke(
        app,
        [
            "review",
            "scrum-metrics",
            "--start",
            "2026-02-17",
            "--end",
            "2026-02-23",
            "--no-run-quality",
        ],
    )
    assert result.exit_code == 0
    assert "throughput_done_count=1" in result.output
    assert "quality_snapshot=skipped" in result.output

    history_path = db_path.parent / "scrum_metrics_history.json"
    assert history_path.exists()
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["metrics"]["throughput_done_count"] == 1
