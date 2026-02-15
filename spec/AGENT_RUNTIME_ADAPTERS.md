# Agent Runtime Adapters

**Date:** 2026-02-15
**Author:** Chief Architect
**Parent document:** `spec/AGENT_RUNTIME.md` (two-layer model, section 1)

---

## Purpose

This document describes how each supported LLM runtime discovers and loads the Agentura core policy layer. The core policy (roles, ADRs, quality gates, verification gate) is identical across runtimes — only the **mechanism** for delivering instructions to the LLM differs.

---

## Adapter Table

| Aspect | Codex (OpenAI) | Claude (Anthropic) | Generic Fallback |
|--------|---------------|-------------------|-----------------|
| **Instruction injection** | `AGENTS.md` at repo root is auto-loaded as system context; task prompt includes role + file refs | `CLAUDE.md` at repo root for project instructions; conversation system prompt for role assignment | User pastes relevant AGENTS.md sections + SKILL.md into system prompt manually |
| **Skill discovery paths** | Reads `agents/<role>/SKILL.md` via file access tools; scans `spec/TASKS/` for task files | Reads `agents/<role>/SKILL.md` via Read tool; scans `spec/TASKS/` via Glob tool | User provides file contents in prompt or attaches files |
| **Quality gate execution** | Runs `uv run pytest` via sandbox shell; checks exit code | Runs `uv run pytest` via Bash tool; checks output | User runs gates manually and reports results |
| **Git operations** | Sandbox shell with git access; commits within sandbox | Bash tool with git access; commits with Co-Authored-By trailer | User commits manually after review |
| **File editing** | Applies patches/edits via code editing tools | Uses Edit/Write tools for file modifications | User applies changes manually |
| **Verification gate report** | Agent outputs structured 7-section report in conversation | Agent outputs structured 7-section report in conversation | User verifies report structure manually |
| **Role enforcement** | Task prompt specifies role; agent reads AGENTS.md to self-constrain | System prompt or user message specifies role; agent reads AGENTS.md to self-constrain | User enforces role boundaries manually |

---

## Adapter Details

### Codex (OpenAI)

**Instruction injection points:**
- `AGENTS.md` at repo root — auto-discovered by Codex as project-level instructions
- Task prompt — user includes role assignment: "You are the Chief Architect. Read `agents/chief_architect/SKILL.md` and execute TASK_R1."
- Codex sandbox has file access to the full repo tree

**Skill discovery:**
- Agent reads `agents/<role>/SKILL.md` directly via file tools
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

### Claude (Anthropic — Claude Code)

**Instruction injection points:**
- `CLAUDE.md` at repo root — auto-loaded by Claude Code as project instructions (if present)
- Conversation system prompt — role assignment via user message or continued session context
- Agent has direct access to repo via Read, Glob, Grep, Edit, Write, Bash tools

**Skill discovery:**
- Agent reads `agents/<role>/SKILL.md` via Read tool
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

### Generic Fallback (other LLMs)

**Instruction injection points:**
- User manually pastes relevant sections of AGENTS.md into the system prompt
- User provides SKILL.md content for the assigned role
- User provides task file content or file paths with instructions to read them

**Skill discovery:**
- User provides file contents or directs the LLM to specific paths
- If the LLM has file access (e.g., via tool use), standard repo paths apply
- If no file access, user must include all relevant context in the prompt

**Limitations and risks:**
- No guaranteed file access — user may need to copy-paste file contents
- No guaranteed ability to run quality gates — user must run and report results
- Higher risk of context loss if LLM lacks tool access or persistent sessions
- Role enforcement depends entirely on prompt engineering and user vigilance

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
