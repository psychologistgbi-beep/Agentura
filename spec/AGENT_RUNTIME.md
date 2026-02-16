# Agent Runtime Architecture

**Date:** 2026-02-15 (updated 2026-02-15)
**Author:** Chief Architect
**Scope:** Process architecture for LLM-based agents operating on the Agentura codebase. Vendor-neutral — same policy layer applies regardless of which LLM runtime (Codex, Claude, or other) executes the agent.

---

## 1. Two-Layer Model

Agent operations in Agentura are split into two distinct layers:

```
┌─────────────────────────────────────────────────────┐
│              Core Policy Layer                       │
│  (vendor-neutral, same rules for every LLM)         │
│                                                      │
│  AGENTS.md  ─  ADRs  ─  SKILL.md  ─  TASKS  ─  QG  │
└──────────────────────┬──────────────────────────────┘
                       │ reads policy, emits artifacts
┌──────────────────────┴──────────────────────────────┐
│            Runtime Adapter Layer                     │
│  (per-LLM: skill discovery, instruction injection)  │
│                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────────────┐     │
│  │  Codex  │  │ Claude  │  │ Generic runtime │     │
│  └─────────┘  └─────────┘  └─────────────────┘     │
└─────────────────────────────────────────────────────┘
```

### Core policy layer (runtime-agnostic)

Everything in this layer is the same regardless of which LLM executes the agent:

| Component | Location | Governs |
|-----------|----------|---------|
| Operating model | `AGENTS.md` | Agent roles, authority boundaries, security policy |
| Architecture decisions | `spec/ARCH_DECISIONS.md` | Schema, time model, integration approach |
| Agent skill profiles | `agents/<role>/SKILL.md` | Per-role mission, decision rules, checklists |
| Repository skill catalog | `.agents/skills/*/SKILL.md` | Task-scoped reusable workflows (explicit/implicit invocation) |
| Task specifications | `spec/TASKS/TASK_*.md` | Scoped implementation instructions |
| Acceptance criteria | `spec/ACCEPTANCE.md` | Definition of done |
| Quality gates | `AGENTS.md` section 4 | Tests, coverage, migration integrity |
| Security policy | `AGENTS.md` section 5 | Secrets, least privilege, PII |

**Key principle:** Acceptance of a task deliverable is judged by the core policy layer, never by which runtime produced it. A commit from Codex and a commit from Claude are held to the same quality gates, the same verification protocol, the same authority boundaries.

### Runtime adapter layer (per-LLM)

Each LLM runtime has different mechanisms for discovering instructions and injecting context. The adapter layer describes how each runtime maps to the core policy layer. See `spec/AGENT_RUNTIME_ADAPTERS.md` for the full adapter table.

---

## 2. Instruction Sources (priority order)

Agents receive instructions from these sources, in decreasing priority:

| Priority | Source | Location | Purpose |
|----------|--------|----------|---------|
| 1 | **AGENTS.md** (root) | `/AGENTS.md` | Operating model: roles, authority, quality gates, security |
| 2 | **Agent skill files** | `agents/<role>/SKILL.md` | Per-role profile: mission, decision rules, checklists |
| 3 | **Spec documents** | `spec/TECH_SPEC.md`, `spec/ARCH_DECISIONS.md`, `spec/ACCEPTANCE.md` | Requirements, ADRs, acceptance criteria |
| 4 | **Task files** | `spec/TASKS/TASK_*.md` | Scoped implementation instructions with acceptance checks |
| 5 | **Framework baselines** | `spec/frameworks/*.md` | Role-specific planning frameworks (for example FPF for System Analyst) |
| 6 | **Integration plans** | `spec/integrations/*.md` | Per-service data flow, security constraints, failure modes |
| 7 | **User instructions** | Conversation context | Ad-hoc directives (must not contradict sources 1–3 without explicit override) |

**Conflict resolution:** Higher-priority source wins. If a user instruction contradicts AGENTS.md or an ADR, the agent must flag the conflict and request explicit override authorization before proceeding. This rule applies to all runtimes equally.

