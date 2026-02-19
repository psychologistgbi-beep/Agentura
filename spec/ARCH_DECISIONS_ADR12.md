# ADR-12: Pipeline Engine & Approval Gate

**Date:** 2026-02-17
**Author:** Chief Architect
**Status:** Proposed
**Depends on:** ADR-09 (single writer), ADR-11 (ingestion pipeline)

---

## Context

The current ingestion pipeline (ADR-11) is hard-coded as a linear function chain inside `ingest/pipeline.py`. There is no generic mechanism for:

1. **Reusable deterministic pipelines** — new workflows (email triage, delegation follow-up, daily GTD cycle) would require duplicating the pattern of extract → classify → dedup → route.
2. **Approval gates** — confidence-based routing in `ingest/router.py` auto-creates tasks above threshold, but there is no universal "pause-and-wait-for-human" mechanism usable across different pipelines.
3. **Audit trail** — `ingest_log` is pipeline-specific; there is no cross-pipeline event log.
4. **Idempotency** — each pipeline implements its own dedup; there is no generic idempotency-key mechanism.
5. **Error handling** — LLM failure causes the document to stay `pending`, but there is no retry policy, dead-letter queue, or backoff.

The reengineering plan calls for a two-layer architecture (Agent Layer + Service Layer) with deterministic pipeline execution as the backbone.

---

## Decision

Introduce a **Pipeline Engine** (deterministic state-machine runner) and an **Approval Gate** (human-in-the-loop blocker) as core infrastructure, backed by four new tables.

### 1. Pipeline Engine

A pipeline is a named sequence of **steps**. Each step has:
- A **handler function** `(context: StepContext) -> StepResult`
- A **step type**: `deterministic`, `llm`, `approval`, `fan_out`
- **Retry policy**: `max_retries`, `backoff_seconds`
- **Idempotency key**: `hash(pipeline_run_id + step_name + input_hash)`

Pipeline execution model:
```
PipelineRun(id, pipeline_name, status, input_hash, correlation_id, created_at, updated_at)
    └── PipelineEvent(id, run_id, step_name, status, input_hash, output_hash,
                      idempotency_key, attempt, error, created_at)
```

**Status transitions for PipelineRun:**
```
pending → running → completed
                  → failed (all retries exhausted on any step)
                  → waiting_approval (blocked on approval gate)
```

**Status transitions for PipelineEvent (per step):**
```
pending → running → completed
                  → failed → retrying → completed | failed
                  → waiting_approval → approved → completed
                                     → rejected → completed (with skip)
```

**Idempotency:** Before executing a step, engine checks `idempotency_key` in `pipeline_events`. If a `completed` event exists with the same key, the step is skipped and cached output is returned. This makes pipeline re-runs safe after crash recovery.

**Correlation ID:** Every pipeline run gets a UUID `correlation_id` propagated to all events, LLM calls, and audit entries — enabling end-to-end tracing.

### 2. Approval Gate

When a pipeline step produces an action requiring human approval, it creates an `ApprovalRequest`:

```
ApprovalRequest(id, pipeline_run_id, step_name, action_type, action_payload_json,
                context_json, status, decided_at, decided_by, created_at)
```

**Status transitions:**
```
pending → approved → (pipeline resumes)
        → rejected → (pipeline logs rejection, continues to next item or terminates)
        → expired  → (after configurable TTL, treated as rejected)
```

**Action types registry** (extensible):
- `create_task` — create a task from draft
- `send_message` — send email/telegram (Wave 2)
- `add_busy_block` — add calendar event
- `modify_task` — change task status/fields
- `batch_create_tasks` — accept multiple drafts at once

**CLI integration:**
- `execas approve list` — show pending approvals
- `execas approve <id>` — approve specific request
- `execas approve reject <id>` — reject
- `execas approve batch` — interactive review of all pending

### 3. Audit Log

All pipeline events are the audit trail. Additionally, a lightweight `audit_log` view aggregates cross-pipeline events:

```sql
-- Not a separate table; audit queries run against pipeline_events
-- with optional JOIN to approval_requests.
-- This avoids data duplication while providing full traceability.
```

### 4. Schema

#### Table: `pipeline_runs`

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK auto-increment | |
| `pipeline_name` | TEXT NOT NULL | INDEX | e.g. `email_triage`, `meeting_ingest`, `gtd_daily` |
| `status` | TEXT NOT NULL | | `pending`/`running`/`completed`/`failed`/`waiting_approval` |
| `input_hash` | TEXT | | SHA-256 of pipeline input for idempotency |
| `correlation_id` | TEXT NOT NULL | UNIQUE | UUID for tracing |
| `input_json` | TEXT | | Serialized pipeline input (for replay) |
| `output_json` | TEXT | | Serialized pipeline output |
| `error` | TEXT | | Error message if failed |
| `created_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |
| `updated_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |

