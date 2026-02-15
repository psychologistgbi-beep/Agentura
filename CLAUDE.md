# Agentura — Claude Code Project Instructions

This file is auto-loaded by Claude Code as project-level context.

## Project

Agentura is a personal Executive Assistant system built as a Python CLI (`apps/executive-cli/`). SQLite + SQLModel/Alembic, Typer CLI, deterministic planning, FTS5 search.

## Core policy documents (read before any task)

| Document | Purpose |
|----------|---------|
| `AGENTS.md` | Operating model: agent roles, authority boundaries, quality gates, security policy |
| `spec/AGENT_RUNTIME.md` | Two-layer runtime model, instruction priority, verification gate protocol |
| `spec/AGENT_RUNTIME_ADAPTERS.md` | Per-LLM adapter details including preflight smoke-checks |
| `spec/ARCH_DECISIONS.md` | Architecture Decision Records (ADR-01 through ADR-10) |
| `spec/TECH_SPEC.md` | Requirements and CLI contract |
| `spec/ACCEPTANCE.md` | Acceptance criteria (MVP + Post-MVP) |

## Rules

1. **Authority boundaries are identical regardless of LLM.** The same AGENTS.md section 2 authority table applies to Claude, Codex, and any other runtime. Do not exceed your assigned role's scope.

2. **Role-based command scope is mandatory.**
   - Technical Lead: plan alignment with user, task orchestration, commit acceptance, guarded `git push`.
   - EA: implementation in `apps/executive-cli`, tests/migrations, `git add/commit`.
   - Chief Architect: docs/spec/ADR/review work only.
   - Developer Helper: planning docs only.
   - Business Coach: advisory output only.
   - System Analyst: requirements and traceability artifacts only.
   - Product Owner: backlog priority and acceptance decisions.
   - Scrum Master: process/flow artifacts and impediment handling.
   - QA/SET: test strategy/evidence and quality tooling in scope.
   - DevOps/SRE: CI/CD and operational runbooks in scope.

   **Role-to-skill mapping (mandatory):**
   | Role | Required skill path |
   |------|---------------------|
   | Chief Architect | `agents/chief_architect/SKILL.md` |
   | Technical Lead | `agents/technical_lead/SKILL.md` |
   | Executive Assistant (EA) | `agents/executive_assistant/SKILL.md` |
   | Developer Helper | `agents/developer_helper/SKILL.md` |
   | Business Coach | `agents/business_coach/SKILL.md` |
   | System Analyst | `agents/system_analyst/SKILL.md` |
   | Product Owner | `agents/product_owner/SKILL.md` |
   | Scrum Master | `agents/scrum_master/SKILL.md` |
   | QA/SET | `agents/qa_set/SKILL.md` |
   | DevOps/SRE | `agents/devops_sre/SKILL.md` |

3. **Safe baseline commands should run without new approvals after runtime policy setup.**
   - `git status`, `git diff`, `git diff --name-only`
   - `ls`, `cat`, `sed -n`, `rg`
   - EA flow: `git add <paths>`, `git commit -m`, `uv run pytest ...`, `uv run execas <local-only command>`

4. **Always-manual approval actions (never auto-allow).**
   - `git push` for roles other than Technical Lead, and any `git push --force*`
   - Destructive operations (`rm -rf`, `git reset --hard`, branch delete, file delete)
   - External services with real credentials
   - Exception for migration integrity quality gate only: `rm -f .data/execas.sqlite` or `rm -f apps/executive-cli/.data/execas.sqlite`, when paired with `uv run execas init`

5. **Quality gates are mandatory.** Every commit must pass:
   ```bash
   cd apps/executive-cli
   uv run pytest -q
   uv run pytest --cov=executive_cli --cov-fail-under=80
   ```

6. **Verification gate for architecture and development tasks.** Every task deliverable (architecture or implementation) must include a structured gate report with 7 sections: role confirmation, decisions, artifacts, traceability, implementation handoff, risks, ADR status. See `spec/AGENT_RUNTIME.md` section 4.

7. **Use minimal preflight before implementation.** Run the runtime preflight smoke-check from `spec/AGENT_RUNTIME_ADAPTERS.md` (Claude section): instruction injection, R2 skill discovery, task discovery, and permissions readiness. If baseline-safe commands require new approvals, or if the assigned role SKILL file is missing/unreadable, status is `not ready to execute`. For implementation tasks, AGENTS.md-only fallback is prohibited.

8. **ADR before schema change.** No migration without an approved ADR in `spec/ARCH_DECISIONS.md`.

9. **Secrets never in repo.** Credentials only in env vars. `.gitignore` covers `.env`, `*.pem`, `*.key`, `credentials.*`.

10. **Single writer for SQLite.** Only the EA role writes to the database (ADR-09). Other roles produce proposals.

11. **Atomic commits.** One commit = one logical change. Commit message describes what and why.

## Key paths

- CLI source: `apps/executive-cli/src/executive_cli/`
- Models: `apps/executive-cli/src/executive_cli/models.py`
- Migrations: `apps/executive-cli/alembic/versions/`
- Tests: `apps/executive-cli/tests/`
- Agent skills: `agents/<role>/SKILL.md`
- Task specs: `spec/TASKS/TASK_*.md`
