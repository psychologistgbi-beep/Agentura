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

2. **Quality gates are mandatory.** Every commit must pass:
   ```bash
   cd apps/executive-cli
   uv run pytest -q
   uv run pytest --cov=executive_cli --cov-fail-under=80
   ```

3. **Verification gate for architecture and development tasks.** Every task deliverable (architecture or implementation) must include a structured gate report with 7 sections: role confirmation, decisions, artifacts, traceability, implementation handoff, risks, ADR status. See `spec/AGENT_RUNTIME.md` section 4.

4. **Preflight before implementation.** Before starting any implementation task, run the runtime preflight smoke-check defined in `spec/AGENT_RUNTIME_ADAPTERS.md` (Claude section). A task cannot proceed until preflight passes.

5. **ADR before schema change.** No migration without an approved ADR in `spec/ARCH_DECISIONS.md`.

6. **Secrets never in repo.** Credentials only in env vars. `.gitignore` covers `.env`, `*.pem`, `*.key`, `credentials.*`.

7. **Single writer for SQLite.** Only the EA role writes to the database (ADR-09). Other roles produce proposals.

8. **Atomic commits.** One commit = one logical change. Commit message describes what and why.

## Key paths

- CLI source: `apps/executive-cli/src/executive_cli/`
- Models: `apps/executive-cli/src/executive_cli/models.py`
- Migrations: `apps/executive-cli/alembic/versions/`
- Tests: `apps/executive-cli/tests/`
- Agent skills: `agents/<role>/SKILL.md`
- Task specs: `spec/TASKS/TASK_*.md`