#### Table: `pipeline_events`

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK auto-increment | |
| `run_id` | INTEGER NOT NULL | FK → pipeline_runs.id, INDEX | |
| `step_name` | TEXT NOT NULL | | e.g. `fetch`, `classify`, `route` |
| `step_type` | TEXT NOT NULL | | `deterministic`/`llm`/`approval`/`fan_out` |
| `status` | TEXT NOT NULL | | `pending`/`running`/`completed`/`failed`/`retrying`/`waiting_approval`/`approved`/`rejected` |
| `input_hash` | TEXT | | SHA-256 of step input |
| `output_hash` | TEXT | | SHA-256 of step output |
| `idempotency_key` | TEXT | UNIQUE INDEX | `hash(run_id + step_name + input_hash)` |
| `attempt` | INTEGER NOT NULL | DEFAULT 1 | Retry counter |
| `error` | TEXT | | Error details if failed |
| `duration_ms` | INTEGER | | Execution time |
| `created_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |

#### Table: `approval_requests`

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK auto-increment | |
| `pipeline_run_id` | INTEGER | FK → pipeline_runs.id, INDEX | Nullable for standalone approvals |
| `step_name` | TEXT | | Pipeline step that triggered this |
| `action_type` | TEXT NOT NULL | INDEX | `create_task`/`send_message`/etc. |
| `action_payload_json` | TEXT NOT NULL | | Serialized action details |
| `context_json` | TEXT | | Human-readable context for reviewer |
| `status` | TEXT NOT NULL | DEFAULT `pending` | `pending`/`approved`/`rejected`/`expired` |
| `decided_at` | TEXT | | ISO-8601 when decided |
| `decided_by` | TEXT | DEFAULT `user` | Who decided (future: delegation) |
| `created_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |

#### Table: `llm_call_log`

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK auto-increment | |
| `correlation_id` | TEXT | INDEX | Links to pipeline run |
| `provider` | TEXT NOT NULL | | `anthropic`/`openai`/`local` |
| `model` | TEXT NOT NULL | | Model identifier |
| `prompt_hash` | TEXT | | SHA-256 of prompt (not stored raw for privacy) |
| `prompt_tokens` | INTEGER | | Token usage |
| `completion_tokens` | INTEGER | | Token usage |
| `latency_ms` | INTEGER | | Response time |
| `status` | TEXT NOT NULL | | `success`/`error`/`timeout`/`fallback` |
| `error` | TEXT | | Error details |
| `created_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |

---

## Consequences

- **Pipeline Engine replaces ad-hoc pipeline code.** Existing `ingest/pipeline.py` will be refactored to register as a named pipeline (`meeting_ingest`, `dialogue_ingest`, `email_ingest`) on the engine. The engine handles execution, retry, idempotency, and audit — the pipeline only defines step handlers.
- **Approval Gate replaces confidence-based auto-create/draft split.** Instead of `task_drafts` table being a parallel concept, drafts become approval requests with `action_type=create_task`. The `task_drafts` table is preserved for backward compatibility but new pipelines use `approval_requests`.
- **LLM calls become auditable.** `llm_call_log` tracks cost, latency, and error rates across all pipelines — enabling cost control and provider comparison.
- **New CLI commands.** `execas pipeline run <name>`, `execas pipeline status [run_id]`, `execas approve list`, `execas approve <id>`, `execas approve reject <id>`, `execas approve batch`.
- **Migration required.** One new Alembic migration adding 4 tables. No changes to existing tables.
- **Single-writer preserved (ADR-09).** Pipeline Engine writes to its own tables. Task creation still goes through `task_service.create_task_record()`.

---

## Alternatives Considered

1. **Use Temporal/Prefect/Airflow for pipeline orchestration.**
   - Rejected: massive dependency for a single-user CLI app. Our pipelines are simple enough for an in-process state machine. Post-MVP evaluation if pipelines exceed 20 steps or need distributed execution.

2. **Keep `task_drafts` as the approval mechanism.**
   - Rejected: `task_drafts` is task-specific and cannot generalize to other approval needs (send message, add calendar event, modify task). `approval_requests` is action-agnostic.

3. **Store full LLM prompts/responses in `llm_call_log`.**
   - Rejected: privacy risk (prompts may contain user content). Store only hashes and metadata. Raw responses are parsed into structured output and discarded.

4. **Separate audit_log table.**
   - Rejected: `pipeline_events` already provides full audit trail. A separate table would duplicate data. Cross-pipeline queries use `pipeline_events JOIN pipeline_runs`.

---

## Rollback

- Drop 4 new tables via migration downgrade.
- Revert CLI commands to pre-engine versions.
- Existing `ingest/pipeline.py` continues to work as-is (it's being wrapped, not replaced).
