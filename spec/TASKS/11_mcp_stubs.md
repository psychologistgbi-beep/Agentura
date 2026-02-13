# TASK 11 — MCP sync stubs (calendar + email)

## Goal
Add `execas calendar sync` and `execas mail sync` command stubs with graceful fallback.

## Depends on
- TASK 03 (busy blocks table)
- TASK 02 (emails table migration)

## In scope
- Alembic migration for emails table: emails(id, message_id, subject, sender, received_at, snippet, raw_ref).
- `execas calendar sync`:
  - Check for MCP CalDAV connector config (env var or config key).
  - If absent: print actionable error + fallback instructions (use `execas busy add`).
  - If present: placeholder for future CalDAV integration (print "sync not yet implemented").
- `execas mail sync`:
  - Same pattern with MCP IMAP.
  - If absent: error + fallback (manual task capture).
- `execas mail list` — list synced email headers (empty until real sync).
- Define connector Protocol interfaces (ADR-07) in code for future implementation.

## Out of scope
- Actual CalDAV/IMAP implementation.
- Email-to-task linking UI (stretch).

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (calendar, mail groups)
- apps/executive-cli/src/executive_cli/connectors.py (Protocol definitions)
- apps/executive-cli/src/executive_cli/models.py (Email model)
- Alembic migration

## Acceptance checks (TEST_PLAN: T16, T17)
- `execas calendar sync` without MCP -> clear error, no corrupt data.
- `execas mail sync` without MCP -> clear error.
- `execas mail list` works (empty result OK).

## Rollback
- Revert commit.
