# Architecture Decision Records — Executive Assistant MVP

## ADR-01: Datetime Storage Strategy

**Context:** SQLite has no native timezone-aware datetime type. We need a consistent strategy for storing, comparing, and displaying datetimes across CLI input, DB, and planning algorithm.

**Decision:** Store all datetimes as ISO-8601 TEXT with explicit offset: `2026-02-15T10:00:00+03:00`.

**Rationale:**
- Human-readable in raw DB inspection.
- Offset is preserved (important when Russia changes DST rules or user travels).
- Python `datetime.fromisoformat()` (3.11+) parses this natively.
- Sorting: application code normalises to UTC for comparison; we do NOT rely on SQLite string sorting for cross-offset data.

**Consequences:**
- All DB read/write helpers must go through a `dt_to_db()`/`db_to_dt()` pair.
- Unit tests must cover: MSK input -> DB round-trip -> MSK output.
- `date`-only columns (e.g. `due_date`, `day_plans.date`) stored as `YYYY-MM-DD` TEXT.

---

## ADR-02: Timezone Strategy

**Context:** User operates in Europe/Moscow. CLI must interpret bare times as MSK. Future: possible travel/multi-tz.

**Decision:**
- `timezone` setting in DB (default `Europe/Moscow`) is the "display/input timezone".
- All CLI input without explicit offset is interpreted using this setting.
- All CLI output is formatted in this timezone.
- Internally, business logic operates on offset-aware Python `datetime` objects (via `zoneinfo.ZoneInfo`).

**Consequences:**
- No dependency on `pytz`; use stdlib `zoneinfo` (Python 3.9+).
- Changing `timezone` setting changes interpretation of future inputs/outputs but does NOT retroactively convert stored data (offsets are absolute).

---

## ADR-03: Busy Block Merge Policy

**Context:** Calendar events may overlap (manual entry, CalDAV sync duplicates). Spec requires deterministic merge.

**Decision:** Merge on read, not on insert.

**Rationale:**
- Preserves source fidelity: raw CalDAV events stored as-is, manual entries stored as-is.
- Merge is a pure function `merge_intervals(List[Interval]) -> List[Interval]`, easy to test.
- Planning algorithm and `busy list` both call merge before use.

**Details:**
- Overlap: intervals sharing any time range are merged into `(min(start), max(end))`.
- Adjacency: intervals where `end_a == start_b` are **merged** (conservative; avoids micro-gaps).
- Title of merged block: concatenation with " | " separator, sorted by original start time.

**Consequences:**
- `busy list` output may show fewer blocks than stored rows.
- CalDAV re-sync can INSERT duplicates safely; merge handles them.

---

## ADR-04: FTS5 Schema

**Context:** Need full-text search on People and Decisions.

**Decision:** Use SQLite FTS5 content-sync tables.

**Schema:**
```sql
CREATE VIRTUAL TABLE people_fts USING fts5(
    name, org, role, notes,
    content='people', content_rowid='id'
);

CREATE VIRTUAL TABLE decisions_fts USING fts5(
    title, context, choice, consequences,
    content='decisions', content_rowid='id'
);
```

**Sync strategy:** Use triggers (AFTER INSERT/UPDATE/DELETE on content tables) to keep FTS in sync. This is the standard SQLite FTS5 external content pattern.

**Consequences:**
- Triggers must be part of the migration.
- Search queries use `MATCH` syntax; CLI wraps user input with `*` suffix for prefix matching.

---

## ADR-05: Day Plan Upsert Policy

**Context:** User may run `plan day` multiple times for the same date and variant.

**Decision:** Replace (DELETE old + INSERT new) keyed on `(date, variant)`.

**Rationale:**
- MVP does not need plan history/versioning.
- Simplifies queries: at most 3 plans per date (one per variant).
- UNIQUE constraint on `(date, variant)` enforced at DB level.

**Consequences:**
- Previous plan for the same (date, variant) is lost.
- If versioning is needed later, add a `version` column.

