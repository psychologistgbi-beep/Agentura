# Team Standards (Scrum Delivery)

**Owner:** Chief Architect  
**Effective date:** 2026-02-15  
**Applies to:** all roles defined in `AGENTS.md`

## 1. Delivery Framework

- Team operates in Scrum with 2-week sprints.
- Sprint Goal is mandatory before sprint start.
- Ceremonies and cadence:
  - Sprint Planning: once per sprint, up to 120 minutes.
  - Daily Scrum: every work day, 15 minutes.
  - Backlog Refinement: 2 sessions per week, 45 minutes each.
  - Sprint Review: end of sprint, 60 minutes.
  - Sprint Retrospective: end of sprint, 45 minutes.

## 2. Backlog Standards

- Work decomposition: `Epic -> Feature -> Story -> Task`.
- No work starts without backlog traceability.
- Every Story must have:
  - business outcome;
  - acceptance criteria;
  - scope boundaries;
  - dependency notes.

## 3. Definition of Ready (DoR)

A Story/Task is ready only when all conditions are met:
- owner role is explicit;
- acceptance criteria are testable;
- affected files/components are known;
- architecture/security constraints are listed;
- verification commands are defined.

## 4. Definition of Done (DoD)

A change is done only when all conditions are met:
- implementation matches approved scope;
- code/docs reviewed by assigned reviewer role;
- mandatory quality gates pass:
  - `uv run pytest -q`
  - `uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80`
  - migration integrity check when applicable;
- security checks pass (no secrets, least privilege, authority boundaries respected);
- gate report includes all 7 required sections from `spec/AGENT_RUNTIME.md`.

## 5. Architecture and ADR Standards

- ADR is mandatory before changes to:
  - schema/migrations;
  - time model/timezone logic;
  - planning/scoring rules;
  - integration approach;
  - security policy.
- No implementation may bypass Chief Architect approval for ADR-required areas.
- Rollback path must be defined for every non-trivial decision.

## 6. Engineering Standards

- Branch strategy: short-lived branches with `codex/` prefix when branch work is needed.
- Atomic commits: one commit equals one logical change.
- Diff discipline: prefer < 300 LOC per commit where practical.
- No silent spec divergence: update relevant spec in the same change.
- Determinism requirement: planning and scoring behavior must be deterministic for identical inputs.

## 7. QA/SET Standards

- Test strategy must cover:
  - happy path;
  - boundary conditions;
  - regressions for touched behavior.
- Test evidence must be included in gate report.
- Escaped defects must be linked back to missing acceptance criteria or missing tests in retro notes.

## 8. DevOps/SRE Standards

- CI pipeline must block merges on failing tests/coverage.
- Operational runbooks must define degraded mode and recovery steps.
- Any scheduled automation must include overlap protection and failure signaling.

## 9. Role Interaction Standards

- System Analyst owns requirement quality and traceability.
- Product Owner owns backlog priority and acceptance on business value.
- Scrum Master owns process health and impediment removal.
- Technical Lead owns delivery orchestration and commit acceptance.
- Chief Architect owns architecture guardrails and ADR governance.
- Executive Assistant owns implementation delivery in product scope.
- QA/SET owns test strategy and quality evidence.
- DevOps/SRE owns delivery pipeline and operational reliability.
- Business Coach remains advisory and does not mutate source of truth.

## 10. Metrics Standards

Mandatory metrics per sprint:
- Sprint Goal success rate.
- Carry-over rate.
- Lead time from ready to done.
- Defect escape rate.
- Quality gate pass rate.

## 11. Escalation Standards

Escalate to user and pause downstream work when any of the following occurs:
- scope changes beyond approved baseline;
- authority conflict between roles;
- quality-gate failure without agreed mitigation;
- security or secrets policy violation.

## 12. Parallel Delivery Standards

- Parallel lanes are allowed only when lane readiness is satisfied (owner, scope, dependency, checks).
- Recommended maximum active lanes per batch: 4.
- Lane dependency tags are mandatory: `none`, `soft`, `hard`.
- High-risk shared files must have a TL lock owner before concurrent execution.
- Each lane must produce an independent gate report and acceptance evidence.
- Integration order defaults to: architecture/requirements -> implementation -> quality -> operations.
- Operational template for active batches: `spec/templates/PARALLEL_WORKBOARD_TEMPLATE.md`.
- Protocol reference: `spec/operations/parallel_delivery_protocol.md`.
