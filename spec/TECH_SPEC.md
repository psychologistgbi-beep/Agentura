# Executive Assistant — Architecture & MVP Spec (v0.1, repo-aligned)

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
2) Data layer (SQLite): single source of truth for tasks, plans, calendar busy blocks, people, decisions, commitments, weekly reviews.
3) Execution layer (CLI): commands to capture/triage tasks, sync calendar/email, produce plans and weekly review outputs.

LLM usage:
- `plan day` is deterministic (no LLM).
- LLM may be used later for narrative/drafting and “smart suggest”, BUT system state remains in SQLite; LLM output must be translated into explicit DB updates.

## 3) Time model & timezone
- Primary timezone: Europe/Moscow.
- All CLI inputs/outputs interpreted in Europe/Moscow unless explicitly specified.
- Storage format: datetimes stored as ISO-8601 strings with explicit offset, in SQLite TEXT (e.g. `2026-02-15T10:00:00+03:00`).
- All DB read/write for datetimes must go through timeutil helpers (`dt_to_db`, `db_to_dt`, parse helpers). Conversions covered by tests.

## 4) Scheduling constraints (initial values, user-configurable)
Stored in settings, editable via CLI:
- planning_start: 07:00
- planning_end: 19:00
- lunch_start: 12:00
- lunch_duration_min: 60
- buffer_min: 5
- min_focus_block_min: 30
- timezone: Europe/Moscow

Policy:
- buffer_min applied between adjacent scheduled blocks.
- min_focus_block_min is minimum focus block duration; gaps smaller than this are never used for focus.

## 5) GTD task model
Statuses (enum):
- NOW, NEXT, WAITING, SOMEDAY, DONE, CANCELED

Minimum fields:
- title (string)
- status (enum)
- project_id (FK, nullable)
- area_id (FK, nullable)
- commitment_id (nullable FK)
- priority (P1/P2/P3)
- estimate_min (int, required)
- due_date (date, nullable)
- next_action (string, optional)
- waiting_on (string, required if WAITING)
- ping_at (datetime, required if WAITING)
- created_at, updated_at

Key behavior (repo-aligned):
- `task capture` default status = NEXT.
- Planner schedules ONLY NOW tasks.
- Weekly review shows Action list: NOW + WAITING, and separately proposes NEXT → NOW.

## 6) Commitments (Strategic Contract 2026 v1.1)
Persist Year Commitments 2026 (seeded by `execas commitment import`):
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

Note: due_date may be coarse (end of year). Weekly review should still produce “off-track” nudges using recency of task creation linked to commitments.

## 7) Knowledge consolidation (MVP scope)
Entities (repo-aligned):
- People: (name, role, context, created_at, updated_at) with FTS5 over name/role/context.
- Decisions: (title, body, decided_date, created_at, updated_at) with FTS5 over title/body.

No org/notes/choice/consequences fields in MVP schema (can be added later via migration).

## 8) Calendar integration (Yandex) — MVP design
Start with ONE primary calendar.

Integration method:
- Prefer MCP connector that talks CalDAV.
- If MCP not available, allow manual busy add/list.

Busy blocks:
- Stored raw in busy_blocks (merge-on-read).
- Busy interval integrity enforced at DB layer: end_dt must be strictly after start_dt.

Observation:
- MVP target cadence: sync/observe calendar ~1x/hour on laptop.

## 9) Email integration (Yandex) — MVP design
MVP: read-only sync of inbox metadata + ability to create follow-up tasks from emails.
- Prefer MCP connector (IMAP/Exchange capability depending on account).
- Security: credentials never stored in repo; use environment variables and local-only secrets (.env excluded from git).

## 10) CLI contract (apps/executive-cli)
Executable: execas

Core:
- execas init
- execas config show
- execas config set <key> <value

Busy:
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
- execas commitment import

Tasks:
- execas task capture "title" --estimate 30 --priority P2 [--project X] [--area Y] [--commitment YC-1] [--due YYYY-MM-DD]
- execas task list [--status NOW] [--due YYYY-MM-DD]
- execas task move <task_id> --status NOW|NEXT|WAITING|SOMEDAY|DONE|CANCELED
- execas task done <task_id>
- execas task waiting <task_id> --on "Person/Thing" --ping "YYYY-MM-DD HH:MM"

People (repo-aligned):
- execas people add [NAME] [--name "NAME"] [--role "..."] [--context "..."]
- execas people search "query" (FTS5)

Decisions (repo-aligned):
- execas decision add [TITLE] [--title "TITLE"] [--body "..."] [--date YYYY-MM-DD]
- execas decision search "query" (FTS5)

