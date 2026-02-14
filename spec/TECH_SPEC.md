# Executive Assistant — Architecture & MVP Spec (v0.1)

## 0) Context & goals (2-week outcomes)
We are building a personal Executive Assistant system with:
- Daily: generate 3 variants of a time-blocked day plan (minimal / realistic / aggressive) using GTD task states + calendar busy time.
- Weekly (Sunday): propose key weekly priorities based on both current inflow ("tekuchka") and strategic Year Commitments.
- Knowledge consolidation: capture People + Decisions as first-class entities; enable full-text search.

MVP aims to include Yandex Mail + Yandex Calendar integration via MCP-backed connectors (start with primary calendar and primary mailbox). If MCP is unavailable, ship manual fallbacks.

## 1) Non-goals for MVP
- Multi-calendar conflict resolution and dedup across accounts (we start with ONE primary calendar).
- A graphical UI (CLI first; later UI possible).
- Automatic rescheduling across participants’ calendars (we can suggest reschedule, not enforce).

## 2) High-level architecture
Three layers:
1) Skills layer (filesystem packages): reusable instructions/templates/examples (already in repo).
2) Data layer (SQLite): single source of truth for tasks, plans, calendar busy blocks, people, decisions, commitments.
3) Execution layer (CLI): commands to capture/triage tasks, sync calendar/email, produce plans and weekly review outputs.

LLM usage:
- `plan day` is **deterministic** (no LLM); variant selection and task ranking use fixed rules.
- LLM may be used later for: weekly review narrative, drafting follow-ups, and future "smart suggest" features.
- The system state remains in SQLite; any LLM output must be translated into explicit DB updates by the Executive Assistant (single writer).

## 3) Time model & timezone
- Primary timezone: Europe/Moscow.
- All CLI inputs/outputs are interpreted in Europe/Moscow unless explicitly specified.
- **Storage format (ADR-01):** store all datetimes as ISO-8601 strings with explicit offset (e.g. `2026-02-15T10:00:00+03:00`). SQLite column type `TEXT`.
- Comparison/sorting: do not rely on TEXT ordering across mixed offsets; normalize via application code where needed.
- Conversions must be tested (roundtrip coverage).

## 4) Scheduling constraints (initial values, user-configurable)
- Planning window: every day 07:00–19:00.
- Lunch: default 12:00, duration 60 minutes, movable deterministically if conflicts.
- Minimum focus block: 30 minutes.
- Buffer policy: a single `buffer_min` setting (default **5** minutes), applied between adjacent scheduled blocks.

All these values must be stored in DB settings and modifiable via CLI.

## 5) GTD task model
Statuses (enum):
- NOW, NEXT, WAITING, SOMEDAY, DONE, CANCELED

Task fields (minimum):
- title (string)
- status (enum)
- project_id (FK)
- area_id (FK)
- commitment_id (nullable FK)
- priority (P1/P2/P3)
- estimate_min (int, required)
- due_date (date, nullable)
- next_action (string, optional)
- waiting_on (string, required if WAITING)
- ping_at (datetime, required if WAITING)
- created_at, updated_at

Projects/Areas:
- Implement as reference tables (not free-text).

## 6) Commitments (from Strategic Contract 2026 v1.1)
Persist Year Commitments 2026:
- YC-1 (D3): by 31.12.2026 raised >= 25M RUB investments in a venture project where user is key initiator/founder.
- YC-2 (D5): by 31.12.2026 created a series of graphic art objects and commercialized them.
- YC-3 (D4): by 31.12.2026 spent >= 4 weeks in an English-speaking professional environment with recorded results in English.

Commitment fields:
- id (YC-1)
- title
- metric / definition_of_done
- due_date
- difficulty
- notes/evidence

## 7) Knowledge consolidation (MVP scope)
Entities (as implemented in DB):
- People: name, role, context, created_at, updated_at
- Decisions: title, body, decided_date, created_at, updated_at

Full-text search:
- SQLite FTS5 for People + Decisions (MATCH queries via CLI).

## 8) Calendar integration (Yandex) — MVP design
Start with ONE primary calendar.
- Preferred: MCP connector talking CalDAV (Yandex supports CalDAV).
- If MCP is unavailable: manual busy add/list remains MVP-complete.

Busy blocks:
- Stored as raw rows (merge-on-read per ADR-03).
- DB-level invariant: end_dt must be after start_dt (enforced by CHECK constraint).

## 9) Email integration (Yandex) — MVP design (planned/stub)
Target: read-only sync of inbox metadata + ability to create follow-up tasks from emails.
- Preferred: MCP connector via IMAP (Yandex supports IMAP).
- Data model for emails is planned (may be delivered as stub first).
- No hard dependency for plan-day/weekly-review correctness.

## 10) CLI contract (apps/executive-cli)
Executable name: execas

Core commands:
- execas init
  - creates SQLite DB, runs migrations, seeds primary calendar + default settings (timezone=Europe/Moscow)
- execas config show
- execas config set <key> <value>
  Keys include planning_start, planning_end, lunch_start, lunch_duration_min, buffer_min, timezone, min_focus_block_min

Busy blocks:
- execas busy add --date YYYY-MM-DD --start HH:MM --end HH:MM --title "..."
- execas busy list --date YYYY-MM-DD

