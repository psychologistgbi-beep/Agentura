# TL Dispatch: INT-YANDEX-01

**Owner:** Technical Lead  
**Date:** 2026-02-15  
**Baseline source:** `spec/operations/tl_plan_yandex_integration_2026-02-15.md`

## Scope lock

- Providers: `yandex_caldav`, `yandex_imap`
- Policy: read-only only
- Mailbox scope: INBOX only

## Dispatch briefs

### INT-DISC-01 (System Analyst + Product Owner)

Goal:
- Produce explicit acceptance checklist for real-account integration.
- Produce env checklist (variable names, validation constraints, no-secret logging rule).

Artifacts:
- `spec/operations/integration_acceptance_yandex.md`

Acceptance:
- Checklist is testable and maps to commands.
- No policy conflicts with `AGENTS.md` security section.

### INT-ARCH-01 (Chief Architect)

Goal:
- Validate integration path against read-only policy and least privilege.
- Confirm fallback and failure behavior is safe.

Artifacts:
- `spec/operations/architecture_review_yandex_readonly.md`

Acceptance:
- Explicit verdict on read-only compliance.
- Explicit verdict on INBOX-only scope.
- Risks and mitigations documented.

### INT-EXEC-01 (Executive Assistant)

Goal:
- Execute real-path integration checks and implement minimal fixes if needed.

In-scope files (if fixes required):
- `apps/executive-cli/src/executive_cli/cli.py`
- `apps/executive-cli/src/executive_cli/sync_service.py`
- `apps/executive-cli/src/executive_cli/connectors/caldav.py`
- `apps/executive-cli/src/executive_cli/connectors/imap.py`
- `apps/executive-cli/tests/*`

Verification commands:
```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas calendar sync
uv run execas mail sync --mailbox INBOX
uv run execas sync hourly --retries 2 --backoff-sec 5
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
```

Acceptance:
- Commands complete without secret leakage.
- INBOX-only behavior is preserved.
- No write operations to external systems.

### INT-QA-01 (QA/SET)

Goal:
- Produce integration quality verdict and risk classification.

Artifacts:
- `spec/operations/qa_verdict_yandex_integration.md`

Acceptance:
- Includes pass/fail per command path.
- Includes regression impact and residual risk.

### INT-OPS-01 (DevOps/SRE + TL)

Goal:
- Validate operational readiness for recurring sync and metrics.

Artifacts:
- `spec/operations/hourly_sync.md` (update if needed)
- `spec/operations/scrum_metrics.md` (confirm routine usage)

Acceptance:
- Runbook includes degraded-mode recovery.
- Metrics collection command included in operating cadence.

## Commit acceptance queue

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| pending | INT-DISC-01 | System Analyst/Product Owner | pending | waiting artifacts |
| pending | INT-ARCH-01 | Chief Architect | pending | waiting artifacts |
| pending | INT-EXEC-01 | Executive Assistant | pending | waiting commit + gates |
| pending | INT-QA-01 | QA/SET | pending | waiting artifacts |
| pending | INT-OPS-01 | DevOps/SRE + TL | pending | waiting artifacts |
