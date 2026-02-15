# Architecture Review: Yandex Read-Only Integration

**Owner:** Chief Architect  
**Date:** 2026-02-15  
**Task:** `INT-ARCH-01`

## Scope reviewed

- CalDAV connector path (`yandex_caldav`) for calendar import.
- IMAP connector path (`yandex_imap`) for mailbox header import.
- EA runtime scenario and helper flow for credential intake.
- New operational verification command: `execas calendar next-week`.

## Compliance verdict

- Read-only policy: **PASS**
- INBOX-only mail scope: **PASS**
- Secret-handling policy: **PASS** (with operational caveat below)

## Evidence highlights

- CalDAV connector uses `PROPFIND` only for collection/event reads; no write verbs are present in connector flow.
- IMAP connector uses `IMAP4_SSL` and `select(..., readonly=True)` and reads headers via `uid SEARCH/FETCH`.
- Mail sync CLI and runbooks keep mailbox scope fixed to `INBOX` in standard flow.
- EA helper flow uses process-level environment variables only and does not persist credentials in repository files.
- `calendar next-week` reads already-synced data from SQLite; it does not call external write operations.

## Risks and mitigations

1. Risk: operator may accidentally run with wrong mailbox option outside helper flow.
Mitigation: retain `INBOX` in runbook defaults and acceptance checklist; reject non-approved scope during TL acceptance.

2. Risk: credentials copied into shell history by manual export.
Mitigation: use `scripts/ea-yandex-check` interactive prompts (no inline password in shell command).

3. Risk: degraded sync may leave partial visibility for planning.
Mitigation: keep fallback runbook (`busy add`, `task capture`) and degraded exit code handling (`2`) in operations.

## Decision

Architecture is approved for `INT-YANDEX-01` under existing read-only and least-privilege constraints.
No ADR update is required for this increment because data model and integration strategy remain unchanged.
