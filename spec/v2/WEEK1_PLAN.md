# WEEK 1 — Фундамент v2: подробный план задач

> Команда: Technical Lead (координация), Chief Architect (решения), System Analyst (трассировка).
> Исполнитель: EA agent. Каждая задача = один атомарный коммит.

---

## Обзор недели

| День | Фокус | Результат |
|------|-------|-----------|
| 1 | Инфраструктура: Docker Compose, models.py, db.py | PostgreSQL запущен, `execas init` создаёт 14 таблиц |
| 2 | Копирование: task_service, connectors/imap | Ядро бизнес-логики работает с тестами |
| 3 | LLM Gateway: rewrite, удаление llm/client.py | Единый `call_llm()` с Ollama |
| 4 | Extraction: extractor, dedup | Golden prompt тесты проходят |
| 5 | Routing: classifier, router + contract tests | Полная цепочка extract→classify→dedup→route работает |

**Milestone W1:** `task_service`, `llm_gateway`, `extractor`, `dedup`, `classifier`, `router` — все работают, unit + contract tests pass, coverage ≥ 80%.

---

## День 1: Инфраструктура

### T1.1 — Docker Compose для PostgreSQL + n8n

**Роль:** EA (создание файла) + Architect (ревью)

**Что делаем:**
1. Создать `docker-compose.yml` в корне проекта
2. Сервисы: `postgres:17-alpine` + `n8nio/n8n:latest`
3. Создать `.env.example` с переменными (без реальных секретов)

**Файлы:**
- `CREATE docker-compose.yml`
- `CREATE .env.example`
- `EDIT .gitignore` — добавить `.env` если нет

**docker-compose.yml:**
```yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: execas
      POSTGRES_USER: execas
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U execas"]
      interval: 5s
      timeout: 3s
      retries: 5

  n8n:
    image: n8nio/n8n:latest
    environment:
      DB_TYPE: postgresdb
      DB_POSTGRESDB_HOST: postgres
      DB_POSTGRESDB_DATABASE: n8n
      DB_POSTGRESDB_USER: execas
      DB_POSTGRESDB_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5678:5678"
    volumes:
      - n8n_data:/home/node/.n8n
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
  n8n_data:
```

**.env.example:**
```
POSTGRES_PASSWORD=changeme
EXECAS_DB_URL=postgresql+psycopg2://execas:changeme@localhost:5432/execas
```

**Done criteria:**
- `docker compose up -d` запускает оба сервиса
- `pg_isready` проходит
- n8n UI доступен на `localhost:5678`

**Commit:** `infra: add Docker Compose for PostgreSQL and n8n`

---

### T1.2 — Rewrite models.py (14 таблиц)

**Роль:** EA (код) + Architect (ревью схемы)

**Что делаем:**
1. Сначала прочитать v1 `models.py` (355 LOC, 23 таблицы)
2. Создать новый `models.py` с 14 таблицами (удалить 9: Commitment, Person, Decision, WeeklyReview, SyncState, PipelineRun, PipelineEvent, ApprovalRequest + LLMCallLog остаётся)
3. Убрать `commitment_id` FK из Task
4. Убрать FTS5 виртуальные таблицы (people_fts, decisions_fts)
5. Добавить PostgreSQL-совместимые типы (убрать SQLite-specific CHECK через text)

**Таблицы v2 (14):**

Core (6):
- `Settings` (key PK, value)
- `Task` (id, title, status, priority, estimate_min, due_date, project_id FK, area_id FK, waiting_on, ping_at, created_at, updated_at)
- `TaskDraft` (id, title, suggested_status, suggested_priority, estimate_min, confidence, rationale, dedup_flag, source_channel, source_document_id FK, source_email_id FK, status, created_at, reviewed_at)
- `BusyBlock` (id, calendar_id FK, start_dt, end_dt, title, source, external_id, external_etag, is_deleted)
- `Calendar` (id, slug UNIQUE, name, timezone)
- `Email` (id, source, external_id, mailbox_uid, subject, sender, received_at, first_seen_at, last_seen_at, flags_json) UNIQUE(source, external_id)

