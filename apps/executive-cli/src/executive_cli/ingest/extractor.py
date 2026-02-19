from __future__ import annotations

import json
from typing import Any

from executive_cli.ingest.types import ExtractedCandidate
from executive_cli.llm.client import LLMClientError, LLMConfig, extract_candidates_with_llm


def extract_candidates(
    *,
    raw_text: str,
    source_channel: str,
    context: dict[str, str],
    provider: str,
    model: str,
    temperature: float,
    session: Any = None,
    correlation_id: str | None = None,
    now_iso: str | None = None,
) -> list[ExtractedCandidate]:
    if not raw_text.strip():
        return []

    # Route through llm_gateway when session is provided and provider is not "local".
    # This logs the call to llm_call_log for observability (ADR-12 / D4).
    if session is not None and provider != "local":
        raw_candidates = _extract_via_gateway(
            session=session,
            raw_text=raw_text,
            source_channel=source_channel,
            context=context,
            provider=provider,
            model=model,
            temperature=temperature,
            correlation_id=correlation_id,
            now_iso=now_iso,
        )
    else:
        # Fallback: direct call through llm/client.py (backward compat, no session)
        config = LLMConfig(provider=provider, model=model, temperature=temperature)
        raw_candidates = extract_candidates_with_llm(
            config=config,
            text=raw_text,
            source_channel=source_channel,
            context=context,
        )

    results: list[ExtractedCandidate] = []
    for item in raw_candidates:
        parsed = _parse_candidate(item)
        if parsed is None:
            continue
        results.append(parsed)
    return results


def _extract_via_gateway(
    *,
    session: Any,
    raw_text: str,
    source_channel: str,
    context: dict[str, str],
    provider: str,
    model: str,
    temperature: float,
    correlation_id: str | None,
    now_iso: str | None,
) -> list[dict[str, Any]]:
    """Route LLM extraction through llm_gateway for observability."""
    from executive_cli.llm_gateway import LLMGatewayError, call_llm

    prompt = _build_prompt(text=raw_text, source_channel=source_channel, context=context)
    try:
        response = call_llm(
            session,
            prompt=prompt,
            provider=provider,
            model=model,
            temperature=temperature,
            correlation_id=correlation_id,
            now_iso=now_iso,
            parse_json=True,
        )
    except LLMGatewayError as exc:
        raise LLMClientError(str(exc)) from exc

    if isinstance(response.parsed, list):
        return response.parsed
    if isinstance(response.parsed, dict):
        # Unwrap {"tasks": [...]} style response
        for key in ("tasks", "candidates", "items"):
            if isinstance(response.parsed.get(key), list):
                return response.parsed[key]
    # Fallback: try to parse text directly
    try:
        result = json.loads(response.text)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _build_prompt(*, text: str, source_channel: str, context: dict[str, str]) -> str:
    return (
        "Extract actionable GTD tasks from text. Return STRICT JSON array only.\\n"
        "Each item keys: "
        "title,suggested_status,suggested_priority,estimate_min,due_date,waiting_on,ping_at,"
        "commitment_hint,project_hint,confidence,rationale.\\n"
        "Rules: suggested_status in NOW|NEXT|WAITING|SOMEDAY. "
        "suggested_priority in P1|P2|P3. confidence in [0,1]. "
        "If unsure, lower confidence.\\n"
        f"source_channel={source_channel}\\n"
        f"context={json.dumps(context, ensure_ascii=True)}\\n"
        "text:\\n"
        f"{text}"
    )


def _parse_candidate(item: Any) -> ExtractedCandidate | None:
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    if not title:
        return None

    confidence_raw = item.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    estimate_raw = item.get("estimate_min")
    estimate_min: int | None
    try:
        estimate_min = int(estimate_raw) if estimate_raw is not None else None
    except (TypeError, ValueError):
        estimate_min = None

    return ExtractedCandidate(
        title=title,
        suggested_status=_normalize_opt_str(item.get("suggested_status")),
        suggested_priority=_normalize_opt_str(item.get("suggested_priority")),
        estimate_min=estimate_min,
        due_date=_normalize_opt_str(item.get("due_date")),
        waiting_on=_normalize_opt_str(item.get("waiting_on")),
        ping_at=_normalize_opt_str(item.get("ping_at")),
        commitment_hint=_normalize_opt_str(item.get("commitment_hint")),
        project_hint=_normalize_opt_str(item.get("project_hint")),
        confidence=confidence,
        rationale=_normalize_opt_str(item.get("rationale")),
    )


def _normalize_opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["LLMClientError", "extract_candidates"]
