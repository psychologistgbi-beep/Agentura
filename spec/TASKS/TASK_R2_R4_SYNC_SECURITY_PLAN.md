# TASK R2–R4: Sync Implementation & Security Plan

**Author:** Chief Architect
**Date:** 2026-02-15
**ADR reference:** `spec/ARCH_DECISIONS.md` ADR-10 (lines 200–243), ADR-07 (lines 130–155)
**AGENTS.md authority:** Section 2 — Integration design: Chief Architect proposes & approves (line 70)

---

## Overview

This document covers the implementation plan for three sequential releases that build on top of the R1 schema (TASK_R1_ADR10_SCHEMA_IMPLEMENTATION.md):

| Release | Scope | Depends on |
|---|---|---|
| **R2** | Calendar incremental sync (Yandex CalDAV) | R1 (schema) |
| **R3** | Mail headers ingest + task-email links (Yandex IMAP) | R1 (schema) |
| **R4** | Redaction/logging guardrails + security hardening | R1 (schema); validates R2+R3 |

**R2 and R3 are independent of each other** — they can be developed in parallel or in any order.
**R4 depends on R1** for schema but should be reviewed against R2/R3 code before merge.

---

## R2: Calendar Incremental Sync

### Goal

Implement `execas calendar sync` that fetches events from Yandex Calendar via CalDAV and upserts them into `busy_blocks` using the provenance columns from R1.

### Sync algorithm

```
1. Read cursor from sync_state WHERE source='yandex_caldav' AND scope=<calendar_slug>
2. If cursor is NULL → full sync (PROPFIND all events in date range)
   If cursor is ctag/sync-token → incremental (REPORT changes since cursor)
3. For each remote event:
   a. Compute external_id = UID (or UID + ";" + RECURRENCE-ID for recurring)
   b. Lookup local row by (calendar_id, source='yandex_caldav', external_id)
   c. If not found → INSERT with source='yandex_caldav'
   d. If found AND external_etag == remote ETag → SKIP (no change)
   e. If found AND external_etag != remote ETag → UPDATE fields + external_modified_at
4. For local rows with source='yandex_caldav' not seen in remote → SET is_deleted=1
5. Write new cursor to sync_state
6. Steps 3–5 execute in ONE transaction (idempotency invariant from R1)
```

### Watermark/cursor strategy

| Cursor kind | When used | Value stored |
|---|---|---|
| `ctag` | Server supports collection ctag (most CalDAV) | Opaque string from `getctag` |
| `sync_token` | Server supports WebDAV sync-collection (RFC 6578) | `sync-token` URI |

Detection order: try `sync-collection` REPORT first (more efficient). If 403/501 → fall back to ctag comparison + full PROPFIND.

### Dedup rules

- **Primary dedup key:** `(calendar_id, source, external_id)` — enforced by partial unique index (R1).
- **ETag guard:** Skip update when `external_etag` matches. Prevents unnecessary writes on no-change sync.
- **Soft delete:** Events removed from remote set `is_deleted=1`, never physically deleted. This preserves merge-on-read behavior (ADR-03) and allows recovery.

### Files to touch

| File | Change |
|---|---|
| `src/executive_cli/connectors/caldav.py` | New: `CalDavConnector` implementing `CalendarConnector` protocol (ADR-07) |
| `src/executive_cli/sync_service.py` | New: orchestration — cursor read, connector call, upsert, cursor write |
| `src/executive_cli/cli.py` | Add `calendar sync` command (stub → real) |
| `src/executive_cli/busy_service.py` | Add `is_deleted=0` pre-filter in `merge_busy_blocks()` or its call site in `cli.py` (`busy_list` command, ~line 180) |
| `tests/test_calendar_sync.py` | New: mock connector, upsert dedup, soft delete, cursor advance |

### Acceptance criteria

- [ ] `execas calendar sync` fetches events and upserts into `busy_blocks`
- [ ] Duplicate UIDs do not create duplicate rows (IntegrityError or upsert skip)
- [ ] ETag-unchanged events are not updated
- [ ] Events removed from remote are soft-deleted (`is_deleted=1`)
- [ ] Cursor is advanced only on successful commit
- [ ] `busy list` excludes `is_deleted=1` rows
- [ ] Manual busy blocks (`source='manual'`) are completely unaffected
- [ ] Graceful error when CalDAV unreachable (print error + suggest `busy add` fallback)

---

