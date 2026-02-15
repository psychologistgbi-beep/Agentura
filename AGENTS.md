# Agents — Agentura Operating Model

This document defines the agent roles, authority boundaries, and operational rules for the Agentura project.

---

## 1. Agent Roles

### Chief Architect

**Owner:** Architecture, schema, security, quality gates.

Responsibilities:
- Author and maintain Architecture Decision Records (ADRs) in `spec/ARCH_DECISIONS.md`.
- Review and approve schema/migration changes.
- Define and enforce security policies (secrets, least-privilege, MCP boundaries).
- Maintain quality gates (tests, coverage, migration integrity).
- Design integration interfaces (MCP connectors, CalDAV, IMAP).
- Provide architecture review checklists for PRs touching schema, time handling, or integrations.

Does NOT:
- Implement product features directly (delegates to Executive Assistant / feature agents).
- Execute long refactors without an approved ADR/RFC.
- Store or request credentials in plaintext.

### Executive Assistant (EA)

**Owner:** Feature delivery, SQLite writes, CLI commands.

Responsibilities:
- Implement CLI commands and business logic per spec.
- Act as the single writer to SQLite (ADR-09).
- Execute task plans produced by the planner.
- Apply changes only after user confirmation.

Does NOT:
- Change schema or migrations without Chief Architect review.
- Bypass quality gates.

### Developer Helper

**Owner:** Task planning, spec-to-implementation decomposition.

Responsibilities:
- Convert specs into granular tasks under `spec/TASKS/`.
- Ensure each task has goal, scope, files, commands, acceptance checks, rollback notes.
- Verify implementation against specs.

Profile: `agents/developer_helper/SKILL.md`

### Business Coach (advisory)

**Owner:** Goal alignment, priority coaching.

Responsibilities:
- Help user clarify goals, commitments, and priorities.
- Produce recommendations (not commands).
- Cannot modify SQLite or any source of truth directly (ADR-09).

---

## 2. Authority & Boundaries

| Change type                         | Who can propose | Who must approve    |
|-------------------------------------|-----------------|---------------------|
| Schema / migrations                 | Any agent       | Chief Architect     |
| ADR (new or amend)                  | Any agent       | Chief Architect     |
| CLI commands (new or modify)        | EA, Dev Helper  | Chief Architect (schema-touching) or self (pure feature) |
| Scoring / planning weights          | EA              | Chief Architect (ADR required) |
| Integration design (MCP, CalDAV)    | Chief Architect | Chief Architect     |
| Time model / timezone changes       | Any agent       | Chief Architect (ADR required) |
| Test infrastructure                 | Any agent       | Self                |
| Documentation / templates           | Any agent       | Self                |

---

## 3. Architecture Decision Workflow

### When is an ADR required?

An ADR **must** be written before implementation when any of these change:
- Database schema or migrations
- Time model or timezone handling
- Planning algorithm scoring weights or rules
- Weekly review scoring or output policy
- Integration approach (MCP vs direct, new connector)
- Security policy (credential handling, permission model)

### ADR format

```
## ADR-NN: <Title>

**Context:** Why this decision is needed.
**Decision:** What we decided.
**Consequences:** What follows from this decision.
**Alternatives considered:** What else was evaluated and why it was rejected.
**Rollback:** How to reverse this decision if needed.
```

### Storage

All ADRs live in `spec/ARCH_DECISIONS.md`, numbered sequentially (ADR-01, ADR-02, ...).

Templates for ADRs and other architecture artifacts live in `spec/templates/`.

---

## 4. Quality Gates

Every change must pass these gates before merge/commit:

### Tests
```bash
cd apps/executive-cli
uv run pytest -q
```

### Coverage
```bash
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
```

### Migration integrity
```bash
cd apps/executive-cli
rm -f .data/execas.sqlite && uv run execas init
```
All migrations must apply cleanly on a fresh database.

### Linting (when applicable)
No broken imports, no syntax errors. The test suite implicitly validates this.

---

## 5. Security Policy

### Secrets management
- Secrets (API keys, tokens, passwords) are stored **only** via environment variables or local files listed in `.gitignore`.
- **Never** commit credentials, tokens, or passwords to the repository.
- The `.gitignore` must include: `.env`, `*.pem`, `*.key`, `credentials.*`.