---

## 3. Canonical Skill Paths

Agent skill definitions are stored in the repository under a predictable path structure:

```
<repo_root>/
├── AGENTS.md                          # Global operating model (core policy)
├── agents/
│   ├── chief_architect/
│   │   └── SKILL.md                   # Chief Architect profile + checklists
│   ├── technical_lead/
│   │   └── SKILL.md                   # Technical Lead orchestration profile
│   ├── executive_assistant/
│   │   └── SKILL.md                   # Executive Assistant profile
│   ├── developer_helper/
│   │   └── SKILL.md                   # Developer Helper profile
│   ├── business_coach/
│   │   └── SKILL.md                   # Business Coach profile
│   ├── system_analyst/
│   │   └── SKILL.md                   # System Analyst profile
│   ├── product_owner/
│   │   └── SKILL.md                   # Product Owner profile
│   ├── scrum_master/
│   │   └── SKILL.md                   # Scrum Master profile
│   ├── qa_set/
│   │   └── SKILL.md                   # QA/SET profile
│   └── devops_sre/
│       └── SKILL.md                   # DevOps/SRE profile
├── .agents/
│   └── skills/
│       └── <skill_name>/
│           ├── SKILL.md               # Codex skill (name/description + workflow)
│           └── agents/openai.yaml     # Optional metadata (implicit policy, UI hints)
└── spec/
    ├── AGENT_RUNTIME.md               # This file (core policy + layer model)
    ├── AGENT_RUNTIME_ADAPTERS.md      # Per-runtime adapter details
    ├── frameworks/
    │   └── FPF_REFERENCE.md           # System Analyst planning framework baseline
    └── templates/
        ├── ADR_TEMPLATE.md
        ├── INTEGRATION_TEMPLATE.md
        └── THREAT_MODEL_TEMPLATE.md
```

### Path conventions

- **Agent profiles:** `agents/<role_snake_case>/SKILL.md`
- **Codex skill catalog:** `.agents/skills/<skill_name>/SKILL.md`
- **Shared templates:** `spec/templates/<NAME>_TEMPLATE.md`
- **Task specifications:** `spec/TASKS/TASK_<ID>_<NAME>.md`
- **Integration plans:** `spec/integrations/<service_name>.md`

These paths are part of the core policy layer. Each runtime adapter describes how it discovers and loads these files (see `spec/AGENT_RUNTIME_ADAPTERS.md`).

### Role-to-skill mapping (mandatory)

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

### Strict skill discovery policy

- R2 (skill discovery) is mandatory for all task sessions.
- For implementation tasks, the runtime must resolve the assigned role to the exact file path in the mapping table above and read it successfully.
- If the mapped `agents/<role>/SKILL.md` file is missing or unreadable, preflight fails with status `not ready to execute`.
- For implementation tasks, fallback behavior of "continue from AGENTS.md only" is prohibited.

### Adding a new agent role

1. Create `agents/<role>/SKILL.md` following the structure in `agents/chief_architect/SKILL.md`.
2. Add the role to `AGENTS.md` section 1 (Agent Roles).
3. Add authority boundaries to `AGENTS.md` section 2 (Authority & Boundaries table).
4. No code changes required — agent runtime is convention-based, not framework-based.
5. Verify the new role path is added to the role-to-skill mapping table in this file and in `spec/AGENT_RUNTIME_ADAPTERS.md`.
6. Verify preflight R2 passes in each supported runtime adapter.

---

## 4. Agent Verification Gate (runtime-agnostic)

When an agent operates in any role (Chief Architect, Technical Lead, EA, Developer Helper, System Analyst, Product Owner, Scrum Master, QA/SET, DevOps/SRE, etc.) on an architecture or development task, its output must include verifiable markers that demonstrate it actually followed the role's constraints. This verification gate is **mandatory for all runtimes and all task types** (architecture and development) — the same 7-section report structure applies whether the agent runs on Codex, Claude, or any other LLM.

### Required sections in a gate report

