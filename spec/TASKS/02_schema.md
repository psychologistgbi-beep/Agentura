# TASK 02 — SQLite schema + migrations scaffolding

## Goal
Introduce SQLite data layer foundations for MVP:
- DB file creation path strategy (documented)
- Alembic migrations set up
- Initial schema for:
  - settings (key/value)
  - calendars (primary calendar)
  - busy_blocks
  - areas, projects
  - commitments
  - tasks (GTD fields, incl WAITING requirements)
- Ensure `execas init` creates DB and applies migrations (idempotent)

## In scope
- Add SQLModel/SQLAlchemy + Alembic.
- Implement DB initialization and migrations.
- Seed:
  - settings: timezone=Europe/Moscow and planning defaults per TECH_SPEC
  - calendars: one primary calendar
- `execas init`:
  - creates DB if missing
  - applies migrations
  - safe to run twice (no duplicate primary calendar; no crash)

## Out of scope
- FTS5 (People/Decisions) — TASK 09.
- Planning algorithm — TASK 07.
- MCP integrations — TASK 11.
- people, decisions, emails tables — later tasks.

## Files to touch (expected)
- apps/executive-cli/pyproject.toml (deps)
- apps/executive-cli/alembic.ini
- apps/executive-cli/alembic/ (env.py, versions/)
- apps/executive-cli/src/executive_cli/db.py (engine/session/init helpers)
- apps/executive-cli/src/executive_cli/models.py (SQLModel models)
- apps/executive-cli/src/executive_cli/cli.py (init command calls DB init)
- apps/executive-cli/README.md (document DB location/env var)

## Required schema (minimum)
- settings(key TEXT PK, value TEXT)
- calendars(id PK, slug UNIQUE, name, timezone)
- busy_blocks(id PK, calendar_id FK, start_dt, end_dt, title nullable)
- areas(id PK, name UNIQUE)
- projects(id PK, name UNIQUE, area_id FK nullable)
- commitments(id TEXT PK, title, metric/definition_of_done, due_date, difficulty, notes)
- tasks:
  - id PK
  - title
  - status enum: NOW/NEXT/WAITING/SOMEDAY/DONE/CANCELED
  - project_id FK, area_id FK, commitment_id FK nullable
  - priority P1/P2/P3
  - estimate_min INT (required)
  - due_date DATE nullable
  - next_action TEXT nullable
  - waiting_on TEXT nullable but REQUIRED when status=WAITING
  - ping_at DATETIME nullable but REQUIRED when status=WAITING
  - created_at, updated_at

## Steps (commands)
1) Add deps:
   - `uv add sqlmodel sqlalchemy alembic`
2) Initialize alembic:
   - `alembic init alembic` (inside apps/executive-cli)
3) Create models and initial migration:
   - generate revision with autogenerate (or manual).
4) Implement DB path configuration:
   - default under repo/app (documented) OR use env var `EXECAS_DB_PATH`.
5) Update `execas init` to:
   - create/apply migrations
   - seed settings + primary calendar

## Acceptance checks
- Fresh start:
  - remove DB file
  - `uv run execas init` creates DB and applies migrations
- Idempotency:
  - run `uv run execas init` again; success, no duplicates
- Manual verification:
  - sqlite tables exist (via `sqlite3 <db> ".tables"` or equivalent)
  - settings include timezone and planning constraints per TECH_SPEC

## Rollback
- Revert commit. DB file is local artifact; it may be deleted and recreated.
