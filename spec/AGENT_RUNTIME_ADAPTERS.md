# Agent Runtime Adapters

**Date:** 2026-02-15
**Author:** Chief Architect
**Parent document:** `spec/AGENT_RUNTIME.md` (two-layer model, section 1)

---

## Purpose

This document describes how each supported LLM runtime discovers and loads the Agentura core policy layer. The core policy (roles, ADRs, quality gates, verification gate) is identical across runtimes — only the **mechanism** for delivering instructions to the LLM differs.

---

## Adapter Table

| Aspect | Codex (OpenAI) | Claude (Anthropic) | Generic Runtime (manual context injection) |
|--------|---------------|-------------------|-----------------|
| **Instruction injection** | `AGENTS.md` at repo root is auto-loaded as system context; task prompt includes role + file refs | `CLAUDE.md` at repo root for project instructions; conversation system prompt for role assignment | User pastes relevant AGENTS.md sections + SKILL.md into system prompt manually |
| **Skill discovery paths** | Reads `agents/<role>/SKILL.md` via file access tools; reads repo skills from `.agents/skills/*/SKILL.md`; scans `spec/TASKS/` for task files | Reads `agents/<role>/SKILL.md` via Read tool; reads repo skills from `.agents/skills/*/SKILL.md`; scans `spec/TASKS/` via Glob tool | User provides file contents in prompt or attaches files |
| **Quality gate execution** | Runs `uv run pytest` via sandbox shell; checks exit code | Runs `uv run pytest` via Bash tool; checks output | User runs gates manually and reports results |
| **Git operations** | Sandbox shell with git access; commits within sandbox | Bash tool with git access; commits with Co-Authored-By trailer | User commits manually after review |
| **File editing** | Applies patches/edits via code editing tools | Uses Edit/Write tools for file modifications | User applies changes manually |
| **Verification gate report** | Agent outputs structured 7-section report in conversation | Agent outputs structured 7-section report in conversation | User verifies report structure manually |
| **Role enforcement** | Task prompt specifies role; agent reads AGENTS.md to self-constrain | System prompt or user message specifies role; agent reads AGENTS.md to self-constrain | User enforces role boundaries manually |

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

- R2 (skill discovery) is mandatory for all runtime adapters.
- For implementation tasks, runtime preflight must verify the assigned role skill file exists at the mapped path above and is readable.
- If skill discovery fails, status is `not ready to execute`.
- For implementation tasks, AGENTS.md-only continuation is prohibited.

---

## Runtime Baseline Command Matrix

This matrix defines permission baseline expectations per runtime. Commands listed as baseline-safe are expected to run without new approvals once the runtime policy is configured.

| Runtime | Baseline-safe command groups | Notes |
|--------|------------------------------|-------|
| Codex | `git status`, `git diff`, `git diff --name-only`, `rg`, `ls`, `cat`, `sed -n`, `git add <paths>`, `git commit -m`, `git push` (Technical Lead only, guardrailed), `uv run pytest -q`, `uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80`, `uv run execas <local-only command>`, `rm -f .data/execas.sqlite`, `rm -f apps/executive-cli/.data/execas.sqlite` | Role-scoped by `AGENTS.md` section 7. `EA` gets implementation/migration commands; `QA/SET` can run quality-gate flows; `DevOps/SRE` can update CI/runbooks; Technical Lead gets orchestration/acceptance/push within approved plan scope. `rm -f ...execas.sqlite` is migration-integrity-only carve-out. |
| Claude | Same baseline-safe set as Codex via Bash tool | Role-scoped by `AGENTS.md` section 7 and `CLAUDE.md` runtime rules; Technical Lead push is allowed only under guardrails; `QA/SET` and `DevOps/SRE` follow their scoped command limits; same migration-integrity-only carve-out for `execas.sqlite`. |
| Generic runtime | Read-only inspection commands only unless user runs commands manually | No auto-allow assumptions; user remains execution owner |

### Recommended Always-Allow Prefixes (safe baseline)

Apply these only for commands that are baseline-safe and role-scoped:

| Runtime | Recommended prefix set |
|--------|------------------------|
| Codex | `["git", "add"]`, `["git", "commit"]`, `["uv", "run", "pytest"]`, `["git", "push"]` (Technical Lead only) |
| Claude | Equivalent allowlist in local shell policy for `git add`, `git commit`, `uv run pytest`, and `git push` for Technical Lead only |
| Generic runtime | Not applicable (manual execution model) |

