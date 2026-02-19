# TASK S1: Pipeline Engine, Approval Gate & Audit Infrastructure

**Author:** Chief Architect + Technical Lead
**Date:** 2026-02-17
**ADR reference:** ADR-12 (`spec/ARCH_DECISIONS.md`, full spec `spec/ARCH_DECISIONS_ADR12.md`)
**Depends on:** ADR-09 (single writer), ADR-11 (ingestion pipeline), all existing migrations
**Sprint:** 1 of 4 (Reengineering Phase)
**Estimated effort:** 2 weeks

---

## 1. Goal

Build the foundational infrastructure for deterministic pipeline execution:
- **Pipeline Engine** — generic state-machine runner with retry, idempotency, and correlation tracing
- **Approval Gate** — action-agnostic human-in-the-loop blocker with CLI
- **LLM Gateway** — unified proxy for all LLM calls with fallback chain and logging
- **Migration** — 4 new tables per ADR-12
- **Proof of concept** — refactor email ingest pipeline to run on the new engine

---

## 2. Deliverables

### D1: Alembic Migration (4 new tables)

**File:** `alembic/versions/<hash>_add_pipeline_engine_schema.py`

Tables (exact spec in ADR-12):
1. `pipeline_runs` — pipeline execution state
2. `pipeline_events` — per-step audit trail with idempotency keys
3. `approval_requests` — pending/approved/rejected actions
4. `llm_call_log` — LLM call metrics (no raw prompts)

**Models file:** Add 4 new SQLModel classes to `models.py`:
- `PipelineRun`
- `PipelineEvent`
- `ApprovalRequest`
- `LLMCallLog`

**Acceptance criteria:**
- `execas init` applies migration cleanly on fresh DB
- `execas init` applies migration cleanly on existing DB with ADR-11 data
- All FK constraints, indexes, unique constraints match ADR-12 spec
- Migration integrity gate passes: `rm -f .data/execas.sqlite && uv run execas init`

### D2: Pipeline Engine Module

**File:** `src/executive_cli/pipeline_engine.py`

```python
# Core interfaces

@dataclass
class StepDefinition:
    name: str
    handler: Callable[[StepContext], StepResult]
    step_type: str  # "deterministic" | "llm" | "approval" | "fan_out"
    max_retries: int = 0
    backoff_seconds: float = 1.0

@dataclass
class PipelineDefinition:
    name: str
    steps: list[StepDefinition]

@dataclass
class StepContext:
    run_id: int
    correlation_id: str
    step_name: str
    input_data: dict[str, Any]
    session: Session

@dataclass
class StepResult:
    status: str  # "completed" | "failed" | "waiting_approval"
    output_data: dict[str, Any] | None = None
    error: str | None = None
    approval_request: ApprovalRequestInput | None = None

@dataclass
class ApprovalRequestInput:
    action_type: str
    action_payload: dict[str, Any]
    context: dict[str, Any]
```

**Key functions:**

```python
def register_pipeline(definition: PipelineDefinition) -> None:
    """Register a named pipeline. Called at app startup."""

def run_pipeline(
    session: Session,
    *,
    pipeline_name: str,
    input_data: dict[str, Any],
    now_iso: str,
) -> PipelineRunResult:
    """Execute a registered pipeline. Handles retry, idempotency, audit."""

def resume_pipeline(
    session: Session,
    *,
    run_id: int,
    now_iso: str,
) -> PipelineRunResult:
    """Resume a pipeline blocked on approval (after approve/reject)."""

def get_pipeline_status(
    session: Session,
    *,
    run_id: int,
) -> PipelineRunInfo:
    """Return current status of a pipeline run with all step events."""
```

**Idempotency logic (critical):**
1. Compute `idempotency_key = sha256(f"{run_id}:{step_name}:{input_hash}")`.
2. Query `pipeline_events` for existing event with this key.
3. If found with `status=completed` → return cached output, skip execution.
4. If found with `status=failed` and `attempt < max_retries` → increment attempt, re-execute.
5. If not found → create new event, execute handler.

**Retry logic:**
- On step failure: if `attempt < max_retries`, set `status=retrying`, wait `backoff_seconds * 2^attempt`, re-execute.
- On final failure: set step `status=failed`, run `status=failed`, log error.

**Approval integration:**
- When handler returns `StepResult(status="waiting_approval", approval_request=...)`:
  1. Create `ApprovalRequest` row.
  2. Set step `status=waiting_approval`, run `status=waiting_approval`.
  3. Return to caller (pipeline paused).