Supporting (4):
- `TaskEmailLink` (id, task_id FK, email_id FK, link_type, created_at) UNIQUE(task_id, email_id)
- `IngestDocument` (id, channel, source_ref, title, status, items_extracted, created_at, processed_at) UNIQUE(channel, source_ref)
- `IngestLog` (id, document_id FK, action, task_id FK, draft_id FK, confidence, rationale, created_at)
- `LLMCallLog` (id, correlation_id, provider, model, prompt_hash, prompt_tokens, completion_tokens, latency_ms, status, error, created_at)

Reference (2):
- `Area` (id, name)
- `Project` (id, name, area_id FK)

Planner (2):
- `DayPlan` (id, date, variant, source, created_at)
- `TimeBlock` (id, day_plan_id FK, start_dt, end_dt, type, task_id FK, label)

**Изменения относительно v1:**
- Удалить: `Commitment`, `Person`, `Decision`, `WeeklyReview`, `SyncState`, `PipelineRun`, `PipelineEvent`, `ApprovalRequest`
- Удалить: `commitment_id` из `Task`
- Добавить: `rationale`, `dedup_flag`, `source_channel`, `source_document_id`, `source_email_id` в `TaskDraft` (если не было)
- Добавить: `confidence`, `rationale` в `IngestLog` (если не было)

**LOC target:** < 200

**Done criteria:**
- Файл < 200 LOC
- 14 классов с `table=True`
- Все enum-ы определены (TaskStatus, TaskPriority, IngestStatus, etc.)
- Нет импортов удалённых моделей

**Commit:** `feat(models): rewrite models.py — 14 tables for v2`

---

### T1.3 — Rewrite db.py (PostgreSQL + SQLite switch)

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `db.py` (102 LOC)
2. Переписать:
   - `get_database_url()` → читает `EXECAS_DB_URL` env var. Если не задана → fallback на SQLite (для тестов и dev)
   - `get_engine()` → убрать `check_same_thread` для PostgreSQL, оставить для SQLite
   - `apply_migrations()` → Alembic upgrade head
   - `seed_defaults()` → settings + primary calendar
   - `initialize_database()` → orchestrator
3. Настройки по умолчанию:
   - Убрать: `ingest_llm_provider`, `ingest_llm_model`, `ingest_llm_temperature` (LLM config → env vars, не settings table)
   - Оставить: timezone, planning_start/end, lunch, min_focus_block, buffer, ingest_auto_threshold

**LOC target:** < 80

**Done criteria:**
- `EXECAS_DB_URL=postgresql+psycopg2://...` → PostgreSQL engine
- `EXECAS_DB_URL` не задан → SQLite (`.data/execas.sqlite`)
- `execas init` работает с обоими backends
- Unit тест: `initialize_database()` с in-memory SQLite

**Commit:** `feat(db): rewrite db.py — PostgreSQL/SQLite dual backend`

---

### T1.4 — Новая Alembic migration (v2 initial schema)

**Роль:** EA

**Что делаем:**
1. Создать новую migration `v2_initial_schema.py` которая:
   - Создаёт все 14 таблиц с нуля (для новых инсталляций)
   - ИЛИ: сбросить Alembic history и сделать одну начальную миграцию
2. Предпочтительно: одна чистая миграция вместо 8 старых

**Подход:** Оставить старые миграции в git history, но сделать squash:
- Удалить содержимое `alembic/versions/`
- Создать одну `v2_001_initial.py` с 14 таблицами
- Обновить `alembic.ini` если нужно

**Done criteria:**
- `alembic upgrade head` создаёт 14 таблиц на чистой PostgreSQL
- `alembic upgrade head` создаёт 14 таблиц на чистой SQLite
- Нет ошибок при `execas init`

**Commit:** `feat(migrations): squash to single v2 initial schema`

---

### T1.5 — Добавить psycopg2 в зависимости

**Роль:** EA

**Что делаем:**
1. Добавить `psycopg2-binary` (или `psycopg[binary]`) в `pyproject.toml` dependencies
2. `uv sync` для обновления lock