Areas & Projects:
- execas area add "name"
- execas area list
- execas project add "name" [--area "area_name"]
- execas project list

Commitments:
- execas commitment add --id YC-N --title "..." --metric "..." --due YYYY-MM-DD --difficulty DN [--notes "..."]
- execas commitment list
- execas commitment import   (seed YC-1..YC-3 from spec; idempotent)

Tasks:
- execas task capture "title" --estimate 30 --priority P2 [--project X] [--area Y] [--commitment YC-1]
  - default status is NEXT
- execas task list [--status NOW] [--due YYYY-MM-DD]
- execas task move <task_id> --status NOW|NEXT|WAITING|SOMEDAY|DONE|CANCELED
- execas task done <task_id>
- execas task waiting <task_id> --on "Person/Thing" --ping "YYYY-MM-DD HH:MM"

People (FTS):
- execas people add [NAME] [--name "NAME"] [--role "..."] [--context "..."]
- execas people search "query" (FTS)

Decisions (FTS):
- execas decision add [TITLE] [--title "TITLE"] [--body "..."] [--date YYYY-MM-DD]
- execas decision search "query" (FTS)

Planning:
- execas plan day --date YYYY-MM-DD --variant minimal|realistic|aggressive
Outputs:
- Print a time-block schedule with timestamps and block type.
- Also store day_plans + time_blocks in DB.

## 11) Planning algorithm (deterministic)
Inputs:
- planning window settings for date
- busy blocks for date (merged & sorted)
- lunch block (movable)
- tasks in NOW (primary candidates; planner uses NOW-only and prints hint if none)
- constraints: min_focus_block_min, buffer_min

Steps:
1) Build free windows by subtracting merged busy blocks from planning window.
2) Reserve lunch: if lunch overlaps busy, shift deterministically to nearest feasible midday slot.
3) Rank tasks deterministically (priority + commitment + due urgency).
4) Fill variant-specific % of FREE time (after busy+lunch):
   - minimal: <=50%
   - realistic: ~75%
   - aggressive: ~95%
5) Insert buffer_min between blocks.
6) Output time_blocks with types: busy, focus, admin, lunch, buffer.
7) Rationale: selected tasks, didn’t fit, and suggestions (e.g., full day busy).

Out of scope:
- LLM-based planning.
- Task splitting (no split by default).

Edge cases:
- Day fully busy -> output only busy + suggestions.
- Tiny gaps < min_focus_block -> do not schedule focus; represent as admin/buffer.
- Overlapping/adjacent busy blocks -> merged on read.

## 12) Data schema (SQLite)
Tables (minimum):
- settings(key TEXT PRIMARY KEY, value TEXT)
- areas(id, name UNIQUE)
- projects(id, name UNIQUE, area_id FK nullable)
- commitments(id TEXT PRIMARY KEY, title, metric, due_date, difficulty, notes)
- tasks(...)
- calendars(id, slug UNIQUE, name, timezone)
- busy_blocks(id, calendar_id FK, start_dt TEXT, end_dt TEXT, title TEXT, CHECK end_dt>start_dt)
- day_plans(id, date, variant, created_at, source, UNIQUE(date,variant))
- time_blocks(id, day_plan_id FK, start_dt, end_dt, type, task_id nullable, label)
- people(id, name, role, context, created_at, updated_at)
- decisions(id, title, body, decided_date, created_at, updated_at)
- emails(...) (planned)

FTS (ADR-04) as implemented:
- people_fts(name, role, context) — maintained via triggers
- decisions_fts(title, body) — maintained via triggers

Day plan upsert policy (ADR-05):
- Re-running `plan day` for an existing (date, variant) replaces the previous plan (DELETE + INSERT).

## 13) Quality gates
- Unit tests for:
  - time calculations + merging busy blocks
  - planning invariants
  - FTS search basic functionality
- Coverage gate: `pytest --cov=executive_cli --cov-fail-under=80`
- CLI --help works for all commands.
- Migrations reproducible from empty DB.

## 14) Deliverables in 2 weeks
Milestone 1: Bootstrap + config + schema + manual busy add/list.
Milestone 2: Tasks CRUD + projects/areas + commitments import.
Milestone 3: Plan day (3 variants) producing time_blocks and rationale output.
Milestone 4: Yandex sync stubs via MCP (calendar + email), with fallback to manual.
Milestone 5: Weekly review output (Sunday).

## 15) Роль Business Coach (предусмотрено, не в MVP)
Цель: отдельная роль (LLM-агент) для коучинговых интервью со мной и подготовки предложений по задачам/приоритетам, связанным с Year Commitments и текущей операционкой.

Границы ответственности:
- Business Coach общается со мной напрямую (интервью, уточнение контекста, критериев успеха, ограничений).
- Business Coach передаёт Executive Assistant только рекомендации (предложения), но НЕ изменяет состояние системы напрямую.
- Executive Assistant является единственным writer и источником правды: только он пишет в SQLite (создаёт/обновляет задачи, статусы, связи, планы).

Интеграция (без формального протокола на этом этапе):
- Coach -> Executive Assistant: предложения по созданию задач, изменению статусов (например NEXT->NOW), уточнению приоритетов/оценок, weekly focus (5–10 пунктов).
- Применение изменений: вручную/через подтверждение пользователя. Формальный протокол ChangeSet/apply может быть добавлен позже.