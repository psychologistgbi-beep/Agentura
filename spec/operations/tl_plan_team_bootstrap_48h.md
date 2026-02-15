# TL Plan 48h: Team Bootstrap (Scrum)

**Owner:** Technical Lead  
**Date:** 2026-02-15  
**Horizon:** next 48 hours

## Objective

Build a production-ready agent team for Scrum delivery with clear roles, standards, and governance:
- add missing roles (including System Analyst);
- define team architecture and operating standards;
- ship runnable role profiles and runtime mapping;
- accept commits only with evidence and quality gates.

## Alignment lock

- Session objective: `TEAM-BOOTSTRAP-01`
- Aligned with user on `2026-02-15` to complete this block now.
- Baseline frozen for this batch; scope additions require user re-alignment.

## Plan baseline (approved scope)

1. **ARCH-TEAM-01 (Chief Architect): agent team architecture + standards**
   - Describe team architecture for Scrum collaboration.
   - Define mandatory standards for all roles.

2. **DEV-TEAM-01 (Executive Assistant as developer): implement new agents and runtime mapping**
   - Add new role skill profiles.
   - Update core runtime/authority docs and role launcher commands.

3. **TL-ACCEPT-01 (Technical Lead): review, accept/reject, integrate**
   - Review incoming commits against scope, standards, and quality gates.
   - Update acceptance ledger with explicit verdicts.

## Task ownership

| Task | Role | Deliverable |
|---|---|---|
| ARCH-TEAM-01 | Chief Architect | Team architecture and standards docs |
| DEV-TEAM-01 | Executive Assistant | Role profiles + policy/runtime implementation |
| TL-ACCEPT-01 | Technical Lead | Acceptance ledger + push decision |

## Acceptance criteria (batch)

- Both role-scoped tasks (`ARCH-TEAM-01`, `DEV-TEAM-01`) have committed artifacts.
- New roles are discoverable via `agents/<role>/SKILL.md`.
- Role-to-skill mapping is updated consistently in policy/runtime docs.
- Standards are explicit and referenced by role profiles.
- Quality gates pass before final push.

## Integration/push gate (Technical Lead)

Before push:
- commit is in baseline scope;
- commit has explicit TL verdict;
- quality-gate evidence is present;
- no authority-boundary violations;
- push target is explicit and non-force.

## Risks

1. **Role overlap ambiguity:** new roles may duplicate responsibilities.  
   Mitigation: define boundaries and handoffs in architecture doc.
2. **Policy drift:** AGENTS/runtime docs may become inconsistent.  
   Mitigation: enforce synchronized mapping updates in one batch.
3. **Process inflation:** too much process reduces delivery speed.  
   Mitigation: keep standards minimal, measurable, and gate-based.

## Status board

- ARCH-TEAM-01: completed (accepted commit `d64f7db`)
- DEV-TEAM-01: completed (accepted commit `e742e17`)
- TL-ACCEPT-01: completed (acceptance ledger updated)
