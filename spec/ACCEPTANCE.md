# Acceptance Criteria — Executive Assistant MVP (v0.1)

This document defines “done” for the MVP. All criteria must be objectively verifiable.

## A. Repository & Project Structure
A1. Repo contains:
- spec/TECH_SPEC.md
- spec/ACCEPTANCE.md
- spec/TEST_PLAN.md
- spec/TASKS/ (task breakdown files)
- agents/developer_helper/ (skill package skeleton)

A2. Implementation lives under:
- apps/executive-cli/ (Python project)

A3. Git hygiene:
- Each MVP milestone is delivered as small commits (one task = one commit).
- Repo can be cloned and set up on a clean machine following documented steps.

## B. CLI Bootstrapping
B1. CLI executable is available as `execas` (or documented alternative) and responds to:
- `execas --help`
- `execas init --help`
- `execas config --help`
- `execas task --help`
- `execas busy --help`
- `execas plan --help`
- `execas people --help`
- `execas decision --help`

B2. `execas init`:
- Creates SQLite DB (path documented; default location documented).
- Applies migrations from empty state reproducibly.
- Seeds: primary calendar record and required settings entries including timezone.
- Is idempotent (second run does not corrupt state and exits cleanly).

## C. Timezone & Datetime Correctness
C1. System timezone is Europe/Moscow.
- All CLI inputs without explicit timezone are interpreted as Europe/Moscow.
- All CLI outputs are displayed in Europe/Moscow.

C2. Persisted datetimes are stored as ISO-8601 TEXT with explicit offset (ADR-01). Round-trip test: MSK input -> DB -> MSK output preserves value.

C3. Busy block overlap handling (ADR-03):
- Merge is performed on read (not on insert); raw blocks preserved.
- Overlapping or adjacent busy blocks are merged deterministically.
- No negative-duration blocks can exist.

## D. Settings (No “Hidden Defaults” Beyond Spec)
D1. All planning parameters are stored in DB settings and can be shown/changed via CLI.
Minimum required keys and defaults:
- timezone = Europe/Moscow
- planning_start = 07:00
- planning_end = 19:00
- lunch_start = 12:00
- lunch_duration_min = 60
- min_focus_block_min = 30 (includes switching overhead)
- buffer_min = 5

D2. `execas config show` prints all current settings.
D3. `execas config set` updates a setting and the change is persisted.

## E. GTD Task System
E1. Task statuses supported exactly:
NOW, NEXT, WAITING, SOMEDAY, DONE, CANCELED

E2. Task creation requires:
- title
- estimate_min (int)
- priority (P1/P2/P3)

E3. WAITING tasks must include:
- waiting_on
- ping_at (datetime, Europe/Moscow)

E4. Areas and Projects exist as reference data (not free-text):
- `execas area add/list` and `execas project add/list` work.
- Projects optionally link to an area.
- Tasks can link to project/area.

E5. Task listing supports filters at least by:
- status
- due date (optional)
- project/area (optional)
- commitment_id (optional)

## F. Commitments
F1. Commitments can be created/stored and linked to tasks.
F2. Commitments include: id (YC-*), title, definition_of_done/metric, due_date, difficulty, notes/evidence.
F3. `execas commitment add/list/import` commands exist. `execas commitment import` seeds YC-1..YC-3 idempotently.

## G. Primary Calendar & Busy Blocks
G1. There is exactly one primary calendar in MVP.
G2. Busy blocks can be created manually via CLI and listed per day.

### G3 — MVP (stub)
G3-mvp. Calendar sync exists as a command stub with:
- Clear error if MCP/credentials not configured.
- Fallback workflow documented (manual `busy add`/`busy list`).

### G3 — Post-MVP (R2: real sync)
G3-post. `execas calendar sync` performs incremental CalDAV sync:
- Upserts external events into `busy_blocks` with `source='yandex_caldav'`.
- Dedup by `(calendar_id, source, external_id)` partial unique index.
- ETag-unchanged events are skipped.
- Removed events are soft-deleted (`is_deleted=1`), not physically deleted.
- `busy list` excludes `is_deleted=1` rows.
- Manual busy blocks (`source='manual'`) are never affected by sync.
- Cursor advanced only on successful commit (idempotency).
- Graceful error when CalDAV unreachable (fallback to `busy add`).

## H. Planning: `plan day` with 3 variants and time-block output
H1. `execas plan day --date YYYY-MM-DD --variant minimal|realistic|aggressive`:
- Produces a schedule of time blocks with explicit start/end timestamps.
- Stores the result in DB: day_plans + time_blocks.

H2. Time block types include at least:
busy, focus, admin, lunch, buffer

H3. Planning respects constraints:
- Planning window 07:00–19:00 only.
- Busy blocks are never overwritten.
- Lunch is reserved at/around 12:00; if conflict, moved to nearest feasible slot around mid-day.
- Blocks shorter than min_focus_block_min are not used for focus; they become buffer/admin.
- Buffer is inserted according to buffer_min policy (MVP: single global buffer).

H4. Determinism (ADR-06):
Given the same inputs (tasks, busy blocks, settings), the produced plan is identical. No LLM is used in `plan day`.

H4a. Day plan upsert (ADR-05):
Re-running `plan day` for the same (date, variant) replaces the previous plan.

H5. Output includes a short rationale:
- Which tasks were chosen and why (priority, due, commitment).
- What didn’t fit and suggested actions (reschedule, split—not implemented by default).

## I. Weekly Review (Sunday)
I1. `execas review week --week YYYY-Www` produces:
- A prioritized list of weekly focus items (5–10) derived from commitments + deadlines + WAITING pings + NEXT pool.
- Markdown output saved (location documented) and summary stored in DB.

## J. Knowledge: People & Decisions + Full-Text Search
J1. People:
- Add and search people via CLI.
- Search uses FTS (substring/term search works).

J2. Decisions:
- Add decisions via CLI (title, context, choice; consequences optional).
- Search uses FTS.

J3. FTS index updates when new people/decisions are added.

## K. Email Integration (Yandex)

### K1 — MVP (stub)
K1-mvp. Mail sync exists as a command stub with:
- Clear error if MCP/credentials not configured.
- Fallback workflow documented (manual `task capture` from email).

### K1 — Post-MVP (R3: real sync)
K1-post. `execas mail sync` performs incremental IMAP header ingest:
- Upserts email metadata into `emails` table with `source='yandex_imap'`.
- Dedup by `(source, external_id)` where `external_id` = Message-ID header.
- UIDVALIDITY change triggers full resync.
- `last_seen_at` and `flags_json` updated on re-sync.
- No email body stored (metadata only: subject, sender, received_at, flags).
- Cursor advanced only on successful commit.
- Graceful error when IMAP unreachable.

### K2 — MVP (stub)
K2-mvp. Ability to create a task from an email is documented as future workflow.

### K2 — Post-MVP (R3: task-email linking)
K2-post. Two commands for task-email association:
- `execas task capture --from-email <email_id>`: creates a new task with defaults derived from email metadata (title from subject, status=NEXT, priority=P2, estimate=30) and auto-creates a `task_email_links` row with `link_type='origin'`.
- `execas task link-email <task_id> <email_id> [--type origin|reference|follow_up]`: links an existing task to an email. Duplicate `(task_id, email_id)` raises friendly error.
- `execas task show <id>` displays linked emails (subject + sender + received_at).

## L. Testability & Documentation
L1. `spec/TEST_PLAN.md` is implementable; at least core tests can be executed locally.
L2. Setup instructions exist (in README or apps/executive-cli/README).
L3. All “TBD” items are explicitly listed in TECH_SPEC and/or a separate TBD section.