**Done criteria:**
- `import psycopg2` работает
- `create_engine("postgresql+psycopg2://...")` не падает

**Commit:** `deps: add psycopg2-binary for PostgreSQL support`

---

### T1.6 — Тест: init создаёт все таблицы

**Роль:** EA

**Что делаем:**
1. Написать тест в `tests/test_db.py`:
   - `test_initialize_creates_all_tables` — in-memory SQLite, проверить 14 таблиц
   - `test_seed_defaults_creates_settings` — проверить default settings
   - `test_seed_defaults_creates_primary_calendar` — проверить primary calendar
2. Адаптировать `tests/conftest.py` для новых моделей

**Done criteria:**
- Все тесты проходят
- `uv run pytest tests/test_db.py -v` — зелёные

**Commit:** `test(db): init creates 14 tables and seeds defaults`

---

### T1.7 — Quality gate: Day 1

**Роль:** TL (проверка)

**Что делаем:**
```bash
cd apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-fail-under=80
```

**ВАЖНО:** На день 1 старые тесты могут ломаться из-за удалённых моделей. Решение:
- Удалить тесты для удалённых модулей (pipeline_engine, pipelines, approval_gate)
- Адаптировать conftest.py
- Цель: все оставшиеся тесты зелёные

**Done criteria:**
- pytest -q → 0 failures
- coverage ≥ 80%

---

## День 2: Core domain

### T2.1 — Скопировать task_service.py + адаптация

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `task_service.py` (80 LOC) — **переиспользуем**
2. Изменения:
   - Убрать `commitment_id` параметр и логику
   - Проверить совместимость с новым `models.py`
   - Убедиться что `TaskStatus`, `TaskPriority` импортируются из нового `models.py`
3. Добавить docstring с owner (`# Owner: EA`)

**LOC target:** ~75

**Done criteria:**
- `create_task_record()` работает с новыми моделями
- `TaskServiceError` при валидационных ошибках

**Commit:** `feat(task_service): adapt for v2 models, remove commitment_id`

---

### T2.2 — Тесты для task_service

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `test_task_service.py` (если есть отдельный) — **переиспользуем**
2. Адаптировать/расширить тесты:
   - `test_create_task_valid` — happy path
   - `test_create_task_empty_title_error` — пустой title → TaskServiceError
   - `test_create_task_zero_estimate_error` — estimate_min=0 → error
   - `test_create_task_waiting_without_ping_error` — WAITING без ping_at → error
   - `test_create_task_with_email_link` — from_email_id → TaskEmailLink создан
   - `test_create_task_email_not_found_error` — несуществующий email → error

**Coverage target:** ≥ 90% для task_service.py

**Done criteria:**
- 6+ тестов, все зелёные
- coverage task_service.py ≥ 90%

**Commit:** `test(task_service): 6 unit tests, coverage ≥ 90%`

---

### T2.3 — Скопировать connectors/imap.py + адаптация

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `connectors/imap.py` (274 LOC) — **переиспользуем**
2. Изменения:
   - Убрать BODY fetch если есть (ADR-10: headers only)
   - Проверить совместимость с новым `models.py` (Email model)
   - Убедиться что `MailConnectorError` определён
   - Добавить docstring с owner
3. Скопировать `connectors/__init__.py`

**LOC target:** ~250

**Done criteria:**
- `ImapConnector.fetch_headers()` компилируется
- `MailConnectorError` определён
- Нет импортов удалённых моделей

**Commit:** `feat(connectors): copy imap.py for v2, headers-only`

---

### T2.4 — Тесты для IMAP connector

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `test_mail_sync.py` (408 LOC) — **частично переиспользуем** (только тесты для fetch_headers)
2. Написать/адаптировать:
   - `test_fetch_headers_success` — mock IMAP, корректный разбор headers
   - `test_fetch_headers_connection_error` — IMAP недоступен → MailConnectorError
   - `test_fetch_headers_since_uid_filtering` — since_uid=100 → только UID > 100
   - `test_fetch_headers_empty_inbox` — пустой INBOX → пустой результат
   - `test_fetch_headers_encoding` — non-ASCII subject → корректный decode

