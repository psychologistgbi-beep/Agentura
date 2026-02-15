# TASK DEV-TEAM-01: Implement Additional Agent Roles

**Author:** Technical Lead  
**Assigned role:** Executive Assistant (Developer)  
**Date:** 2026-02-15

## Goal

Implement additional agent roles required for Scrum operation (including System Analyst), wire them into runtime policy mapping, and ensure role launch tooling supports the new roles.

## In scope

- Add `SKILL.md` files for new roles:
  - System Analyst
  - Product Owner
  - Scrum Master
  - QA/SET
  - DevOps/SRE
- Update role definitions and authority mapping in policy/runtime docs.
- Update preflight template role list.
- Update role launcher scripts and command docs.

## Out of scope

- Product feature changes in `apps/executive-cli/src/`.
- Database schema/migration changes.
- Integration credential handling changes.

## Files to touch

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

## Commands

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

## Acceptance checks

- New roles appear in role-to-skill mapping tables in all runtime policy docs.
- Every new role profile includes: role, mission, required inputs, output contract, and safety/authority rules.
- Launcher supports new role shortcuts without breaking existing commands.
- Quality gates pass and evidence is attached.
- Deliverable includes 7-section gate report.

## Rollback notes

- If mapping consistency fails, keep SKILL files and revert runtime docs to last consistent state, then re-apply mappings in one atomic commit.
