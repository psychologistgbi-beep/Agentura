# D1. ARCH_OVERVIEW — Agentura v2 (Reset/MVP)

## 1. Цели

- **Бизнес-результат за 2 недели:** реальные письма из Yandex IMAP → задачи в SQLite → план дня.
- **Надёжность > простота > экономия.** Каждый компонент работает или явно падает с ошибкой. Нет silent failures.
- **Ollama-only для простых задач.** Локальная LLM (qwen2.5:7b, 18 GB RAM). Cloud API не используется для задач ассистента. Тщательная приёмка результата LLM обязательна.
- **n8n = оркестратор.** Cron, retry, webhook, error handling — вне Python-кода.
- **PostgreSQL в Docker.** Замена SQLite. Docker Compose: PostgreSQL + n8n.

## 2. Не-цели (запрещено в MVP)

- Telegram / web UI / мобильное приложение
- Отправка email (send/reply) — только read-only inbox
- Custom pipeline state machine (n8n заменяет)
- Governance > 3 ролей (EA, Architect, TL)
- Gate reports из 7 секций
- Больше 1 LLM-клиента в коде
- YAML/DSL для pipeline-определений
- Микросервисный деплой (Docker Compose с несколькими контейнерами)

## 3. Принципы

| # | Принцип | Правило |
|---|---------|---------|
| P1 | Один вызов — один результат | Каждая функция: input → output/error. Нет side-effect-функций длиннее 50 строк |
| P2 | Fail loud | Любая ошибка → exception + запись в лог. Никогда `pass` в `except` для бизнес-логики |
| P3 | Single source of truth | 1 LLM-клиент (`call_llm`). 1 task creator (`create_task_record`). 1 DB writer per entity |
| P4 | Test the money | Модули, генерирующие бизнес-ценность (extractor, dedup, planner): coverage ≥ 90%. Остальные: ≥ 70% |
| P5 | Минимум абстракций | Не создавать registry/engine/framework пока нет 3+ реальных use-case |

## 4. Границы системы

```
┌────────────────────────────────────────────┐
│                  n8n                        │
│  cron daily │ email trigger │ approval wh   │
└──────┬──────────────┬───────────┬──────────┘
       │ HTTP/exec    │           │
┌──────┴──────────────┴───────────┴──────────┐
│              CLI (execas)                   │
│  init · task capture · ingest email         │
│  daily · approve batch · dash               │
└──────┬──────────────────────────────────────┘
       │
┌──────┴──────────────────────────────────────┐
│           Domain Services                    │
│  ingest_service · task_service · planner     │
└──────┬──────────────────────────────────────┘
       │
┌──────┴──────┐  ┌────────────────────────────┐
│ LLM Gateway │  │    Connectors              │
│ call_llm()  │  │  IMAP (Yandex) · CalDAV    │
└─────────────┘  └────────────────────────────┘
       │                     │
┌──────┴─────────────────────┴────────────────┐
│     PostgreSQL (Docker, ≤14 tables)         │
└─────────────────────────────────────────────┘
```

## 5. Ключевой сценарий: email → tasks → plan day

```
1. n8n cron (07:00) → execas daily --date 2026-02-20
2. CLI → imap_connector.fetch_new_headers(since=cursor)
3. Для каждого нового email:
   a. call_llm(prompt=extract_prompt(subject, sender)) → [{title, confidence, ...}]
   b. classify(candidates, session) → resolved project/area/commitment
   c. dedup(title, session) → skip | flag
   d. route(confidence):
      ≥ 0.8 → create_task_record() автоматически
      0.3–0.79 → insert task_draft (pending review)
      < 0.3 → log + skip
   e. write ingest_log entry
4. CLI → planner.plan_day(date, variant="realistic")
5. CLI → print summary + "run `execas approve batch` if pending"
```

## 6. Компоненты и ответственность

| Компонент | Файл | LOC target | Ответственность |
|-----------|------|------------|-----------------|
| CLI | `cli.py` | < 400 | Typer, 6 команд, zero logic |
| LLM Gateway | `llm_gateway.py` | < 250 | `call_llm()`, fallback, logging, sanitisation |
| Ingest Service | `ingest_service.py` | < 200 | `ingest_email()`, `ingest_file()` — один модуль, параметр `channel` |
| Extractor | `extractor.py` | < 100 | prompt → LLM → parse JSON → `ExtractedCandidate[]` |
| Classifier | `classifier.py` | < 150 | resolve project/area/commitment hints |
| Dedup | `dedup.py` | < 100 | exact + Levenshtein match |
| Router | `router.py` | < 100 | confidence → auto/draft/skip |
| Task Service | `task_service.py` | < 80 | `create_task_record()`, validation |
| Planner | `planner.py` | < 500 | `plan_day()` — deterministic scheduling |
| IMAP Connector | `connectors/imap.py` | < 250 | fetch headers, incremental UID |
| CalDAV Connector | `connectors/caldav.py` | < 500 | fetch events |
| Models | `models.py` | < 200 | SQLModel classes, ≤ 12 tables |
| DB | `db.py` | < 60 | engine, init, settings |

**Total target: ~2 400 LOC** (vs 9 640 текущих).

## 7. Правило переиспользования

> При разработке микросервисов — сначала поиск существующих модулей, на их основе создавать дополнительную функциональность. Не писать новый модуль, пока не проверен текущий код на переиспользование.

## Open questions

Нет — всё определяется в D2–D9. Все вопросы интервью закрыты (см. INTERVIEW_QUESTIONS.md).