**Done criteria:**
- 5+ тестов, все зелёные
- mock IMAP (не реальный сервер)

**Commit:** `test(imap): 5 unit tests for fetch_headers`

---

### T2.5 — Quality gate: Day 2

**Роль:** TL

```bash
uv run pytest -q && uv run pytest --cov=executive_cli --cov-fail-under=80
```

---

## День 3: LLM Gateway

### T3.1 — Rewrite llm_gateway.py

**Роль:** EA + Architect (ревью fallback chain)

**Что делаем:**
1. Прочитать v1 `llm_gateway.py` (449 LOC) — **переписываем с упрощениями**
2. Контракт из D6:
   ```python
   def call_llm(session, *, prompt, provider=None, model=None,
                temperature=0.0, timeout_s=30, correlation_id=None,
                now_iso=None, parse_json=False) -> LLMResponse
   ```
3. Fallback chain (D6 updated):
   - `ollama` (localhost:11434, qwen2.5:7b) → `local heuristic` → `LLMGatewayError`
   - **Нет Anthropic** в fallback (по решению пользователя)
4. `_sanitise_output()` — strip control chars, truncate 32 KB
5. Логирование в `llm_call_log` если `session` не None
6. `LLMResponse` dataclass (frozen)
7. `LLMGatewayError` exception
8. Owner docstring

**Убрать из v1:**
- Anthropic/OpenAI провайдеры из fallback chain
- Зависимость от `llm/client.py`
- Pipeline Engine integration
- Retry logic (n8n responsibility)

**LOC target:** < 250

**Done criteria:**
- `call_llm()` работает с Ollama
- `call_llm()` fallback на local heuristic при Ollama failure
- `_sanitise_output()` стрипает control chars
- `LLMGatewayError` при полном отказе
- Запись в `llm_call_log` при наличии session

**Commit:** `feat(llm_gateway): rewrite for v2 — Ollama-only, no cloud fallback`

---

### T3.2 — Удалить llm/client.py и llm/ каталог

**Роль:** EA

**Что делаем:**
1. Удалить `src/executive_cli/llm/client.py` (214 LOC)
2. Удалить `src/executive_cli/llm/__init__.py`
3. Удалить каталог `src/executive_cli/llm/`
4. Grep по всему коду: нет `from executive_cli.llm` нигде
5. Удалить тесты если были отдельные для `llm/client.py`

**Done criteria:**
- `grep -r "from executive_cli.llm" src/` → 0 results
- `grep -r "import executive_cli.llm" src/` → 0 results
- Каталог `llm/` удалён

**Commit:** `refactor: delete llm/client.py — replaced by llm_gateway`

---

### T3.3 — Тесты для llm_gateway

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `test_llm_gateway.py` (157 LOC) — **частично переиспользуем**
2. Написать/адаптировать:
   - `test_call_llm_ollama_success` — mock ollama → LLMResponse
   - `test_call_llm_ollama_timeout_fallback_heuristic` — ollama timeout → local heuristic
   - `test_call_llm_all_fail_raises_error` — все провайдеры fail → LLMGatewayError
   - `test_sanitise_output_strips_control_chars` — `\x00\x01text\x7f` → `text`
   - `test_sanitise_output_truncates_32kb` — 64KB input → 32KB output
   - `test_call_llm_logs_to_db` — session provided → llm_call_log запись создана
   - `test_call_llm_logs_error_to_db` — ошибка + session → llm_call_log с status=error
   - `test_call_llm_parse_json` — parse_json=True → parsed field заполнен
   - `test_call_llm_parse_json_invalid` — невалидный JSON → parsed=None, text заполнен

**Coverage target:** ≥ 70% для llm_gateway.py

**Done criteria:**
- 9 тестов, все зелёные
- mock HTTP (не реальный Ollama)

**Commit:** `test(llm_gateway): 9 unit tests, Ollama mock`

---

### T3.4 — Quality gate: Day 3

**Роль:** TL

