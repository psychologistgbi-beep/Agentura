# Integration Plan: Yandex Mail via IMAP/Exchange

**Status:** Draft

**Date:** 2026-02-14

**Related ADR:** ADR-10

---

## 1. Overview

- **Service:** Yandex Mail (IMAP endpoint; Exchange adapter optional)
- **Protocol:** IMAP4rev1 (headers-first)
- **Direction:** Read-only ingest (external -> local)
- **Trigger:** Manual or scheduled `execas mail sync` (hourly optional)

Goal: ingest minimal email metadata safely, allow controlled creation of `NEXT` tasks from messages, and preserve traceable links task <-> email.

## 2. Data flow

```
[Yandex Mail] --(IMAP FETCH headers)--> [Mail Connector] --(EA mapper)--> [SQLite]
                                                     \--> [task creation action]
```

### Inbound

- Fetch only selected headers and metadata:
  - `Message-ID`, `Subject`, `From`, `Date`, `References`, `In-Reply-To`, `UID`, `INTERNALDATE`, flags
- Optional snippet/body fetch is disabled by default.
- Persist to `emails` table (ADR-10) with `source = yandex_imap`.

### Outbound

- No outbound write to mailbox.
- Task creation is local only (`tasks` insert with `status = NEXT`).

## 3. Task creation policy (allowed flow)

`execas task capture --from-email <email_id>` is allowed and deterministic:

- default status: `NEXT`
- title source: normalized subject (fallback: `Email follow-up`)
- priority default: `P2` (user can override)
- estimate default: `30` min (user can override)
- create linkage row in `task_email_links` (ADR-10)

Rules:

- One email can link to many tasks.
- A task can link to many emails (thread/attachments follow-up).
- Link creation is idempotent on `(task_id, email_id)`.

## 4. Privacy and data minimization

- Persist by default:
  - sender address (or hashed sender by policy),
  - subject,
  - timestamps,
  - mailbox ids (`UID`, `Message-ID`),
  - lightweight flags.
- Do not persist full body, attachments, auth tokens, or access credentials.
- Optional snippet storage must be opt-in and length-capped.

## 5. Dedup/idempotency

Canonical identity:

- `source = yandex_imap`
- `external_id = Message-ID` (fallback to mailbox UID when missing)

Upsert rule:

- same `(source, external_id)` => update mutable metadata only
- keep `first_seen_at` immutable, refresh `last_seen_at` each sync

## 6. Failure modes

| Failure | Detection | Impact | Mitigation |
|---|---|---|---|
| Invalid credentials | auth failure | no sync | fail fast, redact details, prompt reconfigure |
| IMAP timeout | network timeout | stale inbox view | bounded retries, keep previous state |
| Duplicate fetch window | repeated UIDs | duplicate risk | upsert by canonical key |
| Malformed header | parser error | partial import | skip bad message, record structured warning |

## 7. Security constraints

- Read-only mailbox permission.
- No send/delete/move operations.
- Secrets managed outside repo/database.
- Logging policy forbids raw auth strings and message body dumps.
