# TL Plan: Speed & LLM Cost Optimization (Baseline)

**Owner:** Technical Lead  
**Date:** 2026-02-16  
**Horizon:** next 72 hours

## Objective

Address user-reported speed concerns and reduce avoidable LLM/service load without radical architecture changes.

## User signal (baseline trigger)

- User reports low perceived project speed and likely overuse of agentic flow in tasks that should be algorithmic.
- User requests practical optimization ideas that improve speed and reduce service load.

## Current-state summary (verified)

- Calendar and mail sync are already algorithmic (CalDAV/IMAP + SQLite), no LLM calls in sync path.
- Planning and review generation are deterministic local logic.
- Operational bottlenecks are mostly in sync orchestration and process parallelism, not model inference.

## Plan baseline (approved execution scope)

1. **SA-OPT-01 (System Analyst + Product Owner):**
   - Produce optimization requirement package with measurable SLO/KPI targets:
     - hourly sync p95 latency;
     - per-run DB touch budget;
     - explicit `LLM calls = 0` for sync runtime path.
   - Deliver traceability from user complaint -> stories -> tasks -> verification.

2. **ARCH-OPT-01 (Chief Architect):**
   - Architecture review for low-risk performance changes in sync path.
   - Explicit approval/defer matrix for:
     - parallel execution of calendar/mail in hourly orchestration;
     - incremental token path priority for CalDAV;
     - bounded sync window controls.

3. **EA-OPT-01 (Executive Assistant):**
   - Implement approved low-risk speed optimizations in code.
   - Keep behavior deterministic and security constraints unchanged.

4. **QA-OPT-01 (QA/SET):**
   - Add/extend performance regression evidence for sync flows.
   - Validate no functional regressions and no secret leakage in degraded/error paths.

5. **OPS-OPT-01 (DevOps/SRE):**
   - Update hourly runbook with performance monitoring points and alert thresholds.

6. **TL-ACC-01 (Technical Lead):**
   - Accept/reject lane commits by scope + gates + traceability.
   - Push accepted range only.

## Prioritized optimization candidates (for execution)

1. Parallelize hourly calendar/mail sync execution.
2. Reduce avoidable full-snapshot fetches in CalDAV path.
3. Reduce full-memory scans for upsert preparation in sync service.
4. Add runtime metrics output for latency and row counts.

## Out of scope

- Fundamental architecture rewrite.
- Schema changes without explicit Chief Architect approval.
- Any change that introduces new write scopes in external providers.

## Acceptance criteria (batch-level)

- User complaint is traceably mapped to executable tasks and measurable targets.
- At least one approved speed optimization implemented and validated.
- Quality gates passed.
- Security/read-only boundaries unchanged.
- TL final report includes business-result status and evidence.

## Execution status

- Batch status: completed.
- Delivery mode: full-plan execution in one batch.
