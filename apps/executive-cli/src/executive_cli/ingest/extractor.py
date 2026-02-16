from __future__ import annotations

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
) -> list[ExtractedCandidate]:
    if not raw_text.strip():
        return []

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
