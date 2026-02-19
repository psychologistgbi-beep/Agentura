# D6. LLM_GATEWAY_SPEC — Единый контракт call_llm()

## 1. Принцип

Один модуль, одна функция, один путь. Весь LLM-трафик проекта идёт через `call_llm()`.
Старый `llm/client.py` удаляется. Prompt-шаблон переносится в `extractor.py`.

## 2. Публичный API

```python
def call_llm(
    session: Session | None,
    *,
    prompt: str,
    provider: str | None = None,     # None → fallback chain
    model: str | None = None,        # None → default per provider
    temperature: float = 0.0,
    timeout_s: int = 30,
    correlation_id: str | None = None,
    now_iso: str | None = None,
    parse_json: bool = False,
) -> LLMResponse
```

**MUST:** `LLMGatewayError` если все провайдеры fail.
**MUST:** если `session` не None → запись в `llm_call_log` (даже при ошибке).
**MUST:** `_sanitise_output()` перед любым parse (strip control chars, truncate 32 KB).

## 3. LLMResponse

```python
@dataclass(frozen=True)
class LLMResponse:
    text: str                               # raw LLM output
    parsed: dict | list | None = None       # only if parse_json=True
    provider: str = ""
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
```

## 4. Fallback chain

**Policy:** использовать локальную LLM только для хорошо описанных простых задач. Тщательная приёмка результата обязательна.

Порядок при `provider=None`:

```
1. ollama (localhost:11434, model=qwen2.5:7b, timeout=30s, RAM=18GB)
     ↓ fail
2. local heuristic (keyword extraction, zero LLM, zero quality)
     ↓ parse_json + fail to parse
3. raise LLMGatewayError("All providers failed: ...")
```

**Cloud API (Anthropic) не используется для задач ассистента.** Ключ доступен через Claude Code подписку, но предназначен для разработки, не для runtime extraction.

Если `provider` задан явно — только этот провайдер, без fallback.

## 5. Extractor prompt schema

**Input для extractor:**
```
prompt = f"""Extract actionable GTD tasks from text. Return STRICT JSON array only.
Each item: {{"title": str, "suggested_status": "NOW|NEXT|WAITING|SOMEDAY",
"suggested_priority": "P1|P2|P3", "estimate_min": int, "due_date": "YYYY-MM-DD"|null,
"waiting_on": str|null, "ping_at": "ISO8601"|null,
"project_hint": str|null, "confidence": float 0-1, "rationale": str}}
source_channel={channel}
context={json.dumps(context)}
text:
{text}"""
```

**Expected LLM response (JSON array):**
```json
[
  {
    "title": "Sign vendor contract",
    "suggested_status": "NEXT",
    "suggested_priority": "P1",
    "estimate_min": 30,
    "due_date": null,
    "waiting_on": null,
    "ping_at": null,
    "project_hint": null,
    "confidence": 0.92,
    "rationale": "Explicit action in email subject"
  }
]
```

**Parse errors:** если JSON невалиден — `parsed = None`, `text` содержит raw output. Caller решает: retry или skip.

## 6. Бюджет и лимиты

| Параметр | Значение | Enforceable |
|----------|----------|-------------|
| Max prompt size | 4 KB | MUST truncate перед отправкой |
| Max response size | 32 KB | MUST truncate после получения |
| Timeout per call | 30s (configurable) | MUST в `urlopen(timeout=)` |
| Daily call budget | 50 calls | SHOULD log warning при >50. MUST NOT block |
| Retry | 0 (n8n retries workflow) | MUST NOT retry внутри gateway |

## 7. Кеширование

**MVP: нет кеша.** Каждый вызов = новый LLM request.

При ~20 emails/day и 1 LLM call per email — ~20 calls/day. Ollama local = zero cost. Кеш не нужен.

SHOULD: добавить `prompt_hash` dedup позже, если объём вырастет до 200+/day.

## 8. Redaction (privacy)

- **MUST NOT** хранить raw prompt в `llm_call_log`. Только `prompt_hash` (sha256[:16]).
- **MUST NOT** отправлять email body в LLM (ADR-10). Только `subject` + `sender`.
- **MUST** sanitise LLM output: strip `\x00-\x08`, `\x0b`, `\x0c`, `\x0e-\x1f`, `\x7f`.

## 9. llm_call_log запись

Каждый вызов (success или error) → одна строка:

```json
{
  "id": 42,
  "correlation_id": "a1b2c3d4",
  "provider": "ollama",
  "model": "qwen2.5:7b",
  "prompt_hash": "3f2a1b4c5d6e7f8a",
  "prompt_tokens": 156,
  "completion_tokens": 89,
  "latency_ms": 1240,
  "status": "success",
  "error": null,
  "created_at": "2026-02-18T07:01:23+00:00"
}
```

При ошибке: `status = "error"`, `error = "TimeoutError: 30s exceeded"`, `latency_ms = 30000`.

## Open questions

Нет.
