# TL Dispatch Batch 2026-02-15

**Task:** `TL-BOOTSTRAP-01`  
**Owner:** Technical Lead  
**Baseline source:** `spec/operations/tl_plan_48h.md`

## Plan baseline

Scope locked to:
- `OPS-02` (EA): hourly sync observability.
- `OPS-03` (EA): scheduler safety.
- `GOV-02` (Chief Architect): policy consistency check.

No schema, ADR, integration-approach, or time-model override is authorized in this batch.

## Dispatch briefs

### OPS-02 (Executive Assistant)

Goal:
- Add machine-readable output for `execas sync hourly` with `--json`.
- Persist latest sync status to `apps/executive-cli/.data/hourly_sync_status.json`.

Files in scope:
- `apps/executive-cli/executive_cli/cli.py`
- `apps/executive-cli/executive_cli/app/*` (only if needed for sync orchestration)
- `apps/executive-cli/tests/*` (sync and CLI behavior coverage)
- `spec/operations/hourly_sync.md` (if behavior changes need docs update)

Verification commands:
```bash
cd apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

Acceptance criteria:
- Minimal preflight stamp present.
- 7-section gate report present.
- Quality gates passed with explicit evidence.
- No schema/migration/ADR/time-model changes.
- No secrets in code, logs, or fixtures.

### OPS-03 (Executive Assistant)

Goal:
- Add scheduler wrapper with lock file to prevent overlapping runs.
- Document lock behavior and recovery flow.

Files in scope:
- `scripts/*` (scheduler wrapper)
- `spec/operations/hourly_sync.md`
- `apps/executive-cli/tests/*` (if runtime behavior is covered by tests)

Verification commands:
```bash
cd apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

Acceptance criteria:
- Minimal preflight stamp present.
- 7-section gate report present.
- Quality gates passed with explicit evidence.
- Lock behavior documented with failure recovery steps.
- No secrets in script/config changes.

### GOV-02 (Chief Architect)

Goal:
- Verify consistency of Technical Lead authority language across runtime policy docs.
- Confirm no conflict with Chief Architect approval boundaries.

Files in scope:
- `AGENTS.md`
- `spec/AGENT_RUNTIME.md`
- `spec/AGENT_RUNTIME_ADAPTERS.md`

Verification commands:
```bash
rg -n "Technical Lead|Push|authority|approve|schema|ADR|time model|integration" AGENTS.md spec/AGENT_RUNTIME.md spec/AGENT_RUNTIME_ADAPTERS.md
```

Acceptance criteria:
- 7-section architecture gate report present.
- Findings map to exact file paths/lines.
- Any boundary change proposal is explicitly deferred pending approval if required.

## Commit acceptance queue

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| pending | OPS-02 | Executive Assistant | pending | waiting for commit + gate report |
| pending | OPS-03 | Executive Assistant | pending | waiting for commit + gate report |
| pending | GOV-02 | Chief Architect | pending | waiting for commit + gate report |

## Acceptance review snapshot (2026-02-15)

| Commit | Task | Role | Verdict | Evidence |
|---|---|---|---|---|
| `77276cb` | N/A (preflight docs) | Technical Lead | rejected (out of current baseline) | `git show --name-only -n 1 77276cb` touched runtime/preflight docs only |
| `445aed5` | N/A (preflight docs) | Technical Lead | rejected (out of current baseline) | `git show --name-only -n 1 445aed5` touched runtime/skill-discovery docs |
| `20eb915` | OPS-01 | Executive Assistant | rejected (not in 48h scope) | commit subject + files show OPS-01, while baseline is OPS-02/OPS-03/GOV-02 |

No incoming commits for `OPS-02`, `OPS-03`, or `GOV-02` are available for acceptance yet.

## Push gate state

- Target branch: `main` (remote `origin/main`)
- Current state: `blocked`
- Blockers:
  - no accepted commits in this batch yet
  - acceptance ledger contains only pending entries
