# Agent Team Architecture (Scrum)

**Owner:** Chief Architect  
**Date:** 2026-02-15  
**Related standards:** `spec/TEAM_STANDARDS.md`

## 1. Purpose

Define an operational architecture for a multi-agent development team that can deliver business tasks under Scrum while preserving authority boundaries, quality gates, and security policy.

## 2. Role Topology

## Product and requirements layer

- Product Owner (PO): owns priorities, release value, acceptance by business outcome.
- System Analyst (SA): owns requirements quality, decomposition, and traceability.
- Business Coach (advisory): provides prioritization recommendations and focus coaching.

## Delivery governance layer

- Scrum Master (SM): owns process integrity and impediment removal.
- Technical Lead (TL): owns execution orchestration, task dispatch, commit acceptance, integration.
- Chief Architect (CA): owns architecture decisions, ADR governance, security guardrails.

## Execution layer

- Executive Assistant (EA): owns implementation in product scope.
- QA/SET: owns test strategy, regression quality, release confidence.
- DevOps/SRE: owns CI/CD reliability, operational runbooks, runtime stability.

## 3. Collaboration Flow

1. PO sets sprint priorities and acceptance outcomes.
2. SA translates priorities into implementable stories/tasks with traceability.
3. SM validates process readiness (DoR, WIP, ceremony health).
4. TL dispatches role-scoped tasks and freezes baseline.
5. CA approves ADR-required decisions and architecture boundaries.
6. EA implements scoped work.
7. QA/SET verifies behavior and non-regression evidence.
8. DevOps/SRE validates operational readiness and release reliability.
9. TL accepts/rejects commits and integrates accepted scope.
10. PO accepts sprint increment on business criteria.

## 4. Decision and Approval Gates

- Gate A (Backlog readiness): PO + SA + SM.
- Gate B (Architecture safety): CA approval for ADR-required scope.
- Gate C (Implementation quality): EA + QA/SET with quality-gate evidence.
- Gate D (Integration acceptance): TL accepts/rejects commit set.
- Gate E (Business acceptance): PO accepts increment in Sprint Review.

## 5. RACI (Condensed)

| Activity | R | A | C | I |
|---|---|---|---|---|
| Prioritize backlog | PO | PO | SA, BC | TL, SM |
| Define requirements | SA | PO | TL, EA | SM |
| Facilitate Scrum process | SM | SM | TL | Team |
| Approve ADR-required decisions | CA | CA | TL, SA | Team |
| Implement features | EA | TL | CA, QA/SET | PO |
| Verify quality and regressions | QA/SET | QA/SET | EA, TL | PO |
| Maintain CI/CD and runbooks | DevOps/SRE | DevOps/SRE | TL, QA/SET | Team |
| Accept/reject commits | TL | TL | CA, QA/SET | PO |

## 6. Handoff Contracts

- SA -> EA: requirements package with acceptance criteria, scope, dependencies, rollback note.
- EA -> QA/SET: implementation summary, changed files, test intent, known risks.
- QA/SET -> TL: verification verdict with failing/passing evidence.
- DevOps/SRE -> TL: operational readiness note (pipeline/runbook state).
- TL -> PO: increment summary with accepted commit list and residual risks.

## 7. Anti-patterns

- TL accepting commits without evidence.
- EA implementing outside baseline scope.
- SM overriding technical or architectural authority.
- PO bypassing DoR/DoD for urgent but undefined work.
- QA/SET sign-off without reproducible verification commands.

## 8. Expected Outcomes

- Reduced role ambiguity and less decision ping-pong.
- Predictable delivery through explicit gates.
- Higher release confidence through QA/SET + DevOps/SRE integration.
- Stronger business alignment via PO + SA partnership.