Planning:
- execas plan day --date YYYY-MM-DD --variant minimal|realistic|aggressive
Output:
- Prints time-block schedule with timestamps and block type.
- Stores day_plans + time_blocks in DB (replace-on-rerun per (date, variant)).

Weekly:
- execas review week --week YYYY-Www
Output:
- Markdown weekly review persisted to DB.
- Action list: NOW + WAITING only.
- Proposals: NEXT → NOW separate section.

## 11) Planning algorithm (deterministic; repo-aligned)
Inputs:
- settings: planning window, lunch, buffer, min_focus_block
- busy blocks for date (merged & sorted)
- tasks in NOW only

Steps:
1) Build free windows = planning window minus merged busy.
2) Reserve lunch: default slot at lunch_start, shift deterministically if busy (nearest feasible midday slot; earlier on tie). If no feasible slot → lunch skipped with note.
3) Rank NOW tasks deterministically.
4) Fill variant-specific % of FREE time (after busy+lunch):
   - minimal: <=50%
   - realistic: ~75%
   - aggressive: ~95%
5) Fit tasks as single focus blocks (no split).
6) Emit full timeline of blocks: busy, lunch, focus, buffer, admin.
7) Rationale: selected tasks, didn’t fit (with deterministic reason), and hints for edge cases:
   - If no NOW tasks: print explicit hint to move NEXT → NOW.
   - If day fully busy: print suggestion to carry tasks to tomorrow / reduce variant.

## 12) Data schema (SQLite, MVP)
Tables (minimum):
- settings(key TEXT PRIMARY KEY, value TEXT)
- areas(id, name UNIQUE)
- projects(id, name UNIQUE, area_id FK nullable)
- commitments(id TEXT PRIMARY KEY, title, metric, due_date, difficulty, notes)
- tasks(...)
- calendars(id, slug UNIQUE, name, timezone)
- busy_blocks(id, calendar_id FK, start_dt TEXT, end_dt TEXT, title TEXT, CHECK end_dt > start_dt)
- day_plans(id, date TEXT, variant TEXT, created_at TEXT, source TEXT, UNIQUE(date, variant))
- time_blocks(id, day_plan_id FK, start_dt TEXT, end_dt TEXT, type TEXT, task_id nullable, label TEXT)
- people(id, name, role, context, created_at, updated_at) + people_fts (FTS5 + triggers)
- decisions(id, title, body, decided_date, created_at, updated_at) + decisions_fts (FTS5 + triggers)
- weekly_reviews(id, week TEXT UNIQUE, created_at TEXT, body_md TEXT)

Email tables may be added later (TASK 11+), keep secrets out of repo.

## 13) Quality gates (repo-aligned)
- Unit tests for:
  - timeutil roundtrip + parsing strictness
  - merge-on-read busy logic (overlap + adjacency)
  - planning invariants (variants, lunch shift, tiny gap, determinism, full-busy, no-NOW hint)
  - FTS People/Decisions basic behavior
  - weekly review determinism + replace-on-rerun
- Coverage gate: pytest-cov with --cov-fail-under=80
- Migrations reproducible from empty DB
- CLI --help works for all commands

## 14) Business Coach role ( предусмотрено, не в MVP)
Purpose: LLM-assisted coaching interviews with the user to clarify priorities, define next actions, and propose tasks linked to Year Commitments and operational workload.

Boundaries:
- Business Coach talks to the user directly.
- Business Coach produces proposals only (no direct writes).
- Executive Assistant is the single writer and source of truth (only it writes SQLite).

Integration (minimal, no protocol yet):
- Coach → EA: proposals to create tasks, adjust priorities/estimates, suggest NEXT→NOW moves, and weekly focus candidates.
- Application of changes: user-confirmed (manual) for MVP.

## 15) Agent: Chief Architect (project-level)
We will create a dedicated project agent that acts as the “Chief Architect” and handles architecture decisions, migrations, integration strategy (MCP/CalDAV/IMAP), and security posture.

Best-practice guardrails:
- Use project instructions via AGENTS.md / equivalent to define scope, autonomy, and rules. (AGENTS.md concept)   [oai_citation:1‡reymer.ai](https://reymer.ai/knowledge/coding-agents-guide)
- Use “skills” (reusable instruction blocks) for recurring work: migrations, testing, connectors, threat-modeling.  [oai_citation:2‡reymer.ai](https://reymer.ai/knowledge/coding-agents-guide)
- Secrets never in repo; use environment variables / local-only .env excluded by .gitignore.  [oai_citation:3‡reymer.ai](https://reymer.ai/knowledge/coding-agents-guide)
- Work in small, verifiable increments: run tests + migrations; commit atomic changes; keep a clean git history.
- Always produce: decision record (ADR update), acceptance checks, and rollback notes for architectural changes.