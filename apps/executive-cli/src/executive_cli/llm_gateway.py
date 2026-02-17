"""LLM Gateway — unified proxy for all LLM calls (ADR-12).

Routes through fallback chain: ollama → anthropic → openai → local.
Logs every call to llm_call_log for cost/latency observability.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlmodel import Session

from executive_cli.models import LLMCallLog


class LLMGatewayError(RuntimeError):
    """Raised when all providers fail."""


@dataclass(frozen=True)
class LLMResponse:
    """Result of an LLM call."""

    text: str
    parsed: dict[str, Any] | list[Any] | None = None
    provider: str = ""
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0


# --- Default config ---

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


# --- Main entry point ---


def call_llm(
    session: Session | None,
    *,
    prompt: str,
    correlation_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    now_iso: str | None = None,
    parse_json: bool = False,
) -> LLMResponse:
    """Call LLM with fallback chain and logging.

    Fallback order (configurable via provider):
      1. ollama (local, zero cost)
      2. anthropic (cloud, paid)
      3. openai (cloud, paid)
      4. local (keyword heuristic, zero quality)

    If provider is specified explicitly, only that provider is tried.
    If provider is None, the full fallback chain is attempted.
    """
    now = now_iso or _now_iso()
    prompt_hash = _hash_prompt(prompt)

    if provider:
        providers = [provider]
    else:
        # Default fallback chain — ollama first (free, local)
        providers = _get_fallback_chain()

    last_error: str | None = None

    for prov in providers:
        start_time = time.monotonic()
        try:
            response = _call_provider(
                provider=prov,
                prompt=prompt,
                model=model,
                temperature=temperature,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            # Parse JSON if requested
            if parse_json and response.text:
                parsed = _parse_json_response(response.text)
                response = LLMResponse(
                    text=response.text,
                    parsed=parsed,
                    provider=response.provider,
                    model=response.model,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    latency_ms=elapsed_ms,
                )
            else:
                response = LLMResponse(
                    text=response.text,
                    parsed=response.parsed,
                    provider=response.provider,
                    model=response.model,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    latency_ms=elapsed_ms,
                )

            # Log success
            _log_call(
                session,
                correlation_id=correlation_id,
                provider=response.provider,
                model=response.model,
                prompt_hash=prompt_hash,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                latency_ms=elapsed_ms,
                status="success",
                now_iso=now,
            )
            return response

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            last_error = f"{prov}: {type(exc).__name__}: {exc}"

            # Log failure
            _log_call(
                session,
                correlation_id=correlation_id,
                provider=prov,
                model=model or "unknown",
                prompt_hash=prompt_hash,
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=elapsed_ms,
                status="fallback" if len(providers) > 1 else "error",
                error=str(exc),
                now_iso=now,
            )
            continue

    raise LLMGatewayError(f"All providers failed. Last error: {last_error}")


# --- Provider implementations ---


def _get_fallback_chain() -> list[str]:
    """Return ordered list of providers to try."""
    chain = []
    # Ollama first if available
    ollama_url = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL)
    if ollama_url:
        chain.append("ollama")
    # Cloud providers if API key exists
    if os.getenv("LLM_API_KEY", "").strip():
        chain.append("anthropic")
        chain.append("openai")
    # Local heuristic as last resort
    chain.append("local")
    return chain


def _call_provider(
    *,
    provider: str,
    prompt: str,
    model: str | None,
    temperature: float,
) -> LLMResponse:
    """Dispatch to a specific provider."""
    if provider == "ollama":
        return _call_ollama(prompt=prompt, model=model, temperature=temperature)
    if provider == "anthropic":
        return _call_anthropic(prompt=prompt, model=model, temperature=temperature)
    if provider == "openai":
        return _call_openai(prompt=prompt, model=model, temperature=temperature)
    if provider == "local":
        return _call_local(prompt=prompt)
    raise LLMGatewayError(f"Unknown provider: {provider}")


def _call_ollama(
    *,
    prompt: str,
    model: str | None,
    temperature: float,
) -> LLMResponse:
    """Call Ollama /api/generate endpoint."""
    base_url = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    use_model = model or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)

    body = {
        "model": use_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    request = Request(
        f"{base_url}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urlopen(request, timeout=120.0) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise LLMGatewayError(f"Ollama HTTP {exc.code}") from None
    except URLError as exc:
        raise LLMGatewayError(f"Ollama unreachable: {exc.reason}") from None
    except TimeoutError:
        raise LLMGatewayError("Ollama request timed out (120s)") from None

    text = data.get("response", "").strip()
    if not text:
        raise LLMGatewayError("Ollama returned empty response")

    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")

    return LLMResponse(
        text=text,
        provider="ollama",
        model=use_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _call_anthropic(
    *,
    prompt: str,
    model: str | None,
    temperature: float,
) -> LLMResponse:
    """Call Anthropic /v1/messages endpoint."""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise LLMGatewayError("LLM_API_KEY not set for Anthropic")

    use_model = model or "claude-sonnet-4-5-20250929"

    body = {
        "model": use_model,
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
        raise LLMGatewayError(f"Anthropic HTTP {exc.code}") from None
    except URLError:
        raise LLMGatewayError("Anthropic unreachable") from None
    except TimeoutError:
        raise LLMGatewayError("Anthropic timeout") from None

    content = data.get("content", [])
    text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
    text = "\n".join(part for part in text_parts if part).strip()
    if not text:
        raise LLMGatewayError("Anthropic returned empty text")

    usage = data.get("usage", {})
    return LLMResponse(
        text=text,
        provider="anthropic",
        model=use_model,
        prompt_tokens=usage.get("input_tokens"),
        completion_tokens=usage.get("output_tokens"),
    )


def _call_openai(
    *,
    prompt: str,
    model: str | None,
    temperature: float,
) -> LLMResponse:
    """Call OpenAI /v1/responses endpoint."""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise LLMGatewayError("LLM_API_KEY not set for OpenAI")

    use_model = model or "gpt-4o"

    body = {
        "model": use_model,
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
        raise LLMGatewayError(f"OpenAI HTTP {exc.code}") from None
    except URLError:
        raise LLMGatewayError("OpenAI unreachable") from None
    except TimeoutError:
        raise LLMGatewayError("OpenAI timeout") from None

    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        text = output_text.strip()
    else:
        text_parts: list[str] = []
        for output_item in data.get("output", []):
            for content_item in output_item.get("content", []):
                text_value = content_item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    text_parts.append(text_value)
        text = "\n".join(text_parts).strip()

    if not text:
        raise LLMGatewayError("OpenAI returned empty text")

    return LLMResponse(
        text=text,
        provider="openai",
        model=use_model,
    )


def _call_local(*, prompt: str) -> LLMResponse:
    """Local keyword heuristic — zero-cost fallback, no network."""
    # Import the existing local extractor logic
    from executive_cli.llm.client import _extract_candidates_local

    # The local extractor works on raw text lines, not prompts
    # Extract the text portion from the prompt
    text = prompt
    text_marker = "text:\n"
    idx = prompt.find(text_marker)
    if idx >= 0:
        text = prompt[idx + len(text_marker):]

    candidates = _extract_candidates_local(text=text)
    return LLMResponse(
        text=json.dumps(candidates, ensure_ascii=False),
        parsed=candidates,
        provider="local",
        model="keyword_heuristic",
    )


# --- JSON parsing ---


def _parse_json_response(text: str) -> dict[str, Any] | list[Any] | None:
    """Parse JSON from LLM response, stripping markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# --- Logging ---


def _log_call(
    session: Session | None,
    *,
    correlation_id: str | None,
    provider: str,
    model: str,
    prompt_hash: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    status: str,
    error: str | None = None,
    now_iso: str,
) -> None:
    """Log an LLM call to the database."""
    if session is None:
        return

    entry = LLMCallLog(
        correlation_id=correlation_id,
        provider=provider,
        model=model,
        prompt_hash=prompt_hash,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=status,
        error=error,
        created_at=now_iso,
    )
    session.add(entry)
    session.flush()
