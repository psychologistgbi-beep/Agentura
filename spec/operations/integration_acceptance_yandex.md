# Yandex Integration Acceptance Checklist

**Owner:** System Analyst + Product Owner + Executive Assistant  
**Date:** 2026-02-15  
**Batch:** `INT-YANDEX-01`

## Functional acceptance

- [ ] Yandex Calendar sync works via `execas calendar sync`.
- [ ] Yandex Mail sync works via `execas mail sync --mailbox INBOX`.
- [ ] Combined run works via `execas sync hourly --retries 2 --backoff-sec 5`.
- [ ] Next-week calendar import verification works via `execas calendar next-week --source yandex_caldav`.

## Policy acceptance

- [ ] Read-only policy preserved for both connectors.
- [ ] Mail scope limited to `INBOX`.
- [ ] No write/delete/move operations to external systems.

## Security acceptance

- [ ] Credentials used only through environment variables.
- [ ] No secret leakage in command output/logs.
- [ ] No secrets in repository files or SQLite.

## Operational acceptance

- [ ] Runbook references are complete:
  - `spec/operations/ea_yandex_integration_scenarios.md`
  - `spec/operations/hourly_sync.md`
- [ ] Metrics calibration command available:
  - `uv run execas review scrum-metrics --no-run-quality`

## Evidence table

| Check | Command | Result | Timestamp | Notes |
|---|---|---|---|---|
| Calendar sync | `uv run execas calendar sync` | `<pass/fail>` | `<ts>` | `<note>` |
| Mail sync | `uv run execas mail sync --mailbox INBOX` | `<pass/fail>` | `<ts>` | `<note>` |
| Hourly sync | `uv run execas sync hourly --retries 2 --backoff-sec 5` | `<0/2/1>` | `<ts>` | `<note>` |
| Next-week import verification | `uv run execas calendar next-week --source yandex_caldav` | `<pass/fail>` | `<ts>` | `<count/notes>` |
| Metrics snapshot | `uv run execas review scrum-metrics --no-run-quality` | `<pass/fail>` | `<ts>` | `<note>` |
