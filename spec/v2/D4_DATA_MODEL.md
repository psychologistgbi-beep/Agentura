# D4. DATA_MODEL — PostgreSQL (Docker), ≤ 14 таблиц

## 1. Таблицы

### Core domain (6 таблиц)

| Table | Назначение | PK | Unique/Index | Retention |
|-------|-----------|-----|-------------|-----------|
| `settings` | Key-value конфиг | `key` | — | permanent |
| `tasks` | GTD задачи | `id` | — | permanent |
| `task_drafts` | Кандидаты на ревью | `id` | ix(status, confidence) | until approved/rejected |
| `busy_blocks` | Календарные блоки | `id` | uq(calendar_id, source, external_id) | permanent |
| `calendars` | Источники календаря | `id` | uq(slug) | permanent |
| `emails` | Email-заголовки (без body) | `id` | uq(source, external_id) | permanent |

### Supporting (4 таблицы)

| Table | Назначение | PK | Unique/Index | Retention |
|-------|-----------|-----|-------------|-----------|
| `task_email_links` | Связь task↔email | `id` | uq(task_id, email_id) | permanent |
| `ingest_documents` | Трекинг обработанных документов | `id` | uq(channel, source_ref) | permanent |
| `ingest_log` | Аудит решений ingest | `id` | ix(document_id) | 90 дней |
| `llm_call_log` | Каждый LLM-вызов | `id` | ix(correlation_id) | 30 дней |

### Reference (2 таблицы)

| Table | Назначение | PK | Retention |
|-------|-----------|-----|-----------|
| `areas` | Зоны ответственности | `id` | permanent |
| `projects` | Проекты (→ area) | `id` | permanent |

**Core + Supporting + Reference: 12 таблиц.**

### Planner tables (подтверждено: сохраняем)

| Table | Назначение | PK | Retention |
|-------|-----------|-----|-----------|
| `day_plans` | Результат planner на дату | `id` | permanent |
| `time_blocks` | Слоты в day_plan | `id` | permanent |

**Total: 14 таблиц** (12 + 2 planner).

### Исключено из MVP (было в v1)

| Таблица v1 | Причина удаления |
|-----------|------------------|
| `commitments` | Переусложнение для MVP. Задачи привязываются к project, не к commitment |
| `people`, `decisions` | People/decisions search — вторичная функция, не MVP |
| `weekly_reviews` | n8n + LLM может генерировать отчёт без отдельной таблицы |
| `sync_state` | IMAP cursor → в `settings` как `key=imap_last_uid` |
| `pipeline_runs`, `pipeline_events` | Pipeline Engine удалён. n8n = оркестратор |
| `approval_requests` | Заменён на `task_drafts.status = pending/approved/rejected` |

### Решение: PostgreSQL в Docker

**Причина перехода с SQLite:** пользователь считает, что БД стоит развернуть как отдельный сервис.

**Docker Compose:**
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
volumes:
  pgdata:
```

**SQLModel compatibility:** SQLModel поддерживает PostgreSQL через `create_engine("postgresql+psycopg2://...")`. Изменения в `db.py` минимальны — меняется только connection string.

**MUST:** для локальной разработки и тестов — in-memory SQLite (`sqlite://`). PostgreSQL = production.
**MUST:** Alembic migrations работают с обоими backends.

## 2. Ключевые модели (сохраняем из v1)

### Task
```
id | title | status(NOW/NEXT/WAITING/SOMEDAY/DONE/CANCELED) | priority(P1/P2/P3)
   | estimate_min | due_date | project_id(FK) | area_id(FK)
   | waiting_on | ping_at | created_at | updated_at
CHECK: estimate_min > 0
CHECK: WAITING → waiting_on IS NOT NULL AND ping_at IS NOT NULL
```

### Email (headers only — ADR-10: no body)
```
id | source | external_id | mailbox_uid | subject | sender
   | received_at | first_seen_at | last_seen_at | flags_json
UNIQUE: (source, external_id)
```

### TaskDraft (заменяет ApprovalRequest для create_task)
```
id | title | suggested_status | suggested_priority | estimate_min
   | confidence | rationale | dedup_flag
   | source_channel | source_document_id(FK) | source_email_id(FK)
   | status(pending/accepted/skipped) | created_at | reviewed_at
INDEX: (status, confidence)
```

### LLMCallLog
```
id | correlation_id | provider | model | prompt_hash
   | prompt_tokens | completion_tokens | latency_ms
   | status(success/error/timeout/fallback) | error | created_at
INDEX: correlation_id
```

### IngestDocument
```
id | channel | source_ref | title | status(pending/processed/failed)
   | items_extracted | created_at | processed_at
UNIQUE: (channel, source_ref)
```

## 3. Lifecycle и retention

| Данные | Запись | Чтение | Удаление |
|--------|--------|--------|----------|
| tasks | ingest → task_service | planner, CLI | manual only |
| task_drafts | ingest → router | CLI approve batch | after accept/reject |
| emails | IMAP sync | ingest | never (headers only, lightweight) |
| llm_call_log | llm_gateway | dash, metrics | 30-day rolling (n8n cron) |
| ingest_log | ingest | debug | 90-day rolling (n8n cron) |
| busy_blocks | CalDAV sync, CLI manual | planner | soft-delete (is_deleted) |

## Open questions

Нет. Все решения приняты:
- `day_plans` + `time_blocks` — сохраняем (14 таблиц total)
- `sync_state` — в `settings` как key
- PostgreSQL в Docker для production
- Миграция данных: не делаем, чистый старт
