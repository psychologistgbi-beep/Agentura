# TL Dispatch Batch: TEAM-BOOTSTRAP-01

**Owner:** Technical Lead  
**Date:** 2026-02-15  
**Baseline source:** `spec/operations/tl_plan_team_bootstrap_48h.md`

## Plan baseline

Scope locked to:
- `ARCH-TEAM-01` (Chief Architect): team architecture and role standards.
- `DEV-TEAM-01` (Executive Assistant/developer): implement role profiles and runtime policy updates.

No schema, migration, or time-model changes are authorized in this batch.

## Dispatch briefs

### ARCH-TEAM-01 (Chief Architect)

Goal:
- Describe target agent architecture for Scrum team operation.
- Define mandatory standards used by all roles.

Files in scope:
- `spec/operations/agent_team_architecture_scrum.md`
- `spec/TEAM_STANDARDS.md`
- `spec/TASKS/TASK_ARCH_TEAM_ARCHITECTURE_01.md` (if refinement needed)

Verification commands:
```bash
cd /Users/gaidabura/Agentura
rg -n "Scrum|Role|handoff|authority|standards|DoR|DoD|quality gates" spec/operations/agent_team_architecture_scrum.md spec/TEAM_STANDARDS.md
```

Acceptance criteria:
- Architecture scope is explicit (roles, handoffs, decision gates).
- Standards are measurable and actionable (not generic principles only).
- No authority conflict with `AGENTS.md` section 2.
- 7-section architecture gate report is present.

### DEV-TEAM-01 (Executive Assistant / Developer)

Goal:
- Add missing agent roles (including System Analyst) with concrete `SKILL.md` profiles.
- Update policy/runtime role mapping and role-launcher support.

Files in scope:
- `AGENTS.md`
- `CLAUDE.md`
- `spec/AGENT_RUNTIME.md`
- `spec/AGENT_RUNTIME_ADAPTERS.md`
- `spec/templates/PREFLIGHT_STAMP_TEMPLATE.md`
- `agents/system_analyst/SKILL.md`
- `agents/product_owner/SKILL.md`
- `agents/scrum_master/SKILL.md`
- `agents/qa_set/SKILL.md`
- `agents/devops_sre/SKILL.md`
- `scripts/codex-role`
- `scripts/codex-role-aliases.sh`
- `spec/operations/codex_role_commands.md`
- `spec/TASKS/TASK_DEV_TEAM_ROLES_01.md` (if refinement needed)

Verification commands:
```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

Acceptance criteria:
- New roles are reflected in role-to-skill mapping across all runtime docs.
- Each new role has explicit mission, output contract, and authority limits.
- Launcher commands include new roles without breaking existing aliases.
- Quality gates pass with explicit evidence.
- 7-section gate report is present.

## Commit acceptance queue

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| pending | ARCH-TEAM-01 | Chief Architect | pending | waiting for commit + gate report |
| pending | DEV-TEAM-01 | Executive Assistant | pending | waiting for commit + gate report |

## Acceptance review snapshot

Pending (will be updated after commit review).

## Push gate state

- Target branch: `main` (remote `origin/main`)
- Current state: `blocked`
- Blockers:
  - no accepted commits in this batch yet
