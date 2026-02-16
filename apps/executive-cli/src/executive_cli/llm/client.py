from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClientError(RuntimeError):
    """Raised when extraction LLM provider is unavailable or returns invalid output."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    temperature: float


def extract_candidates_with_llm(
    *,
    config: LLMConfig,
    text: str,
    source_channel: str,
    context: dict[str, str],
) -> list[dict[str, Any]]:
    provider = config.provider.strip().lower()
    if provider == "local":
        return _extract_candidates_local(text=text)

    prompt = _build_prompt(text=text, source_channel=source_channel, context=context)
    if provider == "anthropic":
        payload_text = _call_anthropic(prompt=prompt, model=config.model, temperature=config.temperature)
    elif provider == "openai":
        payload_text = _call_openai(prompt=prompt, model=config.model, temperature=config.temperature)
    else:
        raise LLMClientError(f"Unsupported LLM provider: {config.provider}")

    return _parse_candidates_json(payload_text)


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


def _call_anthropic(*, prompt: str, model: str, temperature: float) -> str:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise LLMClientError("LLM API key is missing (LLM_API_KEY).")

    body = {
        "model": model,
        "max_tokens": 1200,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30.0) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise LLMClientError(f"Anthropic request failed with HTTP {exc.code}.") from None
    except URLError:
        raise LLMClientError("Anthropic endpoint is unreachable.") from None
    except TimeoutError:
        raise LLMClientError("Anthropic request timed out.") from None

    content = data.get("content", [])
    text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
    payload_text = "\n".join(part for part in text_parts if part).strip()
    if not payload_text:
        raise LLMClientError("Anthropic response did not contain text output.")
    return payload_text


def _call_openai(*, prompt: str, model: str, temperature: float) -> str:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise LLMClientError("LLM API key is missing (LLM_API_KEY).")

    body = {
        "model": model,
        "input": prompt,
        "temperature": temperature,
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30.0) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise LLMClientError(f"OpenAI request failed with HTTP {exc.code}.") from None
    except URLError:
        raise LLMClientError("OpenAI endpoint is unreachable.") from None
    except TimeoutError:
        raise LLMClientError("OpenAI request timed out.") from None

    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts: list[str] = []
    for output_item in data.get("output", []):
        for content_item in output_item.get("content", []):
            text_value = content_item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_parts.append(text_value)
    payload_text = "\n".join(text_parts).strip()
    if not payload_text:
        raise LLMClientError("OpenAI response did not contain text output.")
    return payload_text


def _parse_candidates_json(payload_text: str) -> list[dict[str, Any]]:
    cleaned = payload_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMClientError("LLM output is not valid JSON.") from exc

    if not isinstance(parsed, list):
        raise LLMClientError("LLM output must be a JSON array.")

    results: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            results.append(item)
    return results


def _extract_candidates_local(*, text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    candidates: list[dict[str, Any]] = []
    keywords = (
        "todo",
        "action",
        "follow-up",
        "follow up",
        "нужно",
        "надо",
        "договорились",
        "подготов",
        "провер",
        "send",
        "fix",
    )
    for line in lines:
        lower = line.lower()
        if not any(keyword in lower for keyword in keywords):
            continue

        title = re.sub(r"^(?:[-*]\s*)?(?:\[[ xX]\]\s*)?(?:todo|action)[:\s-]*", "", line, flags=re.IGNORECASE)
        title = title.strip(" -:;")
        if not title:
            continue

        confidence = 0.85 if lower.startswith(("todo", "action", "- todo", "* todo")) else 0.65
        priority = "P1" if any(token in lower for token in ("asap", "urgent", "срочно")) else "P2"
        status = "WAITING" if any(token in lower for token in ("waiting", "awaiting", "жд", "wait")) else "NEXT"

        candidates.append(
            {
                "title": title,
                "suggested_status": status,
                "suggested_priority": priority,
                "estimate_min": 30,
                "due_date": None,
                "waiting_on": None,
                "ping_at": None,
                "commitment_hint": None,
                "project_hint": None,
                "confidence": confidence,
                "rationale": "local keyword extraction",
            }
        )

    return candidates
