# D9. MIGRATION_PLAN — От v1 к v2 за 4 недели

## 1. Стратегия: Reset с селективным копированием

**Не рефакторинг.** Новый `executive_cli/` с чистой структурой. Полезный код из v1 копируется файл-по-файл после ревью.

### Что копируем (сохраняет ценность)

| Файл v1 | Файл v2 | Действие | LOC |
|----------|---------|----------|-----|
| `task_service.py` | `task_service.py` | copy as-is | 81 |
| `planner.py` | `planner.py` | copy, minor cleanup | ~500 |
| `connectors/imap.py` | `connectors/imap.py` | copy, удалить BODY fetch | ~250 |
| `connectors/caldav.py` | `connectors/caldav.py` | copy as-is | ~500 |
| `models.py` | `models.py` | rewrite: оставить 12 таблиц, удалить 10 лишних | ~200 |
| `db.py` | `db.py` | simplify: убрать pipeline settings | ~60 |
| `llm_gateway.py` | `llm_gateway.py` | rewrite: убрать `llm/client.py`, один путь | ~250 |
| `extractor.py` | `extractor.py` | rewrite: убрать Pipeline Engine dependency | ~100 |

### Что удаляем (не приносит ценности)

| Файл/каталог v1 | LOC | Причина удаления |
|-----------------|-----|------------------|
| `pipeline_engine.py` | 521 | Framework без use-case. n8n заменяет |
| `email_pipeline.py` | 406 | Дублирует ingest_service. n8n orchestrates |
| `meeting_pipeline.py` | 365 | Дублирует ingest_service |
| `dialogue_pipeline.py` | 365 | Дублирует ingest_service |
| `gtd_pipeline.py` | 168 | n8n + execas daily заменяет |
| `reflect_pipeline.py` | 205 | Post-MVP |
| `approval_gate.py` | 124 | Заменён на task_drafts + CLI approve |
| `llm/client.py` | 214 | Дубликат llm_gateway. Удаляем |
| `llm/__init__.py` | — | Удаляем каталог llm/ |
| `metrics.py` | 128 | Перепишем проще для dash |

**Total удаляемого: ~2 500 LOC** (26% codebase).

### Что пишем заново

| Файл v2 | LOC target | Описание |
|----------|-----------|----------|
| `ingest_service.py` | ~200 | Единый ingest: email + file через `channel` параметр |
| `classifier.py` | ~150 | Из extractor, разделение ответственности |
| `dedup.py` | ~100 | Из ingest, самостоятельный модуль |
| `router.py` | ~100 | Confidence → auto/draft/skip |
| `metrics.py` | ~80 | pipeline_stats + llm_stats для dash |
| `cli.py` | ~400 | Rewrite: 6 команд, zero logic |

## 2. Что делаем с тестами v1

### Тесты, которые сохраняем (адаптируем)

| Тестовый файл v1 | Причина |
|------------------|---------|
| `test_task_service.py` | task_service копируется as-is |
| `test_planner.py` | planner копируется |
| `tests/conftest.py` | db fixtures полезны |
| `test_db.py` | init/settings тесты |

### Тесты, которые удаляем

| Тестовый файл v1 | Причина |
|------------------|---------|
| `test_pipeline_engine.py` | Pipeline Engine удалён |
| `test_email_pipeline.py` | Pipeline-файлы удалены |
| `test_meeting_pipeline.py` | Pipeline-файлы удалены |
| `test_dialogue_pipeline.py` | Pipeline-файлы удалены |
| `test_gtd_pipeline.py` | Pipeline-файл удалён |
| `test_reflect_pipeline.py` | Pipeline-файл удалён |
| `test_approval_gate.py` | approval_gate удалён |

### Тесты, которые пишем заново

Согласно D8_TESTING_STRATEGY: unit (60+), contract (8), e2e (3).

## 3. Миграция данных

**Решение: миграцию не делаем. Чистый старт.**

v2 стартует с пустой PostgreSQL. Данные из v1 SQLite не переносятся.

Причины:
- Schema принципиально отличается (14 таблиц вместо 22, PostgreSQL вместо SQLite)
- Объём данных v1 минимален
- Чистый старт проще и надёжнее

### База данных v2: PostgreSQL в Docker

```yaml
# docker-compose.yml
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
      - postgres

volumes:
  pgdata:
  n8n_data:
```

**MUST:** `execas init` создаёт схему через Alembic migrations (PostgreSQL).
**MUST:** для тестов — in-memory SQLite (`sqlite://`). SQLModel совместим с обоими backends.

## 4. План по неделям

### Неделя 1: Фундамент

| День | Задача | Артефакт | Done criteria |
|------|--------|----------|---------------|
| 1 | Docker Compose (PostgreSQL + n8n) | `docker-compose.yml` | `docker compose up -d` → PostgreSQL + n8n running |
| 1 | Новый `models.py` (14 таблиц) | `models.py` < 200 LOC | `execas init` создаёт все таблицы в PostgreSQL, тесты проходят |
| 1 | Новый `db.py` | `db.py` < 80 LOC | engine init + settings CRUD + PostgreSQL/SQLite switch |
| 2 | Copy `task_service.py` + tests | 81 LOC + tests | `create_task_record()` работает, coverage ≥ 90% |
| 2 | Copy `connectors/imap.py` | ~250 LOC | fetch_headers() работает с mock |
| 3 | Rewrite `llm_gateway.py` | < 250 LOC | call_llm() с Ollama + fallback, coverage ≥ 70% |
| 3 | Delete `llm/client.py` | — | Нет импортов llm.client нигде |
| 4 | New `extractor.py` | < 100 LOC | extract() → golden prompt fixtures pass |
| 4 | New `dedup.py` | < 100 LOC | exact + Levenshtein, coverage ≥ 90% |
| 5 | New `classifier.py` + `router.py` | < 250 LOC total | contract tests C1-C5 pass |