For `uv run execas`, prefer narrow per-command allowlists for local-only subcommands and do not globally auto-allow connector/sync commands.

### Escalation Boundaries (never auto-allow)

These commands/actions must always stay manual-approval only, regardless of runtime:
- `git push` for roles other than Technical Lead, and any `git push --force*`
- Destructive operations (`rm -rf`, `git reset --hard`, branch delete, file delete)
- Accessing external services with real credentials

### Gated Destructive Exceptions (quality gates)

The following delete commands are carve-outs and may be allowed only for migration integrity checks:
- `rm -f .data/execas.sqlite`
- `rm -f apps/executive-cli/.data/execas.sqlite`

Constraints:
- Allowed only when used for the migration-integrity flow with `uv run execas init`.
- Must not be generalized into broad delete prefixes (`rm`, `rm -f`, `rm -rf`).

---

## Adapter Details

### Codex (OpenAI)

**Instruction injection points:**
- `AGENTS.md` at repo root — auto-discovered by Codex as project-level instructions
- Task prompt — user includes role assignment: "You are the Chief Architect. Read `agents/chief_architect/SKILL.md` and execute TASK_R1."
- Codex sandbox has file access to the full repo tree

**Skill discovery:**
- Agent resolves role to mapped path in this document and reads that `agents/<role>/SKILL.md` file
- Agent discovers repo skills in `.agents/skills/*/SKILL.md` and applies explicit/implicit triggers as needed
- Agent reads `spec/TASKS/TASK_*.md` for task specifications
- Agent reads `spec/ARCH_DECISIONS.md` for ADR context
- No special path configuration needed — standard repo paths apply

**Limitations and risks:**
- Sandbox may have restricted network access (no external CalDAV/IMAP in tests)
- Context window limits may require chunked reading of large spec files
- No persistent state between Codex sessions — each task starts fresh

**Verifying the agent operated in role:**
- Check that the gate report (section 4 of AGENT_RUNTIME.md) has all 7 sections
- Verify file/line references against actual repo state
- Confirm AGENTS.md authority line cited in role confirmation matches the claimed role
- Check commit messages include role context (e.g., "Chief Architect" or task ID)

**Preflight smoke-check (minimal, run before implementation tasks):**

| Check | Command / action | Pass condition |
|-------|-----------------|----------------|
| Instruction injection | Agent reads `AGENTS.md` and states the number of sections | Correct count (currently 8 sections) |
| Skill discovery | Agent reads the assigned role skill file at its mapped path and states the role's mission | Skill file exists and mission text matches file content |
| Repo skill catalog discovery | Agent lists `.agents/skills/*/SKILL.md` and identifies relevant skill(s) for task | Relevant skill inventory is visible and selection is justified |
| Task discovery | Agent lists files matching `spec/TASKS/TASK_*.md` | Lists at least TASK_R1 and TASK_R2_R4 |
| Permissions readiness | Agent runs baseline-safe commands for assigned role without new approvals | All baseline-safe checks pass; always-manual commands remain approval-gated |

### Claude (Anthropic — Claude Code)

**Instruction injection points:**
- `CLAUDE.md` at repo root — auto-loaded by Claude Code as project instructions (if present)
- Conversation system prompt — role assignment via user message or continued session context
- Agent has direct access to repo via Read, Glob, Grep, Edit, Write, Bash tools

**Skill discovery:**
- Agent resolves role to mapped path in this document and reads that `agents/<role>/SKILL.md` via Read tool
- Agent discovers repo skills via `.agents/skills/*/SKILL.md` and applies explicit/implicit triggers as needed
- Agent discovers task files via `Glob("spec/TASKS/TASK_*.md")`
- Agent searches code via Grep tool for cross-referencing
- Agent can spawn sub-agents (Task tool) for parallel exploration

**Limitations and risks:**
- Context window compression may lose earlier conversation details (mitigated by session summaries)
- Claude Code sandbox restricts certain destructive operations by default
- SSH/push access depends on user's local environment configuration

**Verifying the agent operated in role:**
- Same 7-section gate report as any other runtime
- Co-Authored-By trailer in commits identifies the model
- Conversation transcript preserves the full chain of reads → analysis → edits → commit

**Preflight smoke-check (minimal, run before implementation tasks):**