- On `resume_pipeline()`: check approval status, continue if approved.

**Acceptance criteria:**
- Can register and execute a 3-step pipeline with deterministic handlers
- Idempotency: re-running same pipeline with same input = no-op (no duplicate events)
- Retry: step that fails on attempt 1 succeeds on attempt 2 → pipeline completes
- Approval: step returning `waiting_approval` pauses pipeline; `resume_pipeline` continues after approval
- Correlation ID propagated to all events
- All step durations recorded in `duration_ms`

### D3: Approval Gate Module

**File:** `src/executive_cli/approval_gate.py`

```python
def request_approval(
    session: Session,
    *,
    pipeline_run_id: int | None,
    step_name: str | None,
    action_type: str,
    action_payload: dict[str, Any],
    context: dict[str, Any] | None,
    now_iso: str,
) -> int:  # returns approval_request.id
    """Create a pending approval request."""

def approve(session: Session, *, request_id: int, now_iso: str) -> ApprovalRequest:
    """Approve a request. Raises if not pending."""

def reject(session: Session, *, request_id: int, now_iso: str) -> ApprovalRequest:
    """Reject a request. Raises if not pending."""

def list_pending(session: Session) -> list[ApprovalRequest]:
    """Return all pending approval requests, oldest first."""

def execute_approved(session: Session, *, request_id: int, now_iso: str) -> Any:
    """Execute the action of an approved request. Dispatches by action_type."""
```

**Action type dispatch (Sprint 1 scope):**
- `create_task` → calls `task_service.create_task_record()` with payload fields
- Other action types → raise `NotImplementedError` (Wave 2)

**Acceptance criteria:**
- Can create, approve, reject approval requests
- `list_pending` returns only `status=pending` ordered by `created_at`
- `approve` + `execute_approved` creates a task via `task_service`
- Double-approve raises error (idempotent status check)
- Rejected request does not execute action

### D4: LLM Gateway Module

**File:** `src/executive_cli/llm_gateway.py`

Wraps existing `llm/client.py` with:
1. **Unified interface:** single `call_llm(prompt, schema, correlation_id)` function
2. **Fallback chain:** Anthropic → OpenAI → local (configurable order)
3. **Call logging:** every call logged to `llm_call_log` with tokens, latency, status
4. **Rate limiting:** configurable max calls per minute (setting `llm_rate_limit_per_min`, default 60)
5. **Response validation:** reject malformed LLM responses, log as `error`

```python
@dataclass
class LLMResponse:
    parsed: dict[str, Any]  # Structured output
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int

def call_llm(
    session: Session,
    *,
    prompt: str,
    response_schema: type[BaseModel] | None,
    correlation_id: str | None,
    provider: str | None = None,  # override default
    model: str | None = None,
    temperature: float = 0.0,
    now_iso: str,
) -> LLMResponse:
    """Call LLM with fallback chain and logging."""
```

**Acceptance criteria:**
- All LLM calls go through gateway (no direct `llm/client.py` usage from pipeline code)
- Fallback: if primary provider fails, tries secondary, then local
- Every call logged to `llm_call_log` with correct token counts and latency
- Rate limit: if exceeded, raises `LLMRateLimitError` (not silent drop)

### D5: CLI Commands

**New commands in `cli.py`:**

```
execas pipeline run <name> [--input-json <path>]   # Run a named pipeline
execas pipeline status [<run_id>]                   # Show pipeline run status
execas pipeline list [--status <status>]            # List recent pipeline runs

execas approve list                                 # List pending approvals
execas approve <id>                                 # Approve and execute
execas approve reject <id>                          # Reject
```

**Acceptance criteria:**
- `execas pipeline run email_ingest --input-json input.json` executes pipeline
- `execas pipeline status <id>` shows run status with step details
- `execas approve list` shows pending with action type and context summary
- `execas approve <id>` approves, executes action, shows result
- `execas approve reject <id>` rejects, shows confirmation

### D6: Refactor Email Ingest as Proof of Concept

Refactor `ingest_email_channel()` to run on the Pipeline Engine as pipeline `email_ingest`:

**Pipeline steps:**
1. `fetch_unprocessed` (deterministic) — query `emails` table for unprocessed headers
2. `extract` (llm) — call LLM via gateway to extract task candidates
3. `classify` (deterministic + llm) — resolve project/commitment hints
4. `dedup` (deterministic) — exact + fuzzy title match
5. `route` (deterministic + approval) — confidence-based routing; low-confidence → approval request