## R3: Mail Headers Ingest + Task-Email Links

### Goal

Implement `execas mail sync` that fetches email headers from Yandex Mail via IMAP and stores metadata in `emails`. Provide `execas task link-email` to create task-email associations.

### Sync algorithm

```
1. Read cursor from sync_state WHERE source='yandex_imap' AND scope=<mailbox>
2. Parse cursor as UIDVALIDITY:UIDNEXT
3. If UIDVALIDITY changed → full resync of mailbox (UIDs invalidated)
   If same → FETCH UIDs >= stored UIDNEXT
4. For each message:
   a. external_id = Message-ID header (canonical dedup key)
   b. Lookup by (source='yandex_imap', external_id)
   c. If not found → INSERT with first_seen_at = last_seen_at = now
   d. If found → UPDATE last_seen_at, flags_json
5. Write new cursor (UIDVALIDITY:UIDNEXT) to sync_state
6. Steps 4–5 in ONE transaction
```

### Privacy constraints (ADR-10, line 236)

- **NO email body stored.** Only: subject, sender, received_at, flags.
- `flags_json` stores IMAP flags as JSON array (e.g. `["\\Seen","\\Flagged"]`).
- No attachments, no recipients list, no CC/BCC.

### Task-email operations

Two CLI commands cover different workflows:

#### 1. Create task from email (one-step)
```
execas task capture --from-email <email_id> [--estimate N] [--priority P1|P2|P3] [--project X]
```

- Reads email metadata from `emails` table.
- Creates task with: title from subject (fallback: "Email follow-up"), status=NEXT, priority=P2 (default), estimate=30 (default).
- Auto-creates `task_email_links` row with `link_type='origin'`.
- User can override estimate, priority, project via flags.

#### 2. Link existing task to email (post-hoc)
```
execas task link-email <task_id> <email_id> [--type origin|reference|follow_up]
```

- Creates row in `task_email_links`.
- `link_type` defaults to `reference`.
- Unique constraint `(task_id, email_id)` prevents duplicate links.

#### Display
- `execas task show <id>` displays linked emails (subject + sender + received_at).

### Files to touch

| File | Change |
|---|---|
| `src/executive_cli/connectors/imap.py` | New: `ImapConnector` implementing `MailConnector` protocol (ADR-07) |
| `src/executive_cli/sync_service.py` | Add mail sync orchestration (reuse cursor pattern from R2) |
| `src/executive_cli/cli.py` | Add `mail sync` command + `task capture --from-email` flag + `task link-email` command |
| `tests/test_mail_sync.py` | New: mock IMAP, dedup, UIDVALIDITY reset, flag update |
| `tests/test_task_email_link.py` | New: link creation, duplicate rejection, task show with emails |

### Acceptance criteria

- [ ] `execas mail sync` fetches headers and upserts into `emails`
- [ ] Duplicate Message-IDs do not create duplicate rows
- [ ] UIDVALIDITY change triggers full resync
- [ ] `last_seen_at` and `flags_json` updated on re-sync
- [ ] No email body stored anywhere (verify with `PRAGMA table_info`)
- [ ] `task capture --from-email` creates task with defaults from email + origin link
- [ ] `task link-email` creates link; duplicate raises friendly error
- [ ] `task show` displays linked emails
- [ ] Graceful error when IMAP unreachable

---

## R4: Redaction / Logging Guardrails + Security Hardening

### Goal

Ensure that sync operations (R2, R3) do not leak credentials, PII, or sensitive metadata into logs, error messages, or debug output. Add automated tests that enforce these guarantees.

### Guardrail categories

#### G1: Credential redaction

- **Rule:** Credentials (passwords, tokens, app passwords) must NEVER appear in:
  - Log output (stdout, stderr, file logs)
  - Error messages / tracebacks
  - SQLite database
  - Git-tracked files
- **Enforcement:**
  - Connector classes accept credentials as constructor args, never log them.
  - Error messages use generic text: "Authentication failed" not "Password 'xyz123' rejected".
  - Test: capture stderr during auth failure, assert no credential substring present.

#### G2: PII minimization

- **Rule:** Only specified metadata fields are stored (ADR-10 line 236). No email body, no full recipient lists, no attachment content.
- **Enforcement:**
  - `ImapConnector.fetch_inbox()` returns only: `external_id`, `subject`, `sender`, `received_at`, `flags`.
  - `Email` model has no `body` column.
  - Test: mock IMAP response with body, verify body is not stored.