---

## ADR-06: Planning Algorithm — Deterministic, No LLM

**Context:** Spec mentions LLM for proposals, but also requires determinism (same inputs -> same output).

**Decision:** `plan day` is fully deterministic. No LLM call.

**Algorithm summary:**
1. Build free windows = planning_window - merged_busy_blocks.
2. Reserve lunch (shift if conflict with busy).
3. Rank eligible tasks: `score = priority_weight + commitment_bonus + due_urgency`.
   - priority_weight: P1=30, P2=20, P3=10
   - commitment_bonus: +20 if linked to commitment
   - due_urgency: +15 if due today, +10 if due within 3 days
4. Variant controls how many tasks to schedule:
   - minimal: fill <=50% of free time, top tasks only.
   - realistic: fill ~75% of free time, include buffers.
   - aggressive: fill ~95% of free time, still keep buffer_min between blocks.
5. Fit tasks into free windows using first-fit-decreasing (by estimate).
6. Insert buffer_min gaps between adjacent scheduled blocks.

**Consequences:**
- LLM used only for `review week` narrative and future features.
- Scoring weights are configurable later; hardcoded for MVP.

---

## ADR-07: Yandex Integration Boundaries (MVP)

**Context:** Yandex Calendar (CalDAV) and Yandex Mail (IMAP) integration needed.

**Decision for MVP:**
- Integration layer is **stub + manual fallback**.
- `execas calendar sync` and `execas mail sync` are command stubs that:
  - Check for MCP connector availability.
  - If unavailable: print clear error with manual fallback instructions.
  - If available: delegate to MCP tool call (CalDAV PROPFIND/REPORT for calendar; IMAP FETCH for mail).
- Manual fallback: `execas busy add` for calendar, `execas task capture` for email-originated tasks.

**Integration interface (for future):**
```python
class CalendarConnector(Protocol):
    def fetch_events(self, start: date, end: date) -> list[BusyBlock]: ...

class MailConnector(Protocol):
    def fetch_inbox(self, since: datetime) -> list[EmailHeader]: ...
```

**Consequences:**
- No hard dependency on MCP in MVP; app works fully offline with manual input.
- When MCP is available, connectors implement the Protocol and are injected.
- Credentials/config for Yandex stored outside the app DB (env vars or MCP config).

---

## ADR-08: MVP Scope Boundaries

**In scope (must ship):**
- CLI with all commands from TECH_SPEC v0.1
- SQLite schema with migrations (Alembic)
- GTD task lifecycle (capture, move, done, waiting)
- Areas/Projects as reference data
- Commitments CRUD + link to tasks
- Manual busy blocks + merge logic
- Deterministic `plan day` (3 variants)
- People + Decisions with FTS5
- `calendar sync` and `mail sync` as stubs with fallback
- `review week` with ranked output (LLM optional for narrative)
- Unit tests for: merge logic, planning invariants, FTS, datetime conversions

**Out of scope (explicitly deferred):**
- Multi-calendar / multi-account
- Graphical UI
- Automatic rescheduling
- Task splitting across blocks
- Plan versioning/history
- Smart suggestions (LLM-powered task triage)
- Mobile/web access
- Notification/reminder system (beyond CLI ping_at display)

## ADR-09: Business Coach как advisory-роль, Executive Assistant — единственный writer

**Контекст:** Мы хотим добавить роль Business Coach, которая помогает уточнять цели, приоритеты и формировать предложения по задачам. При этом важно избежать хаоса и конфликтов изменений.

**Решение:** Business Coach работает в режиме advisory:
- Coach общается с пользователем напрямую и формирует рекомендации.
- Coach не имеет права изменять “источник правды” (SQLite).
- Executive Assistant — единственный writer: только он применяет изменения (создание/правка задач, статусов, планов) после явного подтверждения пользователя.

