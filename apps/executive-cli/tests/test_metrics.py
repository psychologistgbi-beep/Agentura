"""Tests for metrics.py."""
from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session

from executive_cli.db import get_engine
from executive_cli.metrics import approval_stats, llm_stats, pipeline_stats
from executive_cli.models import ApprovalRequest, LLMCallLog, PipelineRun

NOW = "2026-02-18T10:00:00+00:00"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_metrics.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    from typer.testing import CliRunner

    from executive_cli.cli import app as cli_app

    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    engine = get_engine(ensure_directory=True)
    with Session(engine) as session:
        yield session


def test_pipeline_stats_empty(db_session):
    stats = pipeline_stats(db_session)
    assert stats.total_runs == 0
    assert stats.completed == 0
    assert stats.by_pipeline == {}


def test_pipeline_stats_counts(db_session):
    for status in ["completed", "completed", "failed"]:
        db_session.add(PipelineRun(
            pipeline_name="test_pipe",
            status=status,
            correlation_id=uuid.uuid4().hex,
            created_at=NOW,
            updated_at=NOW,
        ))
    db_session.commit()
    stats = pipeline_stats(db_session)
    assert stats.total_runs == 3
    assert stats.completed == 2
    assert stats.failed == 1
    assert stats.by_pipeline["test_pipe"] == 3


def test_llm_stats_empty(db_session):
    stats = llm_stats(db_session)
    assert stats.total_calls == 0
    assert stats.avg_latency_ms is None


def test_llm_stats_counts_providers(db_session):
    for provider in ["ollama", "ollama", "anthropic", "local"]:
        db_session.add(LLMCallLog(
            provider=provider,
            model="test",
            status="ok",
            latency_ms=100,
            prompt_tokens=10,
            completion_tokens=5,
            created_at=NOW,
        ))
    db_session.commit()
    stats = llm_stats(db_session)
    assert stats.total_calls == 4
    assert stats.ollama_calls == 2
    assert stats.anthropic_calls == 1
    assert stats.local_calls == 1
    assert stats.avg_latency_ms == 100.0
    assert stats.total_tokens == 60  # 4 * (10+5)


def test_approval_stats_pending(db_session):
    db_session.add(ApprovalRequest(
        action_type="create_task",
        action_payload_json='{"title":"test"}',
        status="pending",
        created_at=NOW,
    ))
    db_session.commit()
    stats = approval_stats(db_session)
    assert stats.pending == 1


def test_pipeline_stats_since_filter(db_session):
    db_session.add(PipelineRun(
        pipeline_name="old",
        status="completed",
        correlation_id=uuid.uuid4().hex,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    ))
    db_session.commit()
    stats = pipeline_stats(db_session, since_iso="2026-02-01T00:00:00")
    assert stats.total_runs == 0


def test_llm_stats_failed_calls(db_session):
    db_session.add(LLMCallLog(
        provider="ollama",
        model="test",
        status="error",
        latency_ms=50,
        prompt_tokens=5,
        completion_tokens=0,
        created_at=NOW,
    ))
    db_session.commit()
    stats = llm_stats(db_session)
    assert stats.failed_calls == 1
    assert stats.total_calls == 1


def test_pipeline_stats_waiting_approval(db_session):
    db_session.add(PipelineRun(
        pipeline_name="gated_pipe",
        status="waiting_approval",
        correlation_id=uuid.uuid4().hex,
        created_at=NOW,
        updated_at=NOW,
    ))
    db_session.commit()
    stats = pipeline_stats(db_session)
    assert stats.waiting_approval == 1


def test_llm_stats_no_latency(db_session):
    db_session.add(LLMCallLog(
        provider="anthropic",
        model="claude",
        status="success",
        latency_ms=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=NOW,
    ))
    db_session.commit()
    stats = llm_stats(db_session)
    assert stats.avg_latency_ms is None
    assert stats.total_tokens == 0


def test_approval_stats_empty(db_session):
    stats = approval_stats(db_session)
    assert stats.pending == 0
    assert stats.approved_today == 0
    assert stats.rejected_today == 0
