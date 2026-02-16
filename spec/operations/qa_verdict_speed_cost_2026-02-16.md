# QA Verdict: SPEED-COST-01

**Role:** QA/SET  
**Date:** 2026-02-16

## Scope under test

- Parallel hourly sync orchestration and CLI output stability.
- CalDAV sync-window runtime controls.
- Sync-service query shaping changes for calendar/mail upsert path.

## Verification evidence

Executed commands:

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run pytest -q tests/test_sync_hourly.py tests/test_caldav_connector.py tests/test_calendar_sync.py tests/test_mail_sync.py
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

Observed results:
- Targeted suite: `43 passed`.
- Full suite: `102 passed`.
- Coverage gate: `88.36%` (threshold `>=80%`).
- Migration integrity: pass on fresh DB initialization.

## Quality verdict

- Functional regression status: **PASS**
- Security/regression risk status: **PASS with low residual risk**

## Residual risks

1. Real-world endpoint behavior under sustained parallel runs may vary by provider throttling policy.
2. Operator misconfiguration of sync-window env vars can reduce event visibility range.

## Recommendations

1. Keep scheduler default in parallel mode for speed; switch to `--sequential` on provider throttling incidents.
2. Add runtime alert thresholds on `elapsed_sec` drift in operations runbook.
