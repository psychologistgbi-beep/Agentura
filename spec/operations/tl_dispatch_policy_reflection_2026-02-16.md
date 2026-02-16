# TL Dispatch: POLICY-REFLECTION-01

**Owner:** Technical Lead  
**Date:** 2026-02-16  
**Trigger:** user request to formalize changed policies across project artifacts

## Baseline task

- `spec/TASKS/TASK_TL_POLICY_REFLECTION_01.md`

## Scope lock

- Policy/runtime documentation alignment only.
- No schema/migration/time-model/integration-approach changes.
- No credential value handling in artifacts.

## Lane map (approved)

| Lane ID | Owner role | Goal | File scope | Dependency |
|---|---|---|---|---|
| `SA-POL-INV-01` | System Analyst | Build mismatch inventory and traceability map | `spec/*`, `agents/*` (read + report) | none |
| `DEVHELP-POL-TASK-01` | Developer Helper | Convert inventory into executable doc-edit checklist | `spec/TASKS/`, `spec/operations/` | after `SA-POL-INV-01` |
| `EA-POL-ALIGN-01` | Executive Assistant | Apply wording alignment and run quality gates | policy/runtime docs + templates | after `DEVHELP-POL-TASK-01` |
| `QA-POL-VERIFY-01` | QA/SET | Verify no residual policy drift and no security regression in wording | grep evidence + gate evidence | after `EA-POL-ALIGN-01` |
| `TL-ACCEPT-POL-01` | Technical Lead | Accept/reject diff package and push accepted result | acceptance ledger + push | after `QA-POL-VERIFY-01` |

## Required acceptance evidence per lane

1. `SA-POL-INV-01`
- inventory table: file, old wording, target wording, risk
- traceability links to AGENTS policy source

2. `DEVHELP-POL-TASK-01`
- ordered checklist with rollback notes
- explicit "no ADR-required area changed" statement

3. `EA-POL-ALIGN-01`
- changed file list with concise rationale
- quality-gate outputs:
  - `uv run pytest -q`
  - `uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80`

4. `QA-POL-VERIFY-01`
- grep output showing no stale high-priority policy wording remains
- confirmation that no secrets were introduced into repository files

5. `TL-ACCEPT-POL-01`
- commit acceptance ledger with explicit verdict per commit
- push confirmation for accepted scope only

## Parallel metrics target (mandatory)

- configured parallel lanes: 5
- expected max simultaneous lanes: 2

## Blocking conditions

- Any proposed wording that weakens security guarantees.
- Any change that silently broadens integration permissions.
- Missing quality-gate evidence for EA lane.

## Completion condition

Dispatch is complete only when policy docs, role skills, templates, and runbooks are consistent with the updated secret/runtime policy and TL acceptance ledger is published.
