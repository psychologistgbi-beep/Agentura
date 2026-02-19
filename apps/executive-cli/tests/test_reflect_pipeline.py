"""Tests for reflect_pipeline.py."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from executive_cli.db import get_engine
from executive_cli.models import PipelineRun
from executive_cli.reflect_pipeline import PIPELINE_NAME, WeeklyReflectResult, run_weekly_reflect

NOW = "2026-02-18T10:00:00+00:00"
WEEK = "2026-W08"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_reflect.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    from typer.testing import CliRunner

    from executive_cli.cli import app as cli_app

    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    engine = get_engine(ensure_directory=True)
    with Session(engine) as session:
        yield session


def test_run_weekly_reflect_empty_db(db_session):
    result = run_weekly_reflect(db_session, week=WEEK, now_iso=NOW)
    assert isinstance(result, WeeklyReflectResult)
    assert result.week == WEEK


def test_run_weekly_reflect_creates_pipeline_run(db_session):
    run_weekly_reflect(db_session, week=WEEK, now_iso=NOW)
    runs = db_session.exec(
        select(PipelineRun).where(PipelineRun.pipeline_name == PIPELINE_NAME)
    ).all()
    assert len(runs) >= 1


def test_run_weekly_reflect_has_suggestions(db_session, monkeypatch):
    # Mock LLM to avoid Ollama dependency in tests
    from executive_cli import reflect_pipeline
    from executive_cli.llm_gateway import LLMResponse

    def mock_call_llm(*args, **kwargs):
        return LLMResponse(
            text='["Review pending tasks"]',
            parsed=["Review pending tasks"],
            provider="ollama",
            model="qwen2.5:7b",
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=100,
        )

    monkeypatch.setattr("executive_cli.reflect_pipeline.call_llm", mock_call_llm)
    result = run_weekly_reflect(db_session, week=WEEK, now_iso=NOW)
    assert len(result.suggestions) >= 1


def test_run_weekly_reflect_report_text(db_session):
    result = run_weekly_reflect(db_session, week=WEEK, now_iso=NOW)
    assert "Weekly Reflect" in result.report_text
    assert WEEK in result.report_text


def test_run_weekly_reflect_idempotent(db_session):
    run_weekly_reflect(db_session, week=WEEK, now_iso=NOW)
    run_weekly_reflect(db_session, week=WEEK, now_iso=NOW)
    # Should not crash — pipeline runs are separate (each call = new run_id)


def test_dash_cli(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from executive_cli.cli import app as cli_app

    db_path = tmp_path / "test_dash.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    result = runner.invoke(cli_app, ["dash"])
    assert result.exit_code == 0
    assert "PIPELINES" in result.output
    assert "LLM GATEWAY" in result.output
    assert "APPROVALS" in result.output


def test_dash_cli_with_since(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from executive_cli.cli import app as cli_app

    db_path = tmp_path / "test_dash_since.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    result = runner.invoke(cli_app, ["dash", "--since", "2026-02-01"])
    assert result.exit_code == 0
    assert "2026-02-01" in result.output


def test_weekly_reflect_result_fields():
    r = WeeklyReflectResult(
        week="2026-W08",
        tasks_done=5,
        tasks_created=10,
        pending_approvals=2,
        llm_calls_this_week=20,
        suggestions=["Do X"],
        report_text="Some text",
    )
    assert r.tasks_done == 5
    assert r.suggestions == ["Do X"]