| Section | Content | Verification |
|---------|---------|--------------|
| **Role confirmation** | State which role is being exercised and cite the authority line in AGENTS.md | Reviewer checks AGENTS.md line reference exists |
| **Decisions** | List of decisions made, each referencing an ADR (existing or new) | Reviewer checks ADR numbers and content match |
| **Artifacts** | List of files created/modified with one-line summary each | Reviewer checks files exist and match description |
| **Traceability** | Cross-references to spec files with line numbers | Reviewer spot-checks 2–3 references for accuracy |
| **Implementation handoff** | What the next agent can do, what requires further approval | Reviewer checks scope boundaries match AGENTS.md authority table |
| **Risks / open questions** | Known risks with mitigation or acceptance rationale | Reviewer checks risks are realistic, not fabricated |
| **ADR status** | Explicit statement: "ADR-NN remains unchanged" or "ADR-NN amended: <what changed>" | Reviewer diffs ARCH_DECISIONS.md |

### Distinguishing an authorized agent from a generic LLM

These markers are runtime-agnostic — they apply to any LLM claiming to act as an Agentura agent:

| Marker | Authorized agent | Generic LLM |
|--------|-----------------|-------------|
| Cites specific file paths and line numbers | Yes — verifiable against repo | Often fabricates or gives vague references |
| References existing ADR numbers correctly | Yes — matches ARCH_DECISIONS.md | May invent non-existent ADRs |
| Respects authority boundaries | States what it can/cannot do per AGENTS.md | Does not self-limit; may overstep scope |
| Produces structured gate report | Follows the 7-section template above | Produces unstructured prose |
| States ADR status explicitly | "ADR-10 remains unchanged" or "ADR-10 amended" | Omits or is vague about changes |
| Cross-checks existing code state | References actual function names, model fields, migration IDs | May reference non-existent code |

### Verification checklist (for human reviewer)

This checklist is applied identically regardless of which runtime produced the deliverable:

- [ ] Report has all 7 required sections
- [ ] Role confirmation cites correct AGENTS.md line
- [ ] At least 3 file/line references are spot-checked and accurate
- [ ] ADR status is explicit and matches ARCH_DECISIONS.md diff
- [ ] No authority boundary violations (check against AGENTS.md section 2)
- [ ] Artifacts listed in report actually exist in the repo
- [ ] Runtime identified (which LLM produced this output)

---

## 5. Runtime Preflight (minimal mandatory before implementation)

Before an agent begins any implementation task (code, migrations, CLI commands), it must pass the runtime preflight smoke-check defined in `spec/AGENT_RUNTIME_ADAPTERS.md` for its specific runtime.
Use the short session-start template: `spec/templates/PREFLIGHT_STAMP_TEMPLATE.md`.

### What preflight verifies
1. **Instruction injection** — the agent has loaded AGENTS.md (and CLAUDE.md for Claude runtime).
2. **Skill discovery (R2)** — the agent can read the assigned role's mapped `agents/<role>/SKILL.md`.
3. **Repo skill catalog discovery** — the agent can discover `.agents/skills/*/SKILL.md` and select relevant skill(s).
4. **Task discovery** — the agent can find task files in `spec/TASKS/`.
5. **Permissions readiness** — safe baseline commands for the assigned role execute without new approval prompts.
6. **Framework readiness (System Analyst planning only)** — `spec/frameworks/FPF_REFERENCE.md` is discoverable and loaded.

Quality gates remain mandatory, but are validated before commit/merge (AGENTS.md section 4), not in session-start preflight.

### Permissions readiness (mandatory block)
Preflight is incomplete until permissions readiness is explicitly evaluated.

**Pass criteria:**
- Safe baseline commands from `AGENTS.md` section 7 run in the current runtime session without new approval prompts.
- Commands in the always-manual list remain approval-gated and are not auto-allowed.

