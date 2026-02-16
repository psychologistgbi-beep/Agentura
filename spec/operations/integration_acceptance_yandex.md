# Yandex Integration Acceptance Checklist

**Owner:** System Analyst + Product Owner + Executive Assistant  
**Date:** 2026-02-15  
**Batch:** `INT-YANDEX-01`

## Functional acceptance

- [x] Yandex Calendar sync works via `execas calendar sync`.
- [x] Yandex Mail sync works via `execas mail sync --mailbox INBOX`.
- [x] Combined run works via `execas sync hourly --retries 2 --backoff-sec 5`.
- [x] Next-week calendar import verification works via `execas calendar next-week --source yandex_caldav`.
- [x] `calendar next-week` timezone in output matches assistant timezone setting.

## Policy acceptance

- [x] Read-only policy preserved for both connectors.
- [x] Mail scope limited to `INBOX`.
- [x] No write/delete/move operations to external systems.

## Security acceptance

- [x] Credentials used only through environment variables and/or approved OS Keychain storage.
- [x] No secret leakage in command output/logs.
- [x] No secrets in repository files or SQLite.
- [ ] Error/degraded logs are redacted (no credentials/tokens/password fragments).

## Operational acceptance

- [x] Runbook references are complete:
  - `spec/operations/ea_yandex_integration_scenarios.md`
  - `spec/operations/hourly_sync.md`
- [ ] Metrics calibration command available:
  - `uv run execas review scrum-metrics --no-run-quality`

## Evidence table

| Check | Command | Result | Timestamp | Notes |
|---|---|---|---|---|
| Calendar sync | `uv run execas calendar sync --force-full` | `pass` | `2026-02-16` | `inserted=0 updated=0 skipped=3307 soft_deleted=0 cursor_kind=multi_ctag` |
| Mail sync | `uv run execas mail sync --mailbox INBOX --this-year` | `pass` | `2026-02-16` | `inserted=2 updated=0 cursor_kind=uidvalidity_uidnext` |
| Hourly sync | `uv run execas sync hourly --retries 2 --backoff-sec 5` | `0` | `2026-02-16` | `calendar sync ok, mail sync ok, status=ok` |
| Next-week import verification | `uv run execas calendar next-week --source yandex_caldav --anchor-date 2026-02-15` | `pass` | `2026-02-16` | `week=2026-02-16..2026-02-22 count=65` |
| Timezone check | `uv run execas config show` + `uv run execas calendar next-week --source yandex_caldav --anchor-date 2026-02-15` | `pass` | `2026-02-16` | `timezone=Europe/Moscow matches output label` |
| Redaction check | `uv run execas sync hourly --retries 0 --backoff-sec 1` (failure path) | `<pass/fail>` | `<ts>` | `<no secret strings>` |
| Metrics snapshot | `uv run execas review scrum-metrics --no-run-quality` | `<pass/fail>` | `<ts>` | `<note>` |
