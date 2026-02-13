# Executive Assistant — Architecture & MVP Spec (v0.1)

## 0) Context & goals (2-week outcomes)
We are building a personal Executive Assistant system with:
- Daily: generate 3 variants of a time-blocked day plan (minimal / realistic / aggressive) using GTD task states + calendar busy time.
- Weekly (Sunday): propose key weekly priorities based on both current inflow ("tekuchka") and strategic Year Commitments.
- Knowledge consolidation: capture People + Decisions as first-class entities; enable full-text search.

MVP must include Yandex Mail + Yandex Calendar integration via MCP-backed connectors (start with primary calendar and primary mailbox).

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
- LLM is used to generate proposals (daily plan variants, weekly priorities, drafting follow-ups).
- The system state remains in SQLite; LLM output must be translated into explicit DB updates.

## 3) Time model & timezone
- Primary timezone: Europe/Moscow.
- All CLI inputs/outputs are interpreted in Europe/Moscow unless explicitly specified.
- Store timestamps as timezone-aware ISO strings (or SQLite datetime + offset); conversions must be tested.

## 4) Scheduling constraints (initial values, user-configurable)
- Planning window: every day 07:00–19:00 (life planning: business + hobby + family + rest).
- Quiet window: 19:00–07:00 (no scheduled work blocks by default; can be overridden later).
- Lunch: default 12:00, duration 60 minutes, movable.
- Minimum focus block: 30 minutes INCLUDING 5 minutes switching overhead.
- Buffer policy: TBD clarification from earlier; for MVP use a single fixed buffer_minutes setting, applied between non-busy blocks and around meetings. Allow later extension per block type.

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
- next_action (string, nullable but strongly recommended)
- waiting_on (string, required if WAITING)
- ping_at (datetime, required if WAITING)
- created_at, updated_at

Projects/Areas:
- Implement as reference tables (not free-text) per requirement.

## 6) Commitments (from Strategic Contract 2026 v1.1)
Persist:
- North Star 2029 statements (as text)
- Year Commitments 2026:
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
Entities:
- People (critical)
- Decisions (critical)
Also allow generic Notes later.

Full-text search:
- Enable SQLite FTS5 for People + Decisions (at least for names/roles/notes and decision summaries).

## 8) Calendar integration (Yandex) — MVP design
Start with ONE primary calendar.
Integration method:
- Prefer MCP connector that talks CalDAV (Yandex supports CalDAV sync). If MCP not available, allow manual busy add.
- Data model stores busy blocks normalized in busy_blocks table.

CalDAV note:
- Yandex provides CalDAV sync endpoints for calendar clients; treat as external source of busy time. (Implementation specifics in integration layer.)

## 9) Email integration (Yandex) — MVP design
MVP: read-only sync of inbox metadata + ability to create follow-up tasks from emails.
- Use MCP connector that talks IMAP (Yandex supports IMAP).
- Store minimal email headers/snippets and link tasks to email_message records.

## 10) CLI contract (apps/executive-cli)
Executable name: execas

Core commands:
- execas init
  - creates SQLite DB, runs migrations, seeds primary calendar + default settings (timezone=Europe/Moscow)
- execas config show
- execas config set <key> <value>
  Keys include planning_window, lunch_start, lunch_duration_min, buffer_min, timezone, min_focus_block_min

Calendar:
- execas calendar sync   (via MCP CalDAV; updates busy_blocks)
- execas busy add --date YYYY-MM-DD --start HH:MM --end HH:MM --title "..."
- execas busy list --date YYYY-MM-DD

Tasks:
- execas task capture "title" --estimate 30 --priority P2 [--project X] [--area Y] [--commitment YC-1]
- execas task list [--status NOW] [--date YYYY-MM-DD]
- execas task move <task_id> --status NOW|NEXT|WAITING|SOMEDAY|DONE|CANCELED
- execas task done <task_id>
- execas task waiting <task_id> --on "Person/Thing" --ping "YYYY-MM-DD HH:MM"

People:
- execas people add --name "..." [--org "..."] [--role "..."] [--notes "..."]
- execas people search "query" (FTS)
Decisions:
- execas decision add --title "..." --context "..." --choice "..." [--consequences "..."]
- execas decision search "query" (FTS)

Planning:
- execas plan day --date YYYY-MM-DD --variant minimal|realistic|aggressive
Outputs:
- Print a time-block schedule with timestamps and block type.
- Also store day_plan + time_blocks in DB.

Weekly:
- execas review week --week YYYY-Www
  - Sunday ritual: propose weekly priorities (top 5–10) derived from commitments + inflow + deadlines + waiting pings.
  - Output as markdown, store summary in DB.

## 11) Planning algorithm (deterministic)
Inputs:
- planning window settings for date
- busy blocks for date (merged & sorted)
- lunch block (movable, but default reserved at lunch_start; algorithm may shift if conflicts)
- tasks in NOW (primary candidates) + NEXT (fallback)
- constraints: min_focus_block_min

Steps:
1) Build free windows by subtracting busy blocks from planning window.
2) Reserve lunch (if enabled): if lunch overlaps busy, shift within nearest free window around mid-day.
3) For each variant:
   - minimal: schedule the smallest set of highest-value tasks (prefer those linked to commitments + due soon).
   - realistic: schedule a balanced set with buffers and at least one commitment-linked task if available.
   - aggressive: schedule realistic + stretch tasks, but do not eliminate buffers entirely.
4) Use estimate_min to fit tasks into blocks; split tasks only if explicitly allowed (TBD for MVP: default "no split").
5) Output time_blocks with types: busy, focus, admin, lunch, buffer.
6) Provide a short rationale (why these tasks, what didn't fit, suggested reschedules if needed).

Edge cases:
- Day fully busy -> output only busy + suggested reschedule proposals.
- Tiny gaps < min_focus_block -> mark as buffer/admin, do not schedule focus.
- Overlapping busy blocks -> merge.

## 12) Data schema (SQLite)
Tables (minimum):
- settings(key TEXT PRIMARY KEY, value TEXT)
- areas(id, name UNIQUE)
- projects(id, name UNIQUE, area_id FK nullable)
- commitments(id TEXT PRIMARY KEY, title, metric, due_date, difficulty, notes)
- tasks(...)
- calendars(id, slug UNIQUE, name, timezone)
- busy_blocks(id, calendar_id FK, start_dt, end_dt, title)
- day_plans(id, date, variant, created_at, assumptions)
- time_blocks(id, day_plan_id FK, start_dt, end_dt, type, task_id nullable, label)
- people(id, name, org, role, notes, created_at)
- decisions(id, title, context, choice, consequences, created_at)
- emails(id, message_id, subject, from, received_at, snippet, raw_ref)

FTS:
- people_fts
- decisions_fts

## 13) Quality gates
- Unit tests for:
  - time calculations + merging busy blocks
  - planning invariants
  - FTS search basic functionality
- CLI --help works for all commands.
- Migrations reproducible from empty DB.

## 14) Deliverables in 2 weeks
Milestone 1: Bootstrap + config + schema + manual busy add/list.
Milestone 2: Tasks CRUD + projects/areas + commitments import.
Milestone 3: Plan day (3 variants) producing time_blocks and markdown output.
Milestone 4: Yandex sync stubs via MCP (calendar + email), with fallback to manual.
Milestone 5: Weekly review output (Sunday).