#### G3: Log-level discipline

- **Rule:** Sync operations use structured logging with appropriate levels:
  - `INFO`: sync started, sync completed, N events/emails processed
  - `WARNING`: partial data, rate limit, UIDVALIDITY change
  - `ERROR`: auth failure, connection timeout
  - `DEBUG`: individual event/email processing (never in production default)
- **Enforcement:**
  - No `print()` in connector or sync code — use `logging.getLogger(__name__)`.
  - Test: verify log levels for key scenarios.

#### G4: Connection security

- **Rule:** All external connections use TLS. No plaintext CalDAV/IMAP.
- **Enforcement:**
  - CalDAV connector enforces `https://` URLs. Reject `http://`.
  - IMAP connector uses `IMAP4_SSL` (port 993). No `STARTTLS` fallback.
  - Test: verify connection method assertions.

### Files to touch

| File | Change |
|---|---|
| `src/executive_cli/connectors/caldav.py` | Add credential redaction, TLS enforcement |
| `src/executive_cli/connectors/imap.py` | Add credential redaction, SSL enforcement, PII filter |
| `src/executive_cli/sync_service.py` | Add structured logging, no credential leaks |
| `tests/test_security_guardrails.py` | New: credential redaction, PII minimization, TLS enforcement tests |

### Test matrix

| Test | What it verifies | Category |
|---|---|---|
| `test_caldav_auth_error_no_credential_leak` | CalDAV auth failure stderr has no password | G1 |
| `test_imap_auth_error_no_credential_leak` | IMAP auth failure stderr has no password | G1 |
| `test_email_body_not_stored` | IMAP fetch with body → body absent from DB | G2 |
| `test_email_recipients_not_stored` | IMAP fetch with To/CC → not in DB | G2 |
| `test_caldav_rejects_http` | `http://` URL raises ValueError | G4 |
| `test_imap_uses_ssl` | Connector uses `IMAP4_SSL`, not `IMAP4` | G4 |
| `test_sync_log_levels` | INFO for start/end, ERROR for failures, no DEBUG by default | G3 |

### Acceptance criteria

- [ ] All G1–G4 tests pass
- [ ] `grep -r` for known test credential strings in DB file returns nothing
- [ ] Error messages for auth failures are generic
- [ ] No `print()` calls in connector/sync code
- [ ] CalDAV connector rejects non-HTTPS URLs
- [ ] IMAP connector uses SSL exclusively

---

## Dependencies & Sequencing

```
R1 (schema) ──┬──> R2 (calendar sync)
              ├──> R3 (mail sync)
              └──> R4 (security guardrails)

R2 ──> R4 reviews R2 code
R3 ──> R4 reviews R3 code
```

- **R1 must be complete** before R2, R3, or R4 can start.
- **R2 and R3 are independent** — develop in either order or in parallel.
- **R4 should be developed alongside R2/R3** but its test suite should do a final pass against R2+R3 code before merge.

## Readiness Criteria (per release)

### R2 ready when:
- [ ] R1 migration applied and verified
- [ ] CalDAV test account available (or mock sufficient for unit tests)
- [ ] `CalendarConnector` protocol defined (ADR-07 line 144)
- [ ] `busy_service.py` is_deleted filter planned

### R3 ready when:
- [ ] R1 migration applied and verified
- [ ] IMAP test account available (or mock sufficient for unit tests)
- [ ] `MailConnector` protocol defined (ADR-07 line 148)
- [ ] `task show` display format for linked emails agreed

### R4 ready when:
- [ ] R1 migration applied
- [ ] R2 and/or R3 connector code exists (even draft) for security review
- [ ] Threat model reviewed (`spec/templates/THREAT_MODEL_TEMPLATE.md` applied)

---

## Rollback

Each release can be rolled back independently:
- **R2 rollback:** Remove `calendar sync` command, revert `busy_service.py` filter. Synced busy blocks remain in DB with `source='yandex_caldav'` but are harmless (still shown by `busy list` unless is_deleted filter was added).
- **R3 rollback:** Remove `mail sync` and `task link-email` commands. Email rows remain in DB, task_email_links remain. No impact on core task workflow.
- **R4 rollback:** Revert security tests. No functional impact (guardrails are defensive).
- **Full rollback to pre-R1:** Run `alembic downgrade -1` per R1 rollback strategy. All sync data lost; manual workflow unaffected.
