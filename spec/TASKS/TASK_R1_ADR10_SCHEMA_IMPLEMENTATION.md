# TASK R1: ADR-10 Schema / Migration Implementation

**Author:** Chief Architect
**Date:** 2026-02-15
**ADR reference:** `spec/ARCH_DECISIONS.md` ADR-10 (lines 200–243)
**AGENTS.md authority:** Section 2 — "Schema / migrations: Any agent can propose, Chief Architect must approve" (line 66)

---

## Goal

Implement the database schema changes specified in ADR-10 (External Sync Provenance) as a single Alembic migration. This task covers **only** models + migration — no CLI commands, no sync logic, no connector code.

---

## Exact Schema Specification

### 1. Extend `busy_blocks` (ALTER TABLE — add columns)

Current columns (`models.py:41–54`): `id`, `calendar_id`, `start_dt`, `end_dt`, `title`.

Add these nullable columns (all nullable because existing manual rows have no external metadata):

| Column | Type | Default | Purpose |
|---|---|---|---|
| `source` | TEXT NOT NULL | `'manual'` | Provenance: `manual` / `yandex_caldav` / etc. Server default so existing rows get value. |
| `external_id` | TEXT NULL | NULL | CalDAV UID or UID+RECURRENCE-ID |
| `external_etag` | TEXT NULL | NULL | CalDAV ETag for change detection |
| `external_modified_at` | TEXT NULL | NULL | ISO-8601 from external system (ADR-01 convention) |
| `is_deleted` | INTEGER NOT NULL | `0` | Soft tombstone (0=active, 1=deleted). INTEGER not BOOLEAN per SQLite convention. |

**New constraint:**
```sql
CREATE UNIQUE INDEX uq_busy_blocks_source_external_id
ON busy_blocks(calendar_id, source, external_id)
WHERE external_id IS NOT NULL;
```
Partial unique index: only enforced when `external_id` is non-null, so manual blocks (where `external_id` IS NULL) are unaffected. This is the dedup key for CalDAV sync.

**Design decision — why `source` is NOT NULL with default `'manual'`:**
- Every existing row in production DBs gets `source='manual'` via `server_default`.
- New CalDAV-synced rows get `source='yandex_caldav'`.
- Enables clean WHERE filtering: `WHERE source = 'manual'` for user-created, `WHERE source != 'manual'` for synced.
- Alternative rejected: nullable `source` — ambiguous semantics, harder to query, would require COALESCE everywhere.

### 2. New table: `sync_state`

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | INTEGER | PK | Auto-increment |
| `source` | TEXT NOT NULL | | e.g. `yandex_caldav`, `yandex_imap` |
| `scope` | TEXT NOT NULL | | e.g. `primary` (calendar slug) or `INBOX` (mailbox) |
| `cursor` | TEXT NULL | | Opaque watermark: CalDAV `ctag`/`syncToken`, IMAP `UIDVALIDITY:UIDNEXT` |
| `cursor_kind` | TEXT NULL | | Discriminator: `ctag` / `sync_token` / `imap_uid` |
| `updated_at` | TEXT NOT NULL | | ISO-8601 with offset (ADR-01) |

**Constraint:** `UNIQUE(source, scope)` — one cursor per source+scope pair.

**Idempotency invariant:** Sync reads cursor → fetches delta → writes new cursor + data in one transaction. If transaction fails, cursor is not advanced.

### 3. New table: `emails`

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | INTEGER | PK | Auto-increment |
| `source` | TEXT NOT NULL | | e.g. `yandex_imap` |
| `external_id` | TEXT NOT NULL | | Canonical Message-ID header |
| `mailbox_uid` | INTEGER NULL | | IMAP UID within mailbox |
| `subject` | TEXT NULL | | Subject line (metadata only — no body stored per ADR-10) |
| `sender` | TEXT NULL | | From header |
| `received_at` | TEXT NULL | | ISO-8601 with offset (ADR-01) |
| `first_seen_at` | TEXT NOT NULL | | When we first ingested this record |
| `last_seen_at` | TEXT NOT NULL | | Updated on re-sync |
| `flags_json` | TEXT NULL | | JSON array of IMAP flags, e.g. `["\\Seen","\\Flagged"]` |