| Check | Command / action | Pass condition |
|-------|-----------------|----------------|
| Instruction injection | Read `CLAUDE.md` and `AGENTS.md`; state the number of AGENTS.md sections | `CLAUDE.md` exists and is loaded; correct section count (currently 8) |
| Skill discovery | `Read("<mapped role skill path>")`; state role's mission | Skill file exists and mission text matches file content |
| Repo skill catalog discovery | `Glob(".agents/skills/*/SKILL.md")` and select relevant skill(s) | Relevant skill inventory is visible and selection is justified |
| Task discovery | `Glob("spec/TASKS/TASK_*.md")` | Lists at least TASK_R1 and TASK_R2_R4 |
| Permissions readiness | Run baseline-safe commands for assigned role in Bash tool | No new approvals for baseline-safe commands; always-manual commands still gated |

### Generic Runtime (other LLMs)

**Instruction injection points:**
- User manually pastes relevant sections of AGENTS.md into the system prompt
- User provides SKILL.md content for the assigned role using the mapped role path in this document
- User provides task file content or file paths with instructions to read them

**Skill discovery:**
- User provides assigned role SKILL.md content or directs the LLM to the mapped skill path
- If the LLM has file access (e.g., via tool use), standard repo paths apply
- If no file access, user must include all relevant context in the prompt, including assigned role SKILL.md

**Limitations and risks:**
- No guaranteed file access — user may need to copy-paste file contents
- No guaranteed ability to run quality gates — user must run and report results
- Higher risk of context loss if LLM lacks tool access or persistent sessions
- Role enforcement depends entirely on prompt engineering and user vigilance
- For implementation tasks, AGENTS.md-only prompts are insufficient and fail preflight (R2).

**Verifying the agent operated in role:**
- Same 7-section gate report — user must verify all sections manually
- File/line references must be spot-checked by user against actual repo
- Higher scrutiny needed since the LLM may not have directly read the files it references

---

## Adding a New Runtime Adapter

To add support for a new LLM runtime:

1. Add a column to the adapter table above with the runtime name.
2. Document the instruction injection points (how does this runtime receive AGENTS.md?).
3. Document the skill discovery mechanism (how does it find SKILL.md files?).
4. Document limitations and risks specific to this runtime.
5. Confirm that the verification gate (7-section report) can be produced by this runtime.
6. No code changes required — adapter documentation is purely convention-based.

---

## Cross-Runtime Consistency Checks

When the same task is executed by different runtimes (e.g., architecture review by Codex, then implementation by Claude), the following must hold:

1. **Same quality gates:** Both runtimes run `uv run pytest --cov-fail-under=80` and both must pass.
2. **Same authority boundaries:** Neither runtime can exceed the scope defined in AGENTS.md section 2.
3. **Same verification gate:** Both produce 7-section reports with verifiable references.
4. **Same ADR compliance:** Both reference the same ADR numbers and follow the same decisions.
5. **Compatible artifacts:** Files created by one runtime must be readable and editable by another (no runtime-specific formats).

**Anti-pattern:** Accepting a deliverable from Runtime A with lower scrutiny than Runtime B. The core policy layer does not distinguish between runtimes — only the output quality matters.

---

## Adapter Readiness Criteria

A runtime adapter is considered **ready** (pass) when all of the following hold:

| # | Criterion | How to verify |
|---|-----------|---------------|
| R1 | Agent can read `AGENTS.md` and correctly identify its sections | Preflight check: instruction injection |
| R2 | Agent can locate and read the assigned role's `SKILL.md` at mapped path | Preflight check: skill discovery (mandatory) |
| R3 | Agent can discover task files in `spec/TASKS/` | Preflight check: task discovery |
| R4 | Agent passes permissions readiness for baseline-safe commands | Preflight check: permissions readiness |
| R5 | Agent respects authority boundaries from AGENTS.md section 2 | Verified in gate report: role confirmation section |
| R6 | Agent can produce a 7-section gate report | Verified in final deliverable |
| R7 | Agent does not store credentials in repo or database | Verified by diff review |
| R8 | Quality gates pass before commit/merge (`pytest`, coverage, migration integrity when applicable) | Verified in implementation handoff / CI output |

**Fail = not ready to execute.** If any criterion fails, the runtime adapter is not considered operational for implementation tasks. The agent must resolve the failure before proceeding, or the user must switch to a runtime that passes.
- Missing/unreadable role SKILL file (R2) is a hard fail.
- Implementation-task fallback to AGENTS.md-only context is a hard fail.

**Preflight is mandatory.** Every implementation task session must begin with the runtime's minimal preflight smoke-check (instruction injection, skill discovery R2, task discovery, permissions readiness). Architecture-only tasks may skip task discovery when no `spec/TASKS/` file is involved.