**Milestone W1:** `task_service`, `llm_gateway`, `extractor`, `dedup`, `classifier`, `router` — все работают, unit tests pass, coverage ≥ 80% overall.

### Неделя 2: Ingest + CLI

| День | Задача | Артефакт | Done criteria |
|------|--------|----------|---------------|
| 1 | New `ingest_service.py` | < 200 LOC | `ingest_emails()` flow: fetch → extract → classify → dedup → route |
| 2 | Contract tests C6-C8 | 8 contract tests | Все contract тесты pass |
| 2 | Copy `connectors/caldav.py` | ~500 LOC | fetch_events() работает с mock |
| 3 | Rewrite `cli.py` | < 400 LOC | `execas init`, `execas task capture`, `execas ingest email` |
| 4 | Copy `planner.py` + adapt | ~500 LOC | `execas daily` работает end-to-end |
| 5 | `execas approve batch` + `execas dash` | CLI complete | E2E tests E1-E3 pass |

**Milestone W2:** `execas daily --date 2026-02-20` работает от CLI до результата в SQLite. Все 6 команд реализованы. E2E tests pass. Coverage ≥ 80%.

### Неделя 3: n8n + Integration

| День | Задача | Артефакт | Done criteria |
|------|--------|----------|---------------|
| 1 | n8n Workflow: Daily GTD | n8n export JSON | Cron → execas daily → log success |
| 2 | n8n Workflow: Email Ingest On-Demand | n8n export JSON | Webhook → execas ingest → notify |
| 3 | n8n Workflow: Approval Reminder | n8n export JSON | Cron → count pending → notify |
| 3 | n8n Workflow: LLM Log Cleanup | n8n export JSON | Cron → DELETE old rows |
| 4 | Integration test: real IMAP (Yandex) | Manual test log | 10 emails → tasks/drafts в DB |
| 5 | Integration test: real Ollama | Manual test log | extractor → valid JSON output |

**Milestone W3:** n8n workflows deployed. Real IMAP → real Ollama → tasks в PostgreSQL. Daily pipeline runs unattended.

### Неделя 4: Hardening + Cleanup

| День | Задача | Артефакт | Done criteria |
|------|--------|----------|---------------|
| 1 | Prompt injection tests | 5+ injection fixtures pass | Extractor rejects injection payloads |
| 2 | Edge cases: empty inbox, Ollama down, IMAP timeout | Tests pass | Graceful errors, no crashes |
| 3 | `metrics.py` + `execas dash` polish | Dash output readable | llm_stats + pipeline_stats correct |
| 4 | Delete all v1 pipeline files | Git diff shows removal | No imports of deleted modules |
| 5 | Final cleanup: docs, README, CHANGELOG | Updated docs | `uv run pytest --cov-fail-under=80` pass |

**Milestone W4:** v2 complete. All v1 pipeline code removed. Tests green. Coverage ≥ 80%. n8n runs daily without intervention.

## 5. Критерии "Done" (v2 MVP)

| # | Критерий | Как проверить |
|---|----------|---------------|
| D1 | `execas daily` обрабатывает реальные email из Yandex IMAP | Запустить с реальным IMAP, проверить tasks в DB |
| D2 | Задачи создаются по confidence routing (auto/draft/skip) | Проверить task_drafts с разным confidence |
| D3 | `execas approve batch` работает интерактивно | Запустить, одобрить/отклонить 3 draft |
| D4 | `execas dash` показывает статистику | Запустить после ingest |
| D5 | Ollama = default LLM, fallback на Anthropic | Остановить Ollama → проверить fallback |
| D6 | n8n Daily cron запускается в 07:00 | Проверить n8n execution log |
| D7 | Coverage ≥ 80%, все тесты зелёные | `uv run pytest --cov-fail-under=80` |
| D8 | Нет `pipeline_engine`, `*_pipeline.py`, `llm/client.py` | `grep -r "pipeline_engine\|email_pipeline\|llm.client" src/` → 0 results |
| D9 | ≤ 12 таблиц в models.py | Подсчёт `class.*SQLModel.*table=True` |
| D10 | Total LOC ≤ 2 500 | `find src/ -name "*.py" | xargs wc -l` |

## 6. Риски и mitigation

| Риск | Вероятность | Impact | Mitigation |
|------|-------------|--------|------------|
| Ollama quality недостаточна для extraction | Medium | High | Fallback на Anthropic. Golden prompt тесты покажут рано |
| IMAP connector ломается на edge cases (encodings, empty subjects) | Medium | Medium | Copy из v1 = battle-tested. Добавить encoding tests |
| planner.py слишком связан с v1 models | Low | High | Copy early (Week 1 Day 5), адаптировать imports |
| n8n не установлен / несовместимая версия | Low | Medium | n8n self-hosted via Docker, pin version |
| PostgreSQL Docker не стартует / port conflict | Low | Low | Pin postgres:17-alpine, check port 5432 free |

## 7. Rollback plan

Если v2 не достигает Done criteria к концу недели 4:

1. v1 код остаётся в git history (не удаляется до milestone W4)
2. v1 SQLite файл сохраняется (информационно, миграция не планируется)
3. Fallback: использовать v1 + manual task capture до fix

**MUST NOT:** удалять v1 код из git раньше milestone W2 (CLI complete).

## Open questions

Нет. Все решения приняты:
1. n8n — нет, Docker Compose на неделе 3 (вместе с PostgreSQL)
2. Миграция данных — не делаем, чистый старт
3. Real IMAP тестирование — разработчик с доступом к Yandex аккаунту