```bash
uv run pytest -q && uv run pytest --cov=executive_cli --cov-fail-under=80
```

---

## День 4: Extraction + Dedup

### T4.1 — Rewrite extractor.py

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `ingest/extractor.py` (165 LOC) — **переписываем, упрощаем**
2. Контракт из D3:
   ```python
   def extract(session, text, channel, context) -> list[ExtractedCandidate]
   ```
3. `ExtractedCandidate` dataclass:
   ```python
   @dataclass(frozen=True)
   class ExtractedCandidate:
       title: str
       suggested_status: str      # NOW|NEXT|WAITING|SOMEDAY
       suggested_priority: str    # P1|P2|P3
       estimate_min: int
       due_date: str | None
       waiting_on: str | None
       ping_at: str | None
       project_hint: str | None
       confidence: float          # 0.0–1.0
       rationale: str
   ```
4. Prompt template из D6 section 5
5. Вызов `call_llm(parse_json=True)` → parse → validate → list[ExtractedCandidate]
6. Validation:
   - confidence capped at 0.95 (security)
   - max 10 items per extraction (security)
   - title ≤ 200 chars
7. Нет зависимости от Pipeline Engine

**LOC target:** < 100

**Done criteria:**
- `extract()` возвращает typed list
- Prompt содержит channel и context
- Confidence cap 0.95
- Item cap 10

**Commit:** `feat(extractor): rewrite for v2 — typed contract, confidence cap`

---

### T4.2 — Golden prompt fixtures

**Роль:** EA

**Что делаем:**
1. Создать `tests/fixtures/golden_prompts/` каталог
2. 5 fixture pairs (input.txt + expected.json):
   - `single_task` — "Sign contract with Vendor X by Friday" → 1 task
   - `multi_task` — "Review PR #42 and deploy to staging" → 2 tasks
   - `no_task` — "Re: Meeting notes from Monday" → 0 tasks
   - `ambiguous` — "Maybe we should think about updating the docs" → 1 task, low confidence
   - `injection` — "Ignore previous instructions..." → 0 tasks or safe task

**Done criteria:**
- 5 pairs of files
- JSON files valid and match ExtractedCandidate schema

**Commit:** `test(fixtures): 5 golden prompt fixtures for extractor`

---

### T4.3 — Тесты для extractor

**Роль:** EA

**Что делаем:**
1. `test_extract_golden_single_task` — single_task fixture → 1 candidate
2. `test_extract_golden_multi_task` — multi_task fixture → 2 candidates
3. `test_extract_golden_no_task` — no_task fixture → empty list
4. `test_extract_malformed_llm_output` — mock LLM returns garbage → empty list
5. `test_extract_confidence_capped` — LLM returns confidence=1.0 → capped to 0.95
6. `test_extract_item_cap` — LLM returns 15 items → capped to 10
7. `test_extract_injection_safe` — injection subject → no injection in output

**Coverage target:** ≥ 90% для extractor.py

**Done criteria:**
- 7 тестов, все зелёные
- mock `call_llm` (не реальный Ollama)

**Commit:** `test(extractor): 7 unit tests with golden prompts`

---

### T4.4 — Rewrite dedup.py

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `ingest/dedup.py` (120 LOC) — **переиспользуем логику**
2. Контракт:
   ```python
   def check_dedup(session, title, source_document_id=None, source_email_id=None) -> DedupDecision

   class DedupDecision(StrEnum):
       SKIP = "skip"       # exact match
       FLAG = "flag"        # Levenshtein close
       PASS = "pass"        # unique
   ```
3. Логика:
   - Case-insensitive exact match → SKIP
   - Levenshtein ratio > 0.85 → FLAG
   - Else → PASS
4. Query existing tasks from DB (session.exec)

**LOC target:** < 100

**Done criteria:**
- `check_dedup()` returns DedupDecision enum
- Exact match (case-insensitive) → SKIP
- Levenshtein close → FLAG
- Unique → PASS

**Commit:** `feat(dedup): rewrite for v2 — typed DedupDecision`

---

### T4.5 — Тесты для dedup

**Роль:** EA