**Fail criteria (status = not ready to execute):**
- Any safe baseline command requires a new approval to run.
- Runtime policy only works via ad-hoc one-off escalations for baseline-safe commands.
- Runtime configuration would auto-allow a command from the always-manual list.
- Assigned role skill file is missing or unreadable at the mapped path.
- For implementation tasks, runtime attempts to continue using AGENTS.md only without loading the assigned role SKILL file.
- For System Analyst planning sessions, FPF baseline file is missing/unreadable (`spec/frameworks/FPF_REFERENCE.md`).

### When preflight is required
- **Implementation tasks** (code, migrations, tests): all 4 checks required.
- **Architecture tasks** (docs, ADRs, process): checks 1, 2, and 4 required; check 3 may be skipped if no `spec/TASKS/` file is involved.
- **Skipping preflight** makes the deliverable `not ready to execute` — the human reviewer should request preflight before accepting.

### Preflight is per-session
Preflight runs once at the start of a task session. If the agent continues in the same session, preflight does not need to repeat. A new session (e.g., context reset, new conversation) requires a new preflight.

---

## 6. Trust Boundaries for Agent Operations

```
[User] <-- conversation --> [LLM Agent (any runtime)]
                                |
                    reads: AGENTS.md, SKILL.md, spec/*
                                |
                    writes: code, migrations, docs
                                |
                                v
                         [Git repository]
                                |
                    quality gates: pytest, coverage, migration integrity
```

### What agents CAN do without human approval
- Read any file in the repository
- Execute safe baseline commands from `AGENTS.md` section 7
- Run linters and type checkers
- Create/modify files within their authority scope (AGENTS.md section 2)
- Create git commits (with descriptive messages and role scope compliance)
- Technical Lead can push accepted commits within a user-approved plan, after quality gates pass

### What agents MUST get human approval for
- Push to remote repository (all roles except Technical Lead under AGENTS.md guardrails)
- Destructive operations (`rm -rf`, `git reset --hard`, branch delete, file delete)
- Access external services (CalDAV, IMAP, APIs) with real credentials
- Modify AGENTS.md (operating model changes)
- Amend existing ADRs (architectural decisions)

### What agents MUST NOT do
- Store credentials in code, config, or database
- Bypass quality gates (--no-verify, --cov-fail-under=0)
- Claim a role they haven't been assigned
- Execute changes outside their authority scope without escalation

---

## 7. Operational Invariants

These invariants hold regardless of which agent or runtime is operating:

1. **Single writer for SQLite:** Only EA writes to the database (ADR-09). Other agents produce proposals.
2. **ADR before schema change:** No migration without an approved ADR (AGENTS.md section 3).
3. **Quality gates are mandatory:** Every commit must pass `uv run pytest` and coverage gate (AGENTS.md section 4).
4. **Secrets never in repo:** Credentials in env vars only (AGENTS.md section 5).
5. **Atomic commits:** One commit = one logical change (AGENTS.md section 6).
6. **Explicit ADR status:** Every architecture deliverable states ADR status (section 4 of this document).
7. **Runtime-neutral acceptance:** Task acceptance is judged by core policy, not by which LLM produced the output.

---

## 8. Glossary

| Term | Definition |
|------|-----------|
| **Agent role** | A named responsibility scope (Chief Architect, Technical Lead, EA, Developer Helper, Business Coach, System Analyst, Product Owner, Scrum Master, QA/SET, DevOps/SRE) defined in AGENTS.md with explicit authority boundaries |
| **Runtime adapter** | Per-LLM configuration that maps core policy files to the LLM's instruction injection mechanism (see AGENT_RUNTIME_ADAPTERS.md) |
| **Skill discovery** | The process by which a runtime locates and loads agent skill files (SKILL.md, templates, task specs) |
| **Verification gate** | The 7-section structured report that proves an agent operated within its assigned role (section 4 of this document) |
| **Handoff contract** | The "Implementation handoff" section of a gate report — defines what the next agent can do and what requires further approval |
| **Core policy layer** | The runtime-agnostic set of rules (AGENTS.md, ADRs, skills, quality gates) that all agents must follow |
| **Runtime preflight** | A per-session smoke-check that verifies the runtime adapter can access instructions, role skills, tasks, and baseline permissions readiness (section 5) |
