# TL Dispatch: ARCH-INGEST-01

**Owner:** Technical Lead
**Date:** 2026-02-16
**Baseline source:** User requirement (populate GTD backlog from meetings, dialogues, email)

## Scope lock

- Objective: design task ingestion pipeline from three input channels (meeting protocols, assistant dialogues, incoming email) into GTD backlog.
- Guardrails:
  - docs-only batch — no code, no migrations, no CLI changes;
  - no changes to existing tables (`tasks`, `emails`, `task_email_links`);
  - ADR-09 (EA single writer) preserved;
  - ADR-10 privacy boundary (no email body) preserved.

## Dispatch briefs

### SA-INGEST-01 (System Analyst)

Goal:
- Analyze three input channels (C1 meeting, C2 dialogue, C3 email).
- Define pipeline stages, data model extensions, and human-in-the-loop policy.
- Map channel-specific constraints (format, frequency, privacy).

Artifacts:
- `spec/TASKS/TASK_INGEST_PIPELINE_DESIGN.md` (sections 1–4, 7–8).

Acceptance:
- All 3 channels described with input format, method, frequency, storage.
- Pipeline described end-to-end: Extract → Classify → Deduplicate → Route.
- Human-in-the-loop policy explicit with confidence thresholds.
- Privacy constraints per channel documented.

### ARCH-INGEST-01 (Chief Architect)

Goal:
- Design data model (3 new tables), LLM isolation boundary, and integration with ADR-10 schema.
- Author ADR-11.
- Update EXECUTION_PLAN with Phase 7.

Artifacts:
- `spec/TASKS/TASK_INGEST_PIPELINE_DESIGN.md` (sections 5–6, 9–10).
- `spec/ARCH_DECISIONS.md` (ADR-11).
- `spec/EXECUTION_PLAN.md` (Phase 7).

Acceptance:
- Schema extensions defined without modifying existing tables.
- LLM boundary clearly separated from deterministic stages.
- ADR-11 has all required sections (context, decision, consequences, alternatives, rollback).
- Phase 7 has dependency graph and verify commands.

## Commit acceptance queue

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| `6d11ea1` | SA-INGEST-01 | System Analyst | accepted | `TASK_INGEST_PIPELINE_DESIGN.md` sections 1–4, 7–8 |
| `6d11ea1` | ARCH-INGEST-01 | Chief Architect | accepted | `TASK_INGEST_PIPELINE_DESIGN.md` sections 5–6, 9–10; ADR-11; Phase 7 |
| (this file) | TL gate | Technical Lead | pending TL acceptance | this dispatch + gate report |

## Parallel lanes

| Lane | Task | Role owner | Dependency | Locked files |
|---|---|---|---|---|
| A | SA-INGEST-01 | System Analyst | none | `spec/TASKS/TASK_INGEST_PIPELINE_DESIGN.md` (sections 1–4, 7–8) |
| B | ARCH-INGEST-01 | Chief Architect | hard(A) | `spec/ARCH_DECISIONS.md`, `spec/EXECUTION_PLAN.md`, `spec/TASKS/TASK_INGEST_PIPELINE_DESIGN.md` (sections 5–6, 9–10) |

## Execution snapshot

- Configured participating roles: 7
- Observed active role sessions in this batch execution: 2 (Chief Architect + System Analyst, combined in single session)
- Configured max parallel lanes: 5
- Observed max parallel lanes during implementation: 1 (sequential: SA analysis → Architect design, same session)
