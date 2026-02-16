# TL Dispatch: SPEED-COST-01

**Owner:** Technical Lead  
**Date:** 2026-02-16  
**Baseline source:** `spec/operations/tl_plan_speed_cost_2026-02-16.md`

## Scope lock

- Objective: increase runtime speed and reduce avoidable service load without architecture rewrite.
- Guardrails:
  - no schema/ADR/time-model changes without Chief Architect approval;
  - no new secret handling paths;
  - maintain read-only external sync boundaries.

## Dispatch briefs

### SA-OPT-01 (System Analyst + Product Owner)

Goal:
- Produce FPF-based optimization requirement package from user complaint.
- Define measurable targets and acceptance commands.

Artifacts:
- `spec/TASKS/TASK_TL_SPEED_COST_01.md` (traceability and acceptance checks).

Acceptance:
- Problem frame and assumptions explicit.
- SLO/KPI targets measurable.
- Scope boundaries and non-goals explicit.

### ARCH-OPT-01 (Chief Architect)

Goal:
- Issue architecture verdict for each optimization candidate.

Artifacts:
- architecture verdict section in this dispatch file (or dedicated architecture note).

Acceptance:
- Each candidate marked: `approved now` / `defer` with reason.
- Any ADR-required item explicitly marked as approval-gated.

### EA-OPT-01 (Executive Assistant)

Goal:
- Implement approved low-risk optimizations.

Candidate file scope:
- `apps/executive-cli/src/executive_cli/sync_runner.py`
- `apps/executive-cli/src/executive_cli/cli.py`
- `apps/executive-cli/src/executive_cli/sync_service.py`
- `apps/executive-cli/src/executive_cli/connectors/caldav.py`
- `apps/executive-cli/tests/test_sync_hourly.py`
- `apps/executive-cli/tests/test_calendar_sync.py`
- `apps/executive-cli/tests/test_mail_sync.py`

Verification commands:
```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

Acceptance:
- No regressions in existing sync behavior.
- Speed-focused changes are covered by tests/evidence.
- Security redaction behavior unchanged.

### QA-OPT-01 (QA/SET)

Goal:
- Provide independent quality and risk verdict.

Artifacts:
- gate evidence + risk notes in final QA section.

Acceptance:
- Includes timing/attempt evidence for changed paths.
- Confirms no degradation in fallback/error paths.

### OPS-OPT-01 (DevOps/SRE)

Goal:
- Update runbook metrics and alert thresholds.

File scope:
- `spec/operations/hourly_sync.md`

Acceptance:
- Monitoring points for latency/degraded ratio documented.
- Recovery instructions include performance incidents.

## Commit acceptance queue

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| pending | SA-OPT-01 | System Analyst + Product Owner | pending | task package |
| pending | ARCH-OPT-01 | Chief Architect | pending | architecture verdict |
| pending | EA-OPT-01 | Executive Assistant | pending | code + tests + gates |
| pending | QA-OPT-01 | QA/SET | pending | independent quality verdict |
| pending | OPS-OPT-01 | DevOps/SRE | pending | runbook update |

## Parallel lanes

| Lane | Task | Role owner | Dependency | Locked files |
|---|---|---|---|---|
| A | SA-OPT-01 | System Analyst | none | `spec/TASKS/TASK_TL_SPEED_COST_01.md` |
| B | ARCH-OPT-01 | Chief Architect | hard(A) | `spec/AGENT_RUNTIME.md`, `spec/AGENT_RUNTIME_ADAPTERS.md`, `spec/ARCH_DECISIONS.md` |
| C | EA-OPT-01 | Executive Assistant | hard(B) | `apps/executive-cli/src/executive_cli/cli.py`, `apps/executive-cli/src/executive_cli/sync_runner.py`, `apps/executive-cli/src/executive_cli/sync_service.py`, `apps/executive-cli/src/executive_cli/connectors/caldav.py` |
| D | QA-OPT-01 | QA/SET | hard(C) | `apps/executive-cli/tests/*` |
| E | OPS-OPT-01 | DevOps/SRE | soft(C) | `spec/operations/hourly_sync.md` |

