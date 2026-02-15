# Agent Runtime Architecture

**Date:** 2026-02-15
**Author:** Chief Architect
**Scope:** Process architecture for LLM-based agents operating on the Agentura codebase. No runtime code — this document defines conventions, verification protocols, and trust boundaries.

---

## 1. Instruction Sources (priority order)

Agents operating on the Agentura codebase receive instructions from these sources, in decreasing priority:

| Priority | Source | Location | Purpose |
|----------|--------|----------|---------|
| 1 | **AGENTS.md** (root) | `/AGENTS.md` | Operating model: roles, authority boundaries, quality gates, security policy |
| 2 | **Agent skill files** | `agents/<role>/SKILL.md` | Per-role profile: mission, decision rules, checklists, templates |
| 3 | **Spec documents** | `spec/TECH_SPEC.md`, `spec/ARCH_DECISIONS.md`, `spec/ACCEPTANCE.md` | Source of truth for requirements, ADRs, acceptance criteria |
| 4 | **Task files** | `spec/TASKS/TASK_*.md` | Scoped implementation instructions with acceptance checks |
| 5 | **Integration plans** | `spec/integrations/*.md` | Per-service data flow, security constraints, failure modes |
| 6 | **User instructions** | Conversation context | Ad-hoc directives (must not contradict sources 1–3 without explicit override) |

**Conflict resolution:** Higher-priority source wins. If a user instruction contradicts AGENTS.md or an ADR, the agent must flag the conflict and request explicit override authorization before proceeding.

---

## 2. Canonical Skill Paths

Agent skill definitions are stored in the repository under a predictable path structure:

```
/Users/gaidabura/Agentura/
├── AGENTS.md                          # Global operating model
├── agents/
│   ├── chief_architect/
│   │   └── SKILL.md                   # Chief Architect profile + checklists
│   └── developer_helper/
│       └── SKILL.md                   # Developer Helper profile (future)
└── spec/
    └── templates/
        ├── ADR_TEMPLATE.md            # Architecture Decision Record template
        ├── INTEGRATION_TEMPLATE.md    # Integration design template
        └── THREAT_MODEL_TEMPLATE.md   # Threat model template
```

### Path conventions

- **Agent profiles:** `agents/<role_snake_case>/SKILL.md`
- **Shared templates:** `spec/templates/<NAME>_TEMPLATE.md`
- **Task specifications:** `spec/TASKS/TASK_<ID>_<NAME>.md`
- **Integration plans:** `spec/integrations/<service_name>.md`

### Adding a new agent role

1. Create `agents/<role>/SKILL.md` following the structure in `agents/chief_architect/SKILL.md`.
2. Add the role to `AGENTS.md` section 1 (Agent Roles).
3. Add authority boundaries to `AGENTS.md` section 2 (Authority & Boundaries table).
4. No code changes required — agent runtime is convention-based, not framework-based.

---

## 3. Role Verification Protocol

When an agent claims to operate in an architectural role (Chief Architect, EA, etc.), its output must include verifiable markers that demonstrate it actually followed the role's constraints. A generic LLM response lacks these markers.

### Required sections in an Architecture Gate Report

Every architecture-level deliverable must include:

| Section | Content | Verification |
|---------|---------|--------------|
| **Role confirmation** | State which role is being exercised and cite the authority line in AGENTS.md | Reviewer checks AGENTS.md line reference exists |
| **Decisions** | List of decisions made, each referencing an ADR (existing or new) | Reviewer checks ADR numbers and content match |
| **Artifacts** | List of files created/modified with one-line summary each | Reviewer checks files exist and match description |
| **Traceability** | Cross-references to spec files with line numbers | Reviewer spot-checks 2–3 references for accuracy |
| **Implementation handoff** | What the next agent can do, what requires further approval | Reviewer checks scope boundaries match AGENTS.md authority table |
| **Risks / open questions** | Known risks with mitigation or acceptance rationale | Reviewer checks risks are realistic, not fabricated |
| **ADR status** | Explicit statement: "ADR-NN remains unchanged" or "ADR-NN amended: <what changed>" | Reviewer diffs ARCH_DECISIONS.md |

### Distinguishing authorized architect from generic LLM

| Marker | Authorized architect | Generic LLM |
|--------|---------------------|-------------|
| Cites specific file paths and line numbers | Yes — references are verifiable against repo | Often fabricates or gives vague references |
| References existing ADR numbers correctly | Yes — ADR numbers match ARCH_DECISIONS.md | May invent non-existent ADRs |
| Respects authority boundaries | States what it can/cannot do per AGENTS.md | Does not self-limit; may overstep scope |
| Produces structured gate report | Follows the 7-section template above | Produces unstructured prose |
| States ADR status explicitly | "ADR-10 remains unchanged" or "ADR-10 amended" | Omits or is vague about changes |
| Cross-checks existing code state | References actual function names, model fields, migration IDs | May reference non-existent code |

### Verification checklist (for human reviewer)

- [ ] Report has all 7 required sections
- [ ] Role confirmation cites correct AGENTS.md line
- [ ] At least 3 file/line references are spot-checked and accurate
- [ ] ADR status is explicit and matches ARCH_DECISIONS.md diff
- [ ] No authority boundary violations (check against AGENTS.md section 2)
- [ ] Artifacts listed in report actually exist in the repo

---

## 4. Trust Boundaries for Agent Operations

```
[User] <-- conversation --> [LLM Agent]
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
- Run tests (`uv run pytest`)
- Run linters and type checkers
- Create/modify files within their authority scope (AGENTS.md section 2)
- Create git commits (with descriptive messages)

### What agents MUST get human approval for
- Push to remote repository
- Modify AGENTS.md (operating model changes)
- Amend existing ADRs (architectural decisions)
- Delete files or branches
- Access external services (CalDAV, IMAP) with real credentials
- Any destructive or hard-to-reverse operation

### What agents MUST NOT do
- Store credentials in code, config, or database
- Bypass quality gates (--no-verify, --cov-fail-under=0)
- Claim a role they haven't been assigned
- Execute changes outside their authority scope without escalation

---

## 5. Operational Invariants

These invariants hold regardless of which agent is operating:

1. **Single writer for SQLite:** Only EA writes to the database (ADR-09). Other agents produce proposals.
2. **ADR before schema change:** No migration without an approved ADR (AGENTS.md section 3).
3. **Quality gates are mandatory:** Every commit must pass `uv run pytest` and coverage gate (AGENTS.md section 4).
4. **Secrets never in repo:** Credentials in env vars only (AGENTS.md section 5).
5. **Atomic commits:** One commit = one logical change (AGENTS.md section 6).
6. **Explicit ADR status:** Every architecture deliverable states ADR status (this document, section 3).
