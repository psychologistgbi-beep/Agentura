# TL Dispatch: INGEST-IMPL-01

**Owner:** Technical Lead
**Date:** 2026-02-16
**Baseline source:** User-approved implementation of previously designed ingestion functionality (ADR-11 scope).

## Scope lock

- Objective: implement ingestion pipeline and CLI flows defined in `TASK_INGEST_PIPELINE_DESIGN.md`.
- In-scope:
  - migration and model additions for ingest schema;
  - extraction/classification/dedup/routing runtime;
  - shared task-creation service and CLI integration;
  - tests and quality evidence.
- Out-of-scope:
  - new architecture decisions outside ADR-11;
  - force-push, scope expansion, unrelated backlog tasks.

## Dispatch briefs

### EA-INGEST-IMPL-01 (Executive Assistant)

Goal:
- Implement ingestion pipeline runtime and CLI commands per ADR-11.

Artifacts:
- `apps/executive-cli/alembic/versions/a7b9c2d4e6f1_add_ingest_pipeline_schema.py`
- `apps/executive-cli/src/executive_cli/models.py`
- `apps/executive-cli/src/executive_cli/db.py`
- `apps/executive-cli/src/executive_cli/config.py`
- `apps/executive-cli/src/executive_cli/task_service.py`
- `apps/executive-cli/src/executive_cli/llm/*`
- `apps/executive-cli/src/executive_cli/ingest/*`
- `apps/executive-cli/src/executive_cli/cli.py`

Acceptance:
- `execas ingest` command group available with meeting/dialogue/email/review/accept/skip/status.
- pipeline routes candidates by confidence and dedup policy.
- existing `task capture` uses shared task service path.

### QA-INGEST-IMPL-01 (QA/SET)

Goal:
- Provide regression and schema evidence for ingest implementation.

Artifacts:
- `apps/executive-cli/tests/test_ingest_schema.py`
- `apps/executive-cli/tests/test_ingest_pipeline.py`
- quality-gate command outputs in gate report.

Acceptance:
- new tests pass and verify core flows (draft/accept, auto-create by email, dedup skip).
- global quality gates pass (tests, coverage, migration integrity).

## Commit acceptance queue

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| ingest-impl batch (this delivery commit) | EA-INGEST-IMPL-01 | Executive Assistant | accepted | ingest modules + migration + CLI + shared task service |
| ingest-impl batch (this delivery commit) | QA-INGEST-IMPL-01 | QA/SET | accepted | ingest tests + green quality gates |
| (this file + gate report) | TL gate | Technical Lead | accepted | scope lock + acceptance ledger + push readiness |

## Parallel lanes

| Lane | Task | Role owner | Dependency | Locked files |
|---|---|---|---|---|
| A | EA-INGEST-IMPL-01 | Executive Assistant | none | `apps/executive-cli/src/executive_cli/cli.py`, ingest modules, migration, models |
| B | QA-INGEST-IMPL-01 | QA/SET | hard(A) | ingest test files and quality evidence |
| C | TL-ACCEPT-INGEST-01 | Technical Lead | hard(B) | dispatch ledger + gate report + push |

## Execution snapshot

- Configured participating roles: 7
- Observed active role sessions in this batch execution: 3 (Technical Lead + Executive Assistant + QA/SET, combined session)
- Configured max parallel lanes: 5
- Observed max parallel lanes during implementation: 1