**Последствия:**
- Уменьшается риск расхождения состояния и “самовольных” правок.
- Все изменения проходят через один слой валидации/инвариантов (EA).
- В будущем можно добавить формальный протокол ChangeSet/apply, не ломая модель ролей.


---

## ADR-10: External Sync Provenance Schema (Calendar + Mail)

**Context:**
Backlog B1/B2 introduces incremental sync for Yandex CalDAV and Yandex Mail ingest with idempotency, deduplication, and traceable task-email links. Current schema has `busy_blocks` and `tasks`, but no stable external identity columns, no sync cursor storage, and no email linkage model.

**Decision:**
Adopt a provenance-first schema extension for external ingest:

1. Extend `busy_blocks` with external metadata for synced rows:
   - `source` (e.g. `manual`, `yandex_caldav`)
   - `external_id` (UID / UID+RECURRENCE-ID)
   - `external_etag`
   - `external_modified_at`
   - `is_deleted` (soft tombstone)
2. Add `sync_state` table for per-source cursor/watermark persistence:
   - keys: `(source, scope)`
   - fields: `cursor`, `cursor_kind`, `updated_at`
3. Add `emails` table for read-only message metadata:
   - `source`, `external_id`, `message_id`, `mailbox_uid`, `subject`, `sender`, `received_at`, `first_seen_at`, `last_seen_at`, `flags_json`
4. Add `task_email_links` join table:
   - `task_id`, `email_id`, `link_type`, `created_at`
   - unique `(task_id, email_id)`
5. Add dedup indexes:
   - `busy_blocks(calendar_id, source, external_id)` unique when `external_id` is not null
   - `emails(source, external_id)` unique

**Consequences:**
- Enables deterministic incremental sync and idempotent upserts.
- Preserves manual busy blocks as separate source from external calendar rows.
- Supports privacy-by-default email ingest (metadata only) while keeping auditability for task origin.
- Requires new Alembic migration and model updates before implementation of connector writes.

**Alternatives considered:**
- Keep state only in memory and perform full resync every run.
  - Rejected: expensive, higher duplicate/staleness risk, weak failure recovery.
- Store raw ICS/EML payloads in SQLite.
  - Rejected: unnecessary PII expansion and larger attack surface.
- Reuse `tasks.context` free text for email links.
  - Rejected: non-normalized, not query-safe, cannot enforce referential integrity.

**Rollback:**
- Disable connector sync commands and keep manual fallback (`busy add`, `task capture`).
- Migration rollback removes added tables/columns/indexes and returns to manual-only model.

---

## ADR-11: Task Ingestion Pipeline (LLM-Assisted Extraction from Multiple Channels)

**Context:**
GTD backlog is populated only via manual `execas task capture`. Actionable items from meeting protocols, assistant dialogues, and incoming email are routinely lost because there is no automated extraction path. ADR-10 provides email metadata storage and task-email links, but no mechanism to extract task candidates from any channel.

**Decision:**
Adopt a four-stage ingestion pipeline: Extract → Classify → Deduplicate → Route.

1. **Extract (LLM-required):** Parse unstructured text from three channels (meeting notes, assistant dialogues, email subjects) into structured task candidates with title, status, priority, estimate, due date, and confidence score.

2. **Classify (LLM-assisted + heuristic):** Resolve project/commitment/person hints against existing DB entities. Apply defaults for missing fields (priority=P2, estimate=30, status=NEXT).

3. **Deduplicate (deterministic):** Multi-level dedup — exact title match, fuzzy match (Levenshtein), source-specific checks (email already linked, document already processed). No LLM needed.

4. **Route (deterministic):** Confidence-based routing:
   - >= 0.8 → auto-create in `tasks` (via EA writer, ADR-09)
   - 0.3–0.79 → `task_drafts` for human review
   - < 0.3 → skip (logged only)
   - Threshold configurable via `ingest_auto_threshold` setting.

5. **Schema additions:** Three new tables — `ingest_documents` (source tracking), `task_drafts` (review queue), `ingest_log` (audit trail). No changes to existing `tasks`, `emails`, or `task_email_links` tables.