**Constraint:** `UNIQUE(source, external_id)` — dedup key.

**Privacy note:** No email body is stored. Only metadata (subject, sender, received_at). This is a deliberate ADR-10 decision (line 236: "Rejected: unnecessary PII expansion and larger attack surface").

### 4. New table: `task_email_links`

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | INTEGER | PK | Auto-increment |
| `task_id` | INTEGER NOT NULL | FK → `tasks.id` | |
| `email_id` | INTEGER NOT NULL | FK → `emails.id` | |
| `link_type` | TEXT NOT NULL | | e.g. `origin`, `reference`, `follow_up` |
| `created_at` | TEXT NOT NULL | | ISO-8601 with offset (ADR-01) |

**Constraint:** `UNIQUE(task_id, email_id)` — one link per task-email pair.

---

## Migration Plan

### Single migration file

Revision chain: `d4a2b5c30f18` (current head: `add_weekly_reviews`) → new revision.

### `upgrade()`

Order matters for foreign keys:

1. **ALTER `busy_blocks`:** Add 5 columns with server defaults.
   - SQLite limitation: `ALTER TABLE ADD COLUMN` does not support adding constraints inline. Columns added one by one.
   - `source`: `server_default='manual'`, NOT NULL.
   - `external_id`: nullable.
   - `external_etag`: nullable.
   - `external_modified_at`: nullable.
   - `is_deleted`: `server_default='0'`, NOT NULL.
2. **CREATE INDEX** `uq_busy_blocks_source_external_id` (partial unique).
   - Must use `op.execute()` for partial index (`WHERE external_id IS NOT NULL`) since Alembic's `create_index` doesn't support `WHERE`.
3. **CREATE TABLE** `sync_state` with UNIQUE(source, scope).
4. **CREATE TABLE** `emails` with UNIQUE(source, external_id).
5. **CREATE TABLE** `task_email_links` with UNIQUE(task_id, email_id), FKs to tasks and emails.

### `downgrade()`

Reverse order:

1. DROP TABLE `task_email_links`.
2. DROP TABLE `emails`.
3. DROP TABLE `sync_state`.
4. DROP INDEX `uq_busy_blocks_source_external_id`.
5. SQLite limitation: `ALTER TABLE DROP COLUMN` requires SQLite 3.35.0+ (2021-03-12). Python 3.11 bundles SQLite 3.39+, so this is safe. Drop columns: `is_deleted`, `external_modified_at`, `external_etag`, `external_id`, `source`.

**Alternative rejected — recreate table for column removal:**
SQLite 3.35+ supports `DROP COLUMN` natively. Using `op.batch_alter_table()` for recreation is unnecessary and riskier (data copy). We explicitly require Python 3.11+ (`pyproject.toml:9`), which guarantees SQLite >= 3.39.

---

## Data Invariants

| Invariant | Enforcement | Test requirement |
|---|---|---|
| Manual busy blocks have `source='manual'`, `external_id=NULL` | Default values; application code | Test: create via `busy add`, verify `source='manual'` |
| External busy blocks have non-null `external_id` | Application code (sync layer) | Test: insert with external_id, verify dedup index |
| No two synced blocks share `(calendar_id, source, external_id)` | Partial unique index | Test: duplicate insert raises IntegrityError |
| `sync_state` has at most one row per `(source, scope)` | UNIQUE constraint | Test: upsert cursor, verify single row |
| `emails` has at most one row per `(source, external_id)` | UNIQUE constraint | Test: duplicate insert raises IntegrityError |
| `task_email_links` has at most one link per `(task_id, email_id)` | UNIQUE constraint | Test: duplicate insert raises IntegrityError |
| All ISO-8601 timestamps use `dt_to_db()` | Code convention (ADR-01) | Test: round-trip via `dt_to_db`/`db_to_dt` |
| `is_deleted` is 0 or 1 | Application convention (no CHECK — too fragile for flags) | Test: soft-delete sets to 1, query filters |

