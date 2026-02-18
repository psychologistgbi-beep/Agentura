# D2. MICROSERVICES_POLICY — Железное правило проектирования

> Применяется ко всем модулям Agentura v2. "Микросервис" = Python-модуль с чёткими границами,
> готовый к выносу в отдельный процесс/контейнер без изменения интерфейса.

## 1. Контракты (MUST)

- **MUST** иметь один публичный файл-интерфейс. Все остальные функции — `_private`.
- **MUST** принимать и возвращать типизированные dataclass/Pydantic. Никогда `dict[str, Any]` на границе.
- **MUST** документировать contract в docstring первой публичной функции (input types → output type → exceptions).
- **MUST NOT** импортировать внутренности другого модуля. Только его публичный API.
- **MUST NOT** иметь циклических импортов.

```python
# ✅ GOOD: typed contract
def create_task_record(session: Session, *, title: str, status: TaskStatus, ...) -> Task:
    """Create a task and optional email link. Raises TaskServiceError on validation failure."""

# ❌ BAD: dict-based, no contract
def create_task(session, data: dict) -> dict:
    ...
```

## 2. Single Responsibility (MUST)

- **MUST** иметь одну зону ответственности (один domain entity или один infrastructure concern).
- **MUST NOT** совмещать I/O с бизнес-логикой в одной функции.
- **MUST** быть < 300 LOC (включая docstrings). Если больше — split.

```
# ✅ GOOD: extractor.py — только LLM → candidates parse
# ✅ GOOD: router.py — только confidence → route decision

# ❌ BAD: pipeline.py — fetch + extract + classify + dedup + route в одном файле
```

## 3. Идемпотентность (MUST для write-path)

- **MUST** использовать natural key для dedup при создании записей: `(channel, source_ref)` для IngestDocument, `(source, external_id)` для Email.
- **MUST** проверять существование перед INSERT (SELECT + INSERT, не INSERT ON CONFLICT для бизнес-логики).
- **SHOULD** логировать skip при обнаружении дубликата.
- **MUST NOT** полагаться на auto-increment ID для идемпотентности.

```python
# ✅ GOOD
existing = session.exec(select(IngestDocument).where(
    IngestDocument.channel == channel, IngestDocument.source_ref == ref
)).first()
if existing:
    return IngestResult(skipped=True, reason="already_processed")

# ❌ BAD: pipeline_engine idempotency_key = hash(run_id + step + input)
#    Over-engineering для линейных 3-шаговых пайплайнов
```

## 4. Observability (MUST)

- **MUST** логировать каждый LLM-вызов в `llm_call_log` (provider, latency_ms, tokens, status).
- **MUST** логировать каждое решение ingest в `ingest_log` (action, confidence, document_id).
- **SHOULD** включать `correlation_id` (UUID) в вызовы, проходящие через несколько модулей.
- **MUST NOT** логировать raw prompts или email bodies в БД (privacy: ADR-10).

## 5. Error Handling (MUST)

- **MUST** использовать typed exceptions: `TaskServiceError`, `LLMGatewayError`, `IngestError`.
- **MUST** пробрасывать исключения вверх. Catch только когда есть осмысленное recovery action.
- **MUST NOT** использовать bare `except:` или `except Exception: pass`.
- **SHOULD** включать context в ошибку: `f"Email {email_id}: LLM extraction failed: {exc}"`.

```python
# ✅ GOOD
except LLMGatewayError as exc:
    doc.status = "failed"
    session.add(doc)
    raise IngestError(f"Document {doc.id}: LLM failed") from exc

# ❌ BAD
except Exception:
    pass  # silent failure
```

## 6. Retries и Timeouts (MUST)

- **MUST** устанавливать timeout на каждый HTTP-вызов (LLM, IMAP, CalDAV). Default: 30s.
- **MUST NOT** реализовывать retry-логику в Python-коде. Retries = ответственность n8n.
- **SHOULD** возвращать structured error с `is_retryable: bool` для n8n decision.

```python
# ✅ GOOD: timeout в urllib
urlopen(req, timeout=30)

# ❌ BAD: retry loop внутри модуля
for attempt in range(3):
    try: ...
    except: time.sleep(2 ** attempt)
```

## 7. Ownership (MUST)

- **MUST** иметь одного "владельца" на каждый модуль (имя роли, не человека).
- **MUST** указывать владельца в module docstring.

| Модуль | Владелец |
|--------|----------|
| `cli.py` | EA |
| `llm_gateway.py` | Architect |
| `ingest_service.py`, `extractor.py`, `classifier.py`, `dedup.py`, `router.py` | EA |
| `task_service.py`, `planner.py` | EA |
| `connectors/*` | EA |
| `models.py`, `db.py` | Architect |

## 8. Testing Pyramid (MUST)

- **MUST** unit-тесты для каждой публичной функции.
- **MUST** contract-тесты для cross-module boundaries (extractor→classifier, ingest→task_service).
- **SHOULD** e2e-тест: `execas ingest email --limit 1` с фикстурой email.
- **MUST NOT** mock DB. Использовать in-memory SQLite.
- **MUST NOT** mock LLM в integration-тестах для extractor. Использовать "golden prompt" fixtures с ожидаемым JSON output.

## 9. Версионирование (SHOULD)

- **SHOULD** использовать semantic versioning для CLI (MAJOR.MINOR.PATCH).
- **MUST NOT** делать breaking changes в public API модуля без explicit migration path.
- **SHOULD** документировать breaking changes в CHANGELOG.

## 10. Anti-patterns (MUST NOT)

| # | Anti-pattern | Пример из v1 | Почему плохо |
|---|-------------|--------------|--------------|
| A1 | God-object | `cli.py` 1975 LOC, 23 импорта | Невозможно тестировать/менять один command без загрузки всего |
| A2 | Copy-paste services | 3 pipeline-файла по 365–406 LOC | Баг в одном → баг во всех; maintenance * N |
| A3 | Framework без use-cases | `pipeline_engine.py` (521 LOC) для 3-шаговых линейных цепочек | Complexity tax без payoff |
| A4 | Двойной LLM-клиент | `llm/client.py` + `llm_gateway.py` | Unclear contract, divergent behavior |
| A5 | Governance theatre | 11 ролей, 87 spec-файлов, 7-section gate reports для 1-person project | Tokens spent on ceremony, not value |
| A6 | Bare-dict returns | `call_llm(...) → dict[str, Any]` | No IDE support, no validation, runtime surprises |

## Open questions

Нет.