6. **LLM isolation:** Only `extractor.py` calls the LLM API. All other stages are deterministic. LLM credentials via env var (`LLM_API_KEY`), never in DB or repo.

7. **Privacy boundary:**
   - Meeting notes and dialogue transcripts: full text sent to LLM (user-initiated, user's own content).
   - Email: subject + sender only (no body — ADR-10 line 236 preserved).
   - LLM raw responses discarded after structured parsing.

**Consequences:**
- First LLM dependency in the pipeline (ADR-06 kept `plan day` deterministic — ingestion is explicitly non-deterministic by nature).
- Human-in-the-loop by default: conservative threshold means most candidates go to review queue.
- Manual `task capture` remains fully functional — ingestion is additive, not replacing.
- Three new tables require an Alembic migration (post-R1).
- LLM API cost is per-extraction — configurable model and batch limits control cost.

**Alternatives considered:**
- Rule-based extraction (regex patterns for "TODO:", "ACTION:", etc.)
  - Rejected: too brittle for Russian + English mixed content, misses implicit action items.
- Full email body analysis
  - Rejected: violates ADR-10 privacy boundary (no body storage/transmission).
- Single auto-create mode (no review queue)
  - Rejected: LLM hallucination risk too high for trusted GTD backlog; review queue is essential safety net.
- Embedding-based semantic dedup
  - Deferred: adds vector DB dependency; simple string dedup sufficient for MVP ingestion.

**Rollback:**
- Remove `ingest` CLI commands.
- Drop `ingest_documents`, `task_drafts`, `ingest_log` tables via migration downgrade.
- Tasks already auto-created remain in `tasks` table (they are valid tasks).
- Manual `task capture` + `task capture --from-email` (R3) continue to work.

---

## ADR-12: Pipeline Engine & Approval Gate

**Date:** 2026-02-17
**Author:** Chief Architect
**Status:** Proposed
**Depends on:** ADR-09 (single writer), ADR-11 (ingestion pipeline)

**Context:**
The current ingestion pipeline (ADR-11) is a hard-coded linear function chain inside `ingest/pipeline.py`. There is no generic mechanism for reusable deterministic pipelines, universal approval gates, cross-pipeline audit, generic idempotency keys, or retry/dead-letter policies. The reengineering plan calls for a two-layer architecture (Agent Layer + Service Layer) with deterministic pipeline execution as the backbone.

**Decision:**
Introduce a Pipeline Engine (deterministic state-machine runner) and an Approval Gate (human-in-the-loop blocker) as core infrastructure. Four new tables: `pipeline_runs`, `pipeline_events`, `approval_requests`, `llm_call_log`. Full specification in `spec/ARCH_DECISIONS_ADR12.md`.

Key design points:
1. Pipeline = named sequence of typed steps (`deterministic`/`llm`/`approval`/`fan_out`), each with retry policy and idempotency key.
2. Approval Gate = action-agnostic queue with `pending`→`approved`/`rejected`/`expired` lifecycle.
3. Idempotency via `hash(run_id + step_name + input_hash)` — re-run after crash = no-op for completed steps.
4. Correlation ID (UUID) propagated through all events for end-to-end tracing.
5. LLM calls logged with token counts, latency, provider — never raw prompts (privacy).
6. Single-writer preserved (ADR-09): pipeline engine writes to its own tables; task creation still via `task_service.create_task_record()`.

**Consequences:**
- Existing `ingest/pipeline.py` refactored to register as named pipelines on the engine.
- `task_drafts` table preserved for backward compat; new pipelines use `approval_requests`.
- New CLI: `execas pipeline run <name>`, `execas pipeline status`, `execas approve list|<id>|reject|batch`.
- One new Alembic migration adding 4 tables, no changes to existing tables.

**Rollback:**
- Drop 4 new tables. Revert CLI commands. `ingest/pipeline.py` continues to work as-is.

