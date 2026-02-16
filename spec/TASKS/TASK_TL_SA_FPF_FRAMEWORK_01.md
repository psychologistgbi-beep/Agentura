# TASK TL-SA-FPF-01: Adopt FPF-First Planning for System Analyst

**Author:** Technical Lead  
**Date:** 2026-02-16  
**Scope type:** policy/process alignment

## Goal

Adopt FPF as the primary planning framework for the System Analyst role and make it enforceable via role profile, runtime preflight expectations, and explicit task-plan artifacts.

## Baseline and approval

- User-approved baseline: 2026-02-16 (chat approval by user).
- Delivery mode: single batch, multi-role execution with Technical Lead acceptance.

## Agent execution lanes

| Lane | Owner role | Purpose | File scope | Dependency type |
|------|------------|---------|------------|-----------------|
| L1 | System Analyst | Define mandatory FPF planning artifacts and workflow updates | `agents/system_analyst/SKILL.md`, `spec/frameworks/FPF_REFERENCE.md` | primary |
| L2 | Chief Architect | Align runtime policy and preflight expectations for framework readiness | `AGENTS.md`, `spec/AGENT_RUNTIME.md`, `spec/AGENT_RUNTIME_ADAPTERS.md`, `spec/templates/PREFLIGHT_STAMP_TEMPLATE.md` | depends on L1 artifacts |
| L3 | Developer Helper | Maintain executable task specification and traceability package | `spec/TASKS/TASK_TL_SA_FPF_FRAMEWORK_01.md` | parallel-safe |
| L4 | QA/SET | Validate consistency of policy artifacts and run required quality gates | gate evidence only | depends on L1+L2 |
| L5 | Technical Lead | Accept scope, validate evidence, commit, and push | git metadata and acceptance report | depends on L1-L4 |

## In scope

- Establish FPF as default System Analyst planning approach.
- Add repository-local FPF baseline reference for runtime/preflight checks.
- Reflect role-specific framework readiness in policy/runtime documents.
- Provide lane-scoped acceptance checks and verification commands.

## Out of scope

- Product feature implementation in `apps/executive-cli/src/`.
- Schema/migration changes.
- Integration connector behavior changes.

## Verification commands

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

## Acceptance checks

- [ ] `agents/system_analyst/SKILL.md` explicitly states FPF-first workflow and required outputs.
- [ ] `spec/frameworks/FPF_REFERENCE.md` exists and defines required planning artifacts.
- [ ] Runtime docs include System Analyst framework-readiness check for FPF baseline file.
- [ ] Preflight template includes framework-readiness field and hard-fail condition for SA planning sessions.
- [ ] Quality-gate commands succeed.
- [ ] Technical Lead acceptance report includes mandatory 7 sections.

## Rollback notes

If FPF policy wording causes ambiguity or runtime inconsistency:
- revert only FPF-specific policy/task edits;
- keep unrelated runtime/security changes intact;
- re-dispatch with narrowed scope and explicit wording diffs.