**Что делаем:**
1. `test_dedup_exact_match_skip` — "Sign contract" exists → SKIP
2. `test_dedup_case_insensitive_skip` — "sign CONTRACT" vs "Sign contract" → SKIP
3. `test_dedup_levenshtein_close_flag` — "Sign the contract" vs "Sign contract" → FLAG
4. `test_dedup_unique_pass` — "Buy groceries" vs "Sign contract" → PASS
5. `test_dedup_empty_db_pass` — no existing tasks → PASS
6. `test_dedup_empty_title_error` — "" → error or PASS

**Coverage target:** ≥ 90% для dedup.py

**Done criteria:**
- 6 тестов, все зелёные
- in-memory SQLite

**Commit:** `test(dedup): 6 unit tests, coverage ≥ 90%`

---

### T4.6 — Quality gate: Day 4

**Роль:** TL

```bash
uv run pytest -q && uv run pytest --cov=executive_cli --cov-fail-under=80
```

---

## День 5: Classifier + Router + Contract tests

### T5.1 — Rewrite classifier.py

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `ingest/classifier.py` (169 LOC) — **переиспользуем логику**
2. Контракт из D3:
   ```python
   def classify(session, candidates, channel, doc_id, email_id) -> list[ClassifiedCandidate]

   @dataclass(frozen=True)
   class ClassifiedCandidate:
       # все поля ExtractedCandidate +
       resolved_project_id: int | None
       resolved_area_id: int | None
       source_document_id: int
       source_email_id: int | None
   ```
3. Логика resolve:
   - `project_hint` → fuzzy match против `projects` table → `resolved_project_id`
   - Если project → `area_id` из project
   - Если нет match → None

**LOC target:** < 150

**Done criteria:**
- `classify()` enriches candidates with resolved IDs
- Unknown hints → None (не error)

**Commit:** `feat(classifier): rewrite for v2 — resolve project/area hints`

---

### T5.2 — Тесты для classifier

**Роль:** EA

1. `test_classify_known_project` — project_hint="Website" + project "Website" exists → resolved_project_id
2. `test_classify_unknown_hint` — project_hint="Unknown" → resolved_project_id=None
3. `test_classify_no_hint` — project_hint=None → resolved_project_id=None
4. `test_classify_multiple_candidates` — 3 candidates → 3 classified
5. `test_classify_area_from_project` — project has area → resolved_area_id set

**Coverage target:** ≥ 80%

**Commit:** `test(classifier): 5 unit tests`

---

### T5.3 — Rewrite router.py

**Роль:** EA

**Что делаем:**
1. Прочитать v1 `ingest/router.py` (148 LOC) — **переиспользуем**
2. Контракт:
   ```python
   def route(session, candidate, dedup_decision, threshold, now_iso) -> RouteOutcome

   class RouteOutcome(StrEnum):
       AUTO = "auto"       # confidence ≥ threshold (0.8)
       DRAFT = "draft"     # 0.3 ≤ confidence < threshold
       SKIP = "skip"       # confidence < 0.3 OR dedup=SKIP
   ```
3. Логика:
   - `dedup_decision == SKIP` → SKIP (regardless of confidence)
   - `confidence ≥ threshold` → AUTO → call `create_task_record()`
   - `0.3 ≤ confidence < threshold` → DRAFT → insert TaskDraft
   - `confidence < 0.3` → SKIP → log only

**LOC target:** < 100

**Done criteria:**
- `route()` returns RouteOutcome
- AUTO → task created
- DRAFT → task_draft inserted
- SKIP → only ingest_log

**Commit:** `feat(router): rewrite for v2 — confidence-based routing`

---

### T5.4 — Тесты для router

**Роль:** EA

1. `test_route_high_confidence_auto` — confidence=0.9 → AUTO, task created
2. `test_route_medium_confidence_draft` — confidence=0.5 → DRAFT, task_draft created
3. `test_route_low_confidence_skip` — confidence=0.2 → SKIP
4. `test_route_exact_threshold_auto` — confidence=0.8 → AUTO
5. `test_route_exact_lower_bound_draft` — confidence=0.3 → DRAFT
6. `test_route_dedup_skip_overrides` — confidence=0.9 but dedup=SKIP → SKIP

