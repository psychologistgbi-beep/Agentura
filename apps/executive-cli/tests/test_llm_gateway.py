"""Tests for LLM Gateway (ADR-12)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlmodel import Session, create_engine, SQLModel

from executive_cli.models import LLMCallLog
from executive_cli.llm_gateway import (
    LLMGatewayError,
    LLMResponse,
    _parse_json_response,
    call_llm,
)


@pytest.fixture()
def session():
    """In-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


NOW = "2026-02-17T12:00:00+00:00"


# --- JSON parsing ---

def test_parse_json_plain():
    result = _parse_json_response('[{"title": "test"}]')
    assert isinstance(result, list)
    assert result[0]["title"] == "test"


def test_parse_json_code_fence():
    result = _parse_json_response('```json\n[{"title": "test"}]\n```')
    assert isinstance(result, list)
    assert result[0]["title"] == "test"


def test_parse_json_invalid_returns_none():
    result = _parse_json_response("not json at all")
    assert result is None


# --- Local provider ---

def test_call_local_provider_returns_response(session):
    response = call_llm(
        session,
        prompt="text:\nTODO: Fix the bug in API\nAction: Send report to team",
        provider="local",
        now_iso=NOW,
    )
    assert response.provider == "local"
    assert response.model == "keyword_heuristic"
    # Local extractor should find "TODO" and "Action" keywords
    assert response.text  # non-empty


def test_local_provider_logs_call(session):
    call_llm(
        session,
        prompt="text:\nTODO: something",
        provider="local",
        now_iso=NOW,
    )
    session.flush()

    from sqlmodel import select
    logs = session.exec(select(LLMCallLog)).all()
    assert len(logs) == 1
    assert logs[0].provider == "local"
    assert logs[0].status == "success"


# --- Fallback chain ---

def test_fallback_chain_local_only_when_no_api_key(session):
    """With no OLLAMA_URL and no LLM_API_KEY, should fall back to local."""
    with patch.dict("os.environ", {"OLLAMA_URL": "", "LLM_API_KEY": ""}, clear=False):
        response = call_llm(
            session,
            prompt="text:\nTODO: test task",
            now_iso=NOW,
        )
    assert response.provider == "local"


def test_explicit_unknown_provider_raises(session):
    with pytest.raises(LLMGatewayError, match="Unknown provider"):
        call_llm(
            session,
            prompt="test",
            provider="nonexistent",
            now_iso=NOW,
        )


# --- Ollama provider (mock) ---

def test_ollama_call_mocked(session):
    mock_response = json.dumps({
        "response": '[{"title": "Test task", "confidence": 0.9}]',
        "prompt_eval_count": 50,
        "eval_count": 30,
    }).encode()

    from unittest.mock import MagicMock
    from io import BytesIO

    mock_urlopen = MagicMock()
    mock_urlopen.__enter__ = MagicMock(return_value=BytesIO(mock_response))
    mock_urlopen.__exit__ = MagicMock(return_value=False)

    with patch("executive_cli.llm_gateway.urlopen", return_value=mock_urlopen):
        with patch.dict("os.environ", {"OLLAMA_URL": "http://localhost:11434"}):
            response = call_llm(
                session,
                prompt="Extract tasks",
                provider="ollama",
                model="qwen2.5:7b",
                now_iso=NOW,
            )

    assert response.provider == "ollama"
    assert response.prompt_tokens == 50
    assert response.completion_tokens == 30

    # Check logging
    from sqlmodel import select
    logs = session.exec(select(LLMCallLog)).all()
    assert len(logs) == 1
    assert logs[0].provider == "ollama"
    assert logs[0].status == "success"


# --- Correlation ID ---

def test_correlation_id_propagated_to_log(session):
    call_llm(
        session,
        prompt="text:\nTODO: test",
        provider="local",
        correlation_id="test-corr-123",
        now_iso=NOW,
    )
    session.flush()

    from sqlmodel import select
    logs = session.exec(select(LLMCallLog)).all()
    assert len(logs) == 1
    assert logs[0].correlation_id == "test-corr-123"