---

## Idempotency Rules for Future Sync

These are **not implemented in R1** but the schema must support them:

1. **Calendar sync:** Upsert by `(calendar_id, source, external_id)`. If exists and `external_etag` unchanged → skip. If changed → update fields + `external_modified_at`. If missing from remote → set `is_deleted=1`.
2. **Email sync:** Upsert by `(source, external_id)`. If exists → update `last_seen_at` and `flags_json`. If new → insert with `first_seen_at = last_seen_at = now`.
3. **Cursor advance:** Update `sync_state.cursor` only after successful data commit (same transaction).

---

## Rollback Strategy

1. Run `alembic downgrade -1` to reverse the migration.
2. This drops `task_email_links`, `emails`, `sync_state`, and removes added columns from `busy_blocks`.
3. Manual busy blocks are unaffected (they don't use the new columns).
4. Any synced data is lost on rollback — this is acceptable because manual fallback (`busy add`, `task capture`) remains functional per ADR-07 (line 140).

---

## Files to Touch

| File | Change |
|---|---|
| `apps/executive-cli/src/executive_cli/models.py` | Add/modify: `BusyBlock` (new fields), `SyncState`, `Email`, `TaskEmailLink` models |
| `apps/executive-cli/alembic/versions/<new>.py` | New migration: add columns + create 3 tables + partial index |
| `apps/executive-cli/tests/test_provenance_schema.py` | New: constraint tests (dedup, uniqueness, soft delete, defaults) |

**NOT touched:** `cli.py`, `planner.py`, `review.py`, `busy_service.py`, `config.py`, `db.py`, `timeutil.py`.

---

## Quality Gates (EA must pass all before merge)

Per `AGENTS.md` section 4 (lines 109–133):

```bash
# Migration integrity
cd apps/executive-cli
rm -f .data/execas.sqlite && uv run execas init

# Verify new tables exist
sqlite3 .data/execas.sqlite ".tables"
# Must include: sync_state, emails, task_email_links

# Verify busy_blocks has new columns
sqlite3 .data/execas.sqlite "PRAGMA table_info('busy_blocks');"
# Must include: source, external_id, external_etag, external_modified_at, is_deleted

# Verify partial unique index
sqlite3 .data/execas.sqlite "PRAGMA index_list('busy_blocks');"

# Verify existing manual busy block still works
uv run execas busy add --date 2026-02-20 --start 10:00 --end 11:00 --title "Test"
sqlite3 .data/execas.sqlite "SELECT source, external_id, is_deleted FROM busy_blocks WHERE id=1;"
# Expected: manual||0

# Tests
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80

# Downgrade test
cd apps/executive-cli
rm -f .data/execas.sqlite && uv run execas init
uv run python -c "
from alembic.config import Config; from alembic import command
cfg = Config('alembic.ini')
command.downgrade(cfg, '-1')
command.upgrade(cfg, 'head')
print('Downgrade+upgrade cycle OK')
"
```

---

## EA Handoff Contract

**What EA can do:**
- Implement models and migration exactly as specified above.
- Write tests for the invariants listed.
- Choose Alembic revision ID (any valid hex string).

**What EA must NOT do without Chief Architect approval:**
- Change column types, names, or nullability from this spec.
- Add CLI commands (that is R2/R3/R4).
- Modify existing `busy_service.py` merge logic (the `is_deleted` filter will be added in R2).
- Add `CHECK` constraints beyond what is specified.
- Change the partial index to a full unique index (would break manual blocks).