**Backward compatibility:**
- `execas ingest email` continues to work (calls `pipeline run email_ingest` internally)
- `execas ingest review` / `execas ingest accept` / `execas ingest skip` continue to work
- Existing `task_drafts` data preserved and accessible

**Acceptance criteria:**
- `execas pipeline run email_ingest` produces same results as current `execas ingest email`
- Low-confidence items appear in `execas approve list`
- `execas approve <id>` for a task creation approval creates the task
- All steps logged in `pipeline_events`
- Idempotency: re-running on already-processed emails = no-op
- All LLM calls logged in `llm_call_log`

---

## 3. Implementation Order

```
Step 1: Models + Migration (D1)
  ↓
Step 2: Pipeline Engine core (D2) — register, run, idempotency, retry
  ↓
Step 3: Approval Gate (D3) — request, approve, reject, list, execute
  ↓
Step 4: LLM Gateway (D4) — wrap existing client, add fallback + logging
  ↓
Step 5: CLI commands (D5)
  ↓
Step 6: Email Ingest refactor (D6) — proof of concept
  ↓
Step 7: Integration tests + quality gates
```

Steps 2–4 can be partially parallelized (engine and gate share no code; gateway is independent).

---

## 4. New Files

| File | Purpose |
|------|---------|
| `src/executive_cli/pipeline_engine.py` | Pipeline Engine: register, run, resume, status |
| `src/executive_cli/approval_gate.py` | Approval Gate: request, approve, reject, list, execute |
| `src/executive_cli/llm_gateway.py` | LLM Gateway: unified call, fallback, logging |
| `alembic/versions/<hash>_add_pipeline_engine_schema.py` | Migration for 4 new tables |
| `tests/test_pipeline_engine.py` | Unit tests for engine |
| `tests/test_approval_gate.py` | Unit tests for gate |
| `tests/test_llm_gateway.py` | Unit tests for gateway |
| `tests/test_email_ingest_pipeline.py` | Integration test for refactored email ingest |

## 5. Modified Files

| File | Change |
|------|--------|
| `src/executive_cli/models.py` | Add `PipelineRun`, `PipelineEvent`, `ApprovalRequest`, `LLMCallLog` models |
| `src/executive_cli/cli.py` | Add `pipeline` and `approve` command groups |
| `src/executive_cli/ingest/pipeline.py` | Refactor `ingest_email_channel` to use Pipeline Engine |
| `src/executive_cli/ingest/extractor.py` | Route LLM calls through `llm_gateway.py` |
| `src/executive_cli/db.py` | Add default settings for LLM rate limit |

---

## 6. Quality Gates

All gates mandatory before merge:

```bash
cd apps/executive-cli

# Unit tests pass
uv run pytest -q

# Coverage ≥80%
uv run pytest --cov=executive_cli --cov-fail-under=80

# Migration integrity
rm -f .data/execas.sqlite && uv run execas init

# Specific new tests pass
uv run pytest tests/test_pipeline_engine.py tests/test_approval_gate.py tests/test_llm_gateway.py tests/test_email_ingest_pipeline.py -v
```

---

## 7. Risks

| Risk | Mitigation |
|------|-----------|
| Over-engineering pipeline engine | Keep it simple: Python functions, no YAML DSL in Sprint 1. Max 6 step types. |
| Breaking existing ingest tests | Run all existing tests after each step. Refactored `ingest_email_channel` must produce identical output. |
| SQLite write contention with pipeline events | WAL mode (already default). Pipeline events are append-only, low contention. |
| Approval UX too complex for CLI | Sprint 1: simple `approve <id>`. Batch mode in Sprint 3. |
| LLM gateway adds latency | Gateway is a thin wrapper. No network hops (same process). Measure latency delta. |

---

## 8. Definition of Done

- [ ] All 4 tables created via Alembic migration
- [ ] 4 new SQLModel classes in `models.py`
- [ ] Pipeline Engine: register, run, resume, status — all working
- [ ] Idempotency: re-run same pipeline = no duplicate events
- [ ] Retry: configurable per-step, exponential backoff
- [ ] Approval Gate: request, approve, reject, list, execute
- [ ] LLM Gateway: unified call, fallback chain, call logging
- [ ] CLI: `pipeline run`, `pipeline status`, `pipeline list`, `approve list`, `approve <id>`, `approve reject`
- [ ] Email Ingest runs on Pipeline Engine (backward compatible)
- [ ] All existing tests still pass
- [ ] New tests: ≥80% coverage on new modules
- [ ] Migration integrity gate passes
- [ ] Correlation ID tracing works end-to-end