**Coverage target:** ≥ 90%

**Commit:** `test(router): 6 unit tests, boundary conditions`

---

### T5.5 — Contract tests (C1–C5)

**Роль:** EA

**Что делаем:** Cross-module boundary тесты. Каждый проверяет, что output модуля A подходит как input модуля B.

1. **C1: extractor → classifier** — `extract()` output → `classify()` input. Fields present, types correct.
2. **C2: classifier → dedup** — `classify()` output → `check_dedup()` input. Title and source_document_id present.
3. **C3: dedup → router** — `DedupDecision` enum values match router expectations.
4. **C4: router → task_service** — AUTO route → `create_task_record()` succeeds with routed data.
5. **C5: router → task_drafts** — DRAFT route → `TaskDraft` inserted with all required fields.

**Done criteria:**
- 5 contract tests, все зелёные
- in-memory SQLite, mock `call_llm`
- Тесты в `tests/contract/`

**Commit:** `test(contract): C1-C5 cross-module boundary tests`

---

### T5.6 — Удалить v1 pipeline файлы

**Роль:** EA

**Что делаем:**
1. Удалить файлы:
   - `src/executive_cli/pipeline_engine.py` (521 LOC)
   - `src/executive_cli/ingest/email_pipeline.py` (406 LOC)
   - `src/executive_cli/ingest/meeting_pipeline.py` (365 LOC)
   - `src/executive_cli/ingest/dialogue_pipeline.py` (365 LOC)
   - `src/executive_cli/ingest/pipeline.py` (293 LOC)
   - `src/executive_cli/gtd_pipeline.py` (168 LOC)
   - `src/executive_cli/reflect_pipeline.py` (205 LOC)
   - `src/executive_cli/approval_gate.py` (204 LOC)
   - `src/executive_cli/metrics.py` (128 LOC) — перепишем позже
   - `src/executive_cli/review.py` (294 LOC)
   - `src/executive_cli/scrum_metrics.py` (215 LOC)
   - `src/executive_cli/sync_runner.py` (155 LOC)
   - `src/executive_cli/sync_service.py` (384 LOC)
2. Удалить соответствующие тесты:
   - `test_pipeline_engine.py`, `test_email_pipeline.py`, `test_meeting_pipeline.py`
   - `test_dialogue_pipeline.py`, `test_gtd_pipeline.py`, `test_reflect_pipeline.py`
   - `test_approval_gate.py`, `test_ingest_pipeline.py`
   - `test_weekly_review.py`, `test_scrum_metrics.py`
   - `test_sync_hourly.py`, `test_people_decisions_fts.py`
3. Grep: нет импортов удалённых модулей

**Done criteria:**
- `grep -r "pipeline_engine\|email_pipeline\|meeting_pipeline\|dialogue_pipeline\|approval_gate\|reflect_pipeline\|gtd_pipeline" src/` → 0 results
- Все оставшиеся тесты зелёные

**Commit:** `refactor: remove v1 pipeline code and related modules (~3500 LOC)`

---

### T5.7 — Реорганизовать тестовый каталог

**Роль:** EA

**Что делаем:**
1. Создать структуру:
   ```
   tests/
     conftest.py
     fixtures/
       emails.py
       golden_prompts/
       injection_attempts.py
     unit/
       test_extractor.py
       test_dedup.py
       test_router.py
       test_classifier.py
       test_task_service.py
       test_llm_gateway.py
       test_connectors.py
     contract/
       test_extract_classify.py
       test_classify_dedup.py
       test_dedup_router.py
       test_router_task_service.py
       test_router_task_drafts.py
     e2e/
       (пустой, заполним на Week 2)
   ```
2. Переместить unit тесты в `tests/unit/`
3. Переместить contract тесты в `tests/contract/`

**Done criteria:**
- `uv run pytest tests/unit/ -q` → green
- `uv run pytest tests/contract/ -q` → green
- `uv run pytest -q` → all green

