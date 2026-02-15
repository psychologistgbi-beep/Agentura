# TASK INT-YANDEX-01: Production Integration with Yandex Calendar and Mail

**Author:** Technical Lead  
**Date:** 2026-02-15  
**Scope type:** integration readiness and acceptance

## Goal

Enable production-ready read-only integration with user's Yandex Calendar (CalDAV) and Yandex Mail (IMAP INBOX), with validated operational flow and acceptance artifacts.

## Constraints (hard)

- Read-only only.
- Mailbox scope only `INBOX`.
- No credentials in repository or SQLite.
- All quality gates remain mandatory.

## In scope

- Acceptance criteria and environment checklist.
- EA credential-handling scenarios and secure setup flow.
- Architecture safety review for read-only + least privilege.
- Runtime verification and targeted fixes (if needed).
- QA verdict and residual-risk report.
- Operational runbook validation for hourly sync and metrics.

## Out of scope

- External write operations (calendar/mail).
- Additional mailbox scopes.
- Schema/time-model/ADR changes unless explicitly approved.

## Primary commands

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas calendar sync
uv run execas mail sync --mailbox INBOX
uv run execas sync hourly --retries 2 --backoff-sec 5
uv run execas review scrum-metrics --no-run-quality
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
```
Secure helper path (session-only credentials):
```bash
cd /Users/gaidabura/Agentura
scripts/ea-yandex-check --only-smoke
```

## Acceptance checks

- [ ] Calendar sync works with Yandex endpoint in read-only mode.
- [ ] Mail sync works for INBOX only.
- [ ] No secrets leak in output/logs/errors.
- [ ] EA scenario doc and helper script are used for live setup.
- [ ] Hourly sync behavior and fallback documented.
- [ ] Scrum metrics command is operational for calibration.
- [ ] TL acceptance ledger updated with verdicts.

## Rollback notes

- If live integration fails, keep manual fallback (`busy add`, task capture from email metadata workflow), preserve current stable sync code, and isolate fixes in separate commit(s).
