# TASK TL-BOOTSTRAP-01: Technical Lead Orchestration Cycle

**Author:** Technical Lead  
**Date:** 2026-02-15  
**Purpose:** validate end-to-end Technical Lead workflow (plan -> dispatch -> acceptance -> push).

---

## Goal

Run one controlled delivery cycle where Technical Lead:
1. aligns a short plan with the user;
2. delegates tasks to role-specific agents;
3. accepts or rejects commits by evidence;
4. pushes accepted scope to remote repository.

---

## Inputs

- `AGENTS.md` (role authority and push guardrails)
- `agents/technical_lead/SKILL.md`
- `spec/AGENT_RUNTIME.md`
- `spec/AGENT_RUNTIME_ADAPTERS.md`
- `spec/templates/PREFLIGHT_STAMP_TEMPLATE.md`
- `spec/operations/tl_plan_48h.md`

---

## Scope

In scope:
- planning and sequencing for 2-3 tasks;
- assignment by role (Chief Architect, EA, Developer Helper, Business Coach when needed);
- commit acceptance ledger and final push decision.

Out of scope:
- overriding Chief Architect authority on schema/ADR/integration/time-model;
- force push;
- bypassing quality gates.

---

## Technical Lead workflow

### 1) Plan alignment with user

- Confirm objective, priorities, and next 48h scope.
- Freeze baseline in `spec/operations/tl_plan_48h.md`.

### 2) Dispatch tasks

- Create role-scoped briefs with:
  - goal;
  - files in scope;
  - verification commands;
  - acceptance criteria.
- Require minimal preflight stamp before implementation tasks.

### 3) Review deliverables

For each incoming commit:
- verify 7-section gate report;
- verify role authority boundaries;
- verify quality-gate evidence;
- verify no secret leakage and no policy violations.

Verdict:
- `accepted` if all checks pass;
- `rejected` with explicit remediation if any check fails.

### 4) Push gate

Push allowed only if:
- commit is accepted;
- task is in approved baseline;
- quality gates passed;
- target branch is explicit;
- push is non-force.

---

## Commit Acceptance Ledger (required in TL gate report)

Use this table in TL implementation handoff:

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| `<sha>` | `<id>` | `<role>` | `accepted/rejected` | `<tests/coverage/gate refs>` |

---

## Verification commands

```bash
cd /Users/gaidabura/Agentura
git status --short --branch
git log --oneline -n 20
rg -n "Plan baseline|Task ownership|Acceptance criteria|Integration/push gate" spec/operations/tl_plan_48h.md
rg -n "Goal|Scope|workflow|Commit Acceptance Ledger|Verification commands" spec/TASKS/TASK_TL_BOOTSTRAP_01.md
```

---

## Acceptance criteria

- [ ] `spec/operations/tl_plan_48h.md` exists and defines baseline scope for 48h.
- [ ] At least 2 role-scoped tasks are dispatched from this baseline.
- [ ] Every reviewed commit has explicit `accepted/rejected` verdict and evidence.
- [ ] Push includes only accepted commits from baseline scope.
- [ ] No authority boundary violations are approved by Technical Lead.

---

## Rollback notes

- If any baseline task becomes blocked by architecture/security constraints, pause downstream tasks, request user re-alignment, and update `tl_plan_48h.md` before continuing.