**Commit:** `refactor(tests): reorganize into unit/contract/e2e structure`

---

### T5.8 — Quality gate: Day 5 (Week 1 milestone)

**Роль:** TL

```bash
cd apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-fail-under=80
```

**Milestone W1 checklist:**
- [ ] PostgreSQL Docker работает
- [ ] 14 таблиц в models.py
- [ ] db.py с dual backend (PostgreSQL/SQLite)
- [ ] task_service.py — 6+ тестов, coverage ≥ 90%
- [ ] connectors/imap.py — 5+ тестов
- [ ] llm_gateway.py — 9 тестов, coverage ≥ 70%
- [ ] extractor.py — 7 тестов, golden prompts, coverage ≥ 90%
- [ ] dedup.py — 6 тестов, coverage ≥ 90%
- [ ] classifier.py — 5 тестов, coverage ≥ 80%
- [ ] router.py — 6 тестов, coverage ≥ 90%
- [ ] Contract tests C1-C5 — green
- [ ] v1 pipeline code удалён (~3500 LOC)
- [ ] Тесты реорганизованы (unit/contract/e2e)
- [ ] llm/client.py удалён
- [ ] Overall coverage ≥ 80%
- [ ] 0 test failures

---

## Трассировка: задачи → документы

| Задача | D1 | D2 | D3 | D4 | D6 | D8 | D9 |
|--------|----|----|----|----|----|----|-----|
| T1.1 Docker | | | | ✓ | | | ✓ |
| T1.2 models | ✓ | | | ✓ | | | |
| T1.3 db | ✓ | | | ✓ | | | |
| T1.4 migration | | | | ✓ | | | ✓ |
| T1.5 psycopg2 | | | | ✓ | | | |
| T1.6 test init | | | | | | ✓ | |
| T2.1 task_svc | | ✓ | ✓ | | | | ✓ |
| T2.3 imap | | ✓ | ✓ | | | | ✓ |
| T3.1 llm_gw | | ✓ | ✓ | | ✓ | | |
| T3.2 rm llm/ | | | | | | | ✓ |
| T4.1 extractor | | ✓ | ✓ | | ✓ | | |
| T4.4 dedup | | ✓ | ✓ | | | | |
| T5.1 classifier | | ✓ | ✓ | | | | |
| T5.3 router | | ✓ | ✓ | | | | |
| T5.5 contracts | | ✓ | | | | ✓ | |
| T5.6 rm v1 | | | | | | | ✓ |

---

## Зависимости между задачами

```
T1.5 (psycopg2) ──┐
T1.1 (docker)  ────┼── T1.2 (models) ── T1.3 (db) ── T1.4 (migration) ── T1.6 (test init)
                   │
                   └── T2.1 (task_svc) ── T2.2 (test task_svc)
                   └── T2.3 (imap)     ── T2.4 (test imap)
                   └── T3.1 (llm_gw)  ── T3.3 (test llm_gw)
                       T3.2 (rm llm/)
                   └── T4.1 (extractor) ── T4.3 (test extractor)
                       T4.2 (fixtures)
                   └── T4.4 (dedup) ── T4.5 (test dedup)
                   └── T5.1 (classifier) ── T5.2 (test classifier)
                   └── T5.3 (router) ── T5.4 (test router)

T2.1 + T4.1 + T4.4 + T5.1 + T5.3 → T5.5 (contract tests)
T5.5 + T3.2 → T5.6 (rm v1 pipeline code)
T5.6 → T5.7 (reorganize tests)
T5.7 → T5.8 (milestone gate)
```

---

## Суммарные метрики

| Метрика | v1 (текущее) | v2 (после Week 1) |
|---------|--------------|-------------------|
| Source files | 36 | ~16 |
| Source LOC | 6 275 | ~1 600 |
| Test files | 28 | ~15 |
| Test LOC | 5 701 | ~1 200 |
| DB tables | 23 | 14 |
| CLI commands | 48 | TBD (Week 2) |
| Coverage | 80.89% | ≥ 80% |
| Commits | — | ~20 |
