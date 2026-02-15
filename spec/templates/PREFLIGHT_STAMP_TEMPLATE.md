# PREFLIGHT STAMP (Minimal)

Use this at the start of each session before implementation tasks.

```text
PREFLIGHT STAMP
Runtime: <Codex|Claude|Other>
Role: <Chief Architect|Technical Lead|Executive Assistant|Developer Helper|Business Coach>
Timestamp: <YYYY-MM-DD HH:MM TZ>

1) Instruction injection: <PASS|FAIL>
- AGENTS.md loaded (top-level sections: <N>)

2) Skill discovery (R2): <PASS|FAIL>
- Read mapped role file: agents/<role>/SKILL.md

3) Task discovery: <PASS|SKIP|FAIL>
- Found relevant task file(s): spec/TASKS/TASK_*.md

4) Permissions readiness: <PASS|FAIL>
- Baseline-safe commands run without new approvals
- Always-manual actions remain approval-gated

Hard-fail policy:
- Missing/unreadable role SKILL file => NOT READY TO EXECUTE
- Implementation AGENTS.md-only fallback => NOT READY TO EXECUTE

Preflight status: <READY TO EXECUTE|NOT READY TO EXECUTE>
```