### Least privilege for MCP
- MCP connectors request only the minimum scopes needed.
- Calendar connector: read-only event access.
- Mail connector: read-only inbox access (no send, no delete).
- All connector permissions documented in their integration plan.

### Database
- SQLite file lives in `apps/executive-cli/.data/` (gitignored).
- No sensitive user data stored without explicit user consent.

---

## 6. Change Management

### Atomic commits
- One commit = one logical change.
- Commit message describes **what** and **why**.
- Each commit must pass all quality gates independently.

### Acceptance checks
- Every commit that changes behavior must include verification commands in the commit description or PR body.
- Schema changes must include: fresh `execas init` + `.tables` verification.
- CLI changes must include: example command + expected output.

### Diff discipline
- Prefer diffs under 300 LOC.
- Large changes must be split into sequential commits.
- No silent spec divergence: if implementation deviates from spec, update spec in the same commit.

---

## 7. Agent Runtime & Verification

Architecture is vendor-neutral — same rules apply regardless of which LLM runtime executes an agent.

- **Core policy layer** (this file + ADRs + skills + quality gates): `spec/AGENT_RUNTIME.md`
- **Runtime adapters** (per-LLM discovery/injection details): `spec/AGENT_RUNTIME_ADAPTERS.md`

### Two-layer model
1. **Core policy layer** — roles, authority, ADRs, quality gates, security. Identical for all runtimes.
2. **Runtime adapter layer** — how each LLM (Codex, Claude, other) discovers and loads the core policy. See `spec/AGENT_RUNTIME_ADAPTERS.md`.

### Instruction sources (priority order)
1. `AGENTS.md` (this file) — operating model, authority, security
2. `agents/<role>/SKILL.md` — per-role profile and checklists
3. `spec/TECH_SPEC.md`, `spec/ARCH_DECISIONS.md`, `spec/ACCEPTANCE.md` — requirements and ADRs
4. `spec/TASKS/TASK_*.md` — scoped task instructions
5. `spec/integrations/*.md` — integration plans
6. User conversation — ad-hoc (must not contradict sources 1–3 without explicit override)

### Verification gate (runtime-agnostic)
Every task deliverable — architecture **and** development — must include a structured gate report with 7 sections: role confirmation, decisions, artifacts, traceability, implementation handoff, risks, ADR status. This gate is **mandatory for all runtimes** — see `spec/AGENT_RUNTIME.md` section 4.

### Runtime preflight (mandatory before implementation)
Before starting any implementation task, the agent must pass the runtime preflight smoke-check defined in `spec/AGENT_RUNTIME_ADAPTERS.md`. A task session without successful preflight is considered "not ready to execute". See `spec/AGENT_RUNTIME.md` section 5.

### Runtime-neutral acceptance
Task acceptance is judged by the core policy layer (quality gates, ADR compliance, authority boundaries), never by which LLM produced the deliverable.

### Trust boundary
Agents can read/write within their authority scope and run quality gates. Agents must get human approval for: pushing to remote, modifying AGENTS.md, amending ADRs, accessing external services with real credentials, or any destructive operation.

---

## 8. Release / MVP Checklist

End-to-end scenario that must work before any release:

```bash
cd apps/executive-cli
rm -f .data/execas.sqlite

# Bootstrap
uv run execas init

# Reference data
uv run execas area add "Work"
uv run execas project add "Agentura" --area "Work"
uv run execas commitment import

# Tasks
uv run execas task capture "Design API" --estimate 60 --priority P1 --project "Agentura" --status NOW
uv run execas task capture "Write docs" --estimate 30 --priority P2 --status NEXT

# Busy blocks
uv run execas busy add --date 2026-02-20 --start 10:00 --end 11:00 --title "Standup"
uv run execas busy list --date 2026-02-20

# Planning
uv run execas plan day --date 2026-02-20 --variant realistic

# People & Decisions
uv run execas people add "Alice" --role "Engineer"
uv run execas people search "Alice"
uv run execas decision add "Use SQLite" --body "Good for MVP"
uv run execas decision search "SQLite"

# Weekly review
uv run execas review week --week 2026-W08

# Tests
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
```
