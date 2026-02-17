# Reengineering Plan: Agent Layer + Service Layer Architecture

**Date:** 2026-02-17
**Author:** Chief Architect + Technical Lead
**Status:** Proposed
**Scope:** 4-sprint restructuring of Agentura into two-layer architecture

---

## 1. Problem Statement

Current state:
- LLM agents are chatty and unpredictable — side-effects, weak reproducibility.
- No generic pipeline infrastructure — each workflow is ad-hoc code.
- No universal approval mechanism — confidence routing baked into ingest router.
- No cross-pipeline audit or observability.
- Time-to-value for new workflows is high (each requires full custom implementation).

Target state:
- **Agent Layer** — LLM agents do interpretation/classification, produce proposals (never write directly).
- **Service Layer** — deterministic pipelines execute actions, enforce approvals, maintain audit trail.
- Clear contracts between layers, idempotency everywhere, side-effects gated.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│  CLI (execas)  ·  [future: Telegram bot]  ·  [future: web]     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                      AGENT LAYER                                │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ EmailTriage  │  │ TaskExtract  │  │ ClarifyAgent         │  │
│  │ Agent        │  │ Agent        │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         │    ALL calls via LLM Gateway           │              │
│         │    ALL outputs = typed proposals        │              │
│         └─────────────────┼──────────────────────┘              │
│                           │                                     │
│  ┌────────────────────────┴──────────────────────────────────┐  │
│  │              LLM GATEWAY                                  │  │
│  │  Fallback chain · Rate limiting · Call logging            │  │
│  │  Anthropic → OpenAI → local heuristic                     │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ typed proposals (Pydantic models)
┌──────────────────────────┴──────────────────────────────────────┐
│                     SERVICE LAYER                               │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              PIPELINE ENGINE                               │ │
│  │  State machine runner · Retry · Idempotency · Correlation  │ │
│  │                                                            │ │
│  │  Registered pipelines:                                     │ │
│  │    email_triage · meeting_ingest · dialogue_ingest         │ │
│  │    gtd_daily · delegation_followup · weekly_reflect        │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                             │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │              APPROVAL GATE                                 │ │
│  │  Any side-effect action → pending → approved/rejected      │ │
│  │  Action types: create_task, send_message, add_busy_block   │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                             │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │          DOMAIN SERVICES (single-writer, ADR-09)           │ │
│  │                                                            │ │
│  │  TaskService · PlannerService · CalendarSync · MailSync    │ │
│  │  PeopleService · DecisionService · WeeklyReviewService     │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │          DATA LAYER (SQLite, WAL mode)                     │ │
│  │                                                            │ │
│  │  tasks · emails · busy_blocks · pipeline_runs              │ │
│  │  pipeline_events · approval_requests · llm_call_log        │ │
│  │  ingest_documents · task_drafts · sync_state · ...         │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                    CONNECTOR LAYER                              │
│  CalDAV (Yandex) · IMAP (Yandex) · [future: Telegram Bot API] │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Key Invariants

| # | Invariant | Enforced by |
|---|-----------|-------------|
| I1 | Agents NEVER write to DB directly | Agent outputs are typed proposals; only Service Layer writes |
| I2 | All side-effects go through Approval Gate | Side-effect registry; pipeline engine routes to gate |
| I3 | Every pipeline step has an idempotency key | Pipeline Engine computes `hash(run_id + step + input)` |
| I4 | Every LLM call is logged with cost/latency | LLM Gateway writes to `llm_call_log` |
| I5 | Correlation ID traces request end-to-end | Pipeline Engine generates UUID, propagates to all events |
| I6 | No email body stored or sent to LLM | ADR-10 preserved; subject + sender only |
| I7 | Single writer for all task/plan data | ADR-09; `task_service.create_task_record()` is sole entry |
| I8 | Confidence-based routing with approval | ≥0.8 auto (still through gate, just pre-approved); <0.8 human review |

---

## 4. Deterministic Pipeline Catalog

### P1: Email Triage Pipeline (`email_triage`)

**Trigger:** `execas pipeline run email_triage` or `execas daily`
**Input:** `{since: date | null, limit: int}`

| Step | Type | Handler | Retry | Approval |
|------|------|---------|-------|----------|
| 1. `fetch` | deterministic | MailSync.get_unprocessed_headers | 0 | no |
| 2. `classify` | llm | EmailTriageAgent.classify(header) | 2 | no |
| 3. `route` | deterministic | confidence routing + dedup check | 0 | conditional |
| 4. `create_or_draft` | approval | TaskService.capture or ApprovalGate.request | 0 | if conf < 0.8 |

### P2: Meeting Ingest Pipeline (`meeting_ingest`)

**Trigger:** `execas ingest meeting <file>` or `execas pipeline run meeting_ingest`
**Input:** `{file_path: str, title: str | null}`

| Step | Type | Handler | Retry | Approval |
|------|------|---------|-------|----------|
| 1. `parse` | deterministic | read file, detect format | 0 | no |
| 2. `extract` | llm | TaskExtractorAgent.extract(text) | 2 | no |
| 3. `classify` | llm | ClarifyAgent.resolve(candidates) | 1 | no |
| 4. `dedup` | deterministic | exact + fuzzy title match | 0 | no |
| 5. `route` | approval | per-candidate confidence routing | 0 | if conf < 0.8 |

### P3: GTD Daily Pipeline (`gtd_daily`)

**Trigger:** `execas daily`
**Input:** `{date: date, variant: str}`

| Step | Type | Handler | Retry | Approval |
|------|------|---------|-------|----------|
| 1. `sync` | deterministic | CalendarSync + MailSync (parallel) | 3 | no |
| 2. `triage` | fan_out | Run P1 for each new email | per-item | per-item |
| 3. `organize` | deterministic | assign contexts, link projects | 0 | no |
| 4. `approval_batch` | approval | present all pending approvals | 0 | batch |
| 5. `plan` | deterministic | PlannerService.plan_day (ADR-06) | 0 | no |
| 6. `report` | deterministic | summary output | 0 | no |

### P4: Delegation Follow-up Pipeline (`delegation_followup`) — Sprint 3

**Trigger:** `execas daily` or `execas pipeline run delegation_followup`

| Step | Type | Handler | Retry | Approval |
|------|------|---------|-------|----------|
| 1. `scan` | deterministic | TaskService.list(WAITING, ping_at <= now) | 0 | no |
| 2. `draft` | llm | ResponseDraftAgent.draft_followup | 2 | no |
| 3. `approve` | approval | always requires approval (external comms) | 0 | yes |
| 4. `send` | deterministic | NotificationService.send | 1 | no |
| 5. `update` | deterministic | TaskService.update_ping | 0 | no |

### P5: Weekly Reflect Pipeline (`weekly_reflect`) — Sprint 4

**Trigger:** `execas review week` or `execas pipeline run weekly_reflect`

| Step | Type | Handler | Retry | Approval |
|------|------|---------|-------|----------|
| 1. `collect` | deterministic | TaskService.stats + PlannerService.review | 0 | no |
| 2. `analyze` | llm | ReflectAgent.analyze | 1 | no |
| 3. `store` | deterministic | WeeklyReviewService.save | 0 | no |
| 4. `present` | deterministic | CLI output | 0 | no |

---

## 5. Agent Specifications

### EmailTriageAgent

| Aspect | Detail |
|--------|--------|
| **Purpose** | Classify incoming email: action_required / FYI / spam / delegate / calendar_event |
| **Input** | `EmailHeader{subject, sender, received_at, flags}` |
| **Output** | `TriageResult{category, confidence, suggested_actions[], urgency}` |
| **Tools** | LLM Gateway, TaskService.search_similar, PeopleService.lookup |
| **Confidence** | ≥0.8 auto-route; 0.3–0.79 → approval; <0.3 skip |
| **Sprint** | 2 (Sprint 1 uses existing extractor as placeholder) |

### TaskExtractorAgent

| Aspect | Detail |
|--------|--------|
| **Purpose** | Extract task candidates from unstructured text |
| **Input** | `Document{channel, text, metadata}` |
| **Output** | `list[ExtractedCandidate{title, priority, estimate, confidence, rationale}]` |
| **Tools** | LLM Gateway, TaskService.dedup_check |
| **Confidence** | ≥0.8 auto-create; 0.3–0.79 → draft; <0.3 log-only |
| **Sprint** | 1 (wraps existing `ingest/extractor.py`) |

### ClarifyAgent

| Aspect | Detail |
|--------|--------|
| **Purpose** | Resolve project, area, commitment hints against DB |
| **Input** | `ExtractedCandidate` |
| **Output** | `ClassifiedCandidate{...candidate, project_id, area_id, commitment_id}` |
| **Tools** | LLM Gateway, ProjectService.match, CommitmentService.match |
| **Sprint** | 2 (Sprint 1 uses existing `ingest/classifier.py`) |

### ResponseDraftAgent (Wave 2)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Generate email/message reply drafts |
| **Input** | `EmailHeader + TriageResult + context` |
| **Output** | `DraftResponse{to, subject, body_draft, confidence}` |
| **Approval** | ALWAYS (never auto-send) |
| **Sprint** | 4 |

### ReflectAgent (Wave 2)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Weekly/daily review with metrics and suggestions |
| **Input** | `ReviewRequest{period, scope}` |
| **Output** | `ReviewReport{metrics, blockers[], suggestions[]}` |
| **Side-effects** | None (advisory only) |
| **Sprint** | 4 |

---

## 6. Microservice Boundary Map (In-Process Modules)

> On MVP: Python packages within the monolith. Microservice-ready boundaries via typed interfaces.

| Module | Responsibility | Interface | Data | Sprint |
|--------|---------------|-----------|------|--------|
| `pipeline_engine` | Execute pipelines, retry, idempotency | `run_pipeline()`, `resume_pipeline()`, `get_status()` | `pipeline_runs`, `pipeline_events` | 1 |
| `approval_gate` | Queue and resolve approval requests | `request_approval()`, `approve()`, `reject()`, `list_pending()` | `approval_requests` | 1 |
| `llm_gateway` | Proxy all LLM calls, fallback, logging | `call_llm()` | `llm_call_log` | 1 |
| `task_service` | GTD task lifecycle | `capture()`, `move()`, `done()`, `waiting()` | `tasks`, `task_email_links` | existing |
| `sync_service` | CalDAV + IMAP sync | `sync_calendar()`, `sync_mail()` | `busy_blocks`, `emails`, `sync_state` | existing |
| `planner` | Deterministic day planning | `plan_day()` | `day_plans`, `time_blocks` | existing |
| `review` | Weekly review builder | `build_review()` | `weekly_reviews` | existing |
| `ingest/*` | Ingestion pipeline stages | (being refactored to Pipeline Engine) | `ingest_documents`, `task_drafts`, `ingest_log` | 1 (refactor) |

---

## 7. Sprint Plan

### Sprint 1: Pipeline Engine + Approval Gate (2 weeks)

**Goal:** Build infrastructure, prove with email ingest refactor.

**Deliverables:** See `spec/TASKS/TASK_S1_PIPELINE_ENGINE.md`
- ADR-12 migration (4 tables)
- Pipeline Engine (register, run, resume, idempotency, retry)
- Approval Gate (request, approve, reject, execute)
- LLM Gateway (unified call, fallback, logging)
- CLI commands (pipeline run/status/list, approve list/<id>/reject)
- Email Ingest refactored as proof of concept

**DoD:** All existing tests pass + new module coverage ≥80% + migration integrity.

### Sprint 2: Agent Isolation + Confidence Calibration (2 weeks)

**Goal:** Full agent isolation through LLM Gateway, calibrate on real data.

**Deliverables:**
- EmailTriageAgent: full email classification (not just task extraction)
- ClarifyAgent: DB-backed entity resolution
- Meeting + Dialogue ingest refactored to Pipeline Engine
- Confidence calibration: tune thresholds on first 100 real emails
- Contract-first: Pydantic schemas for all agent inputs/outputs
- Structured JSON logging + pipeline metrics

**DoD:** All 3 ingest channels on Pipeline Engine. EmailTriage accuracy ≥70% on test set. All LLM calls via gateway.

### Sprint 3: GTD Daily Pipeline + Batch Approvals (2 weeks)

**Goal:** One-command daily workflow, batch approval UX.

**Deliverables:**
- `execas daily` — full GTD cycle: sync → triage → organize → approve → plan → report
- Batch approval: `execas approve batch` (interactive CLI review)
- Delegation follow-up pipeline (draft generation, always-approval)
- Side-effect registry: catalog of all gated operations

**DoD:** `execas daily` completes in <5 minutes. Batch approval works. E2E test: email → triage → task → plan.

### Sprint 4: Response Drafts + Observability + Hardening (2 weeks)

**Goal:** Full operational maturity for daily use.

**Deliverables:**
- ResponseDraftAgent: email reply draft generation (always-approval)
- Weekly Reflect Pipeline on Pipeline Engine
- `execas dash` — operational dashboard (pipeline health, approvals, stats)
- Full observability: correlation tracing, error alerting
- Config-as-code: pipeline definitions in Python DSL
- Security hardening: input validation, LLM output sanitization
- Performance: parallel step execution within pipelines

**DoD:** Zero unhandled exceptions over 1 week. Dashboard renders in <2s. Documentation complete.

---

## 8. Engineering Standards

| Standard | Requirement |
|----------|-----------|
| **Contracts** | Pydantic `BaseModel` for all inputs/outputs. Version prefix `v1/` in modules for breaking changes. |
| **Tests** | Unit ≥80% coverage. Integration: per-pipeline E2E. No mocking DB — use in-memory SQLite. |
| **Observability** | Structured JSON logging (`structlog`). Counters: pipeline_runs, approvals, llm_calls. Histograms: latency. Correlation ID in all log entries. |
| **Security** | No secrets in code/DB. LLM input sanitization. Output validation. Rate limiting. Audit log immutable. |
| **Versioning** | Semantic versioning for CLI. ADR for schema changes. Alembic forward-only. |
| **Error handling** | Typed exceptions: `PipelineError`, `LLMError`, `ApprovalTimeout`. Per-step retry. Dead-letter for failed items. |
| **Idempotency** | Every write has idempotency key. Repeat = no-op. Pipeline steps at-least-once with dedup. |
| **Data integrity** | FK enforced. CHECK constraints. Single-writer (ADR-09). WAL mode for concurrent reads. |

---

## 9. Key Risks & Mitigations

| # | Risk | P | I | Mitigation |
|---|------|---|---|-----------|
| 1 | LLM classification accuracy <70% | H | H | Confidence threshold + approval gate + fallback chain + calibration Sprint 2 |
| 2 | Approval fatigue | M | H | Batch UX Sprint 3; auto-threshold tuning; category bypass |
| 3 | Pipeline state corruption on crash | M | H | WAL mode; per-step transactions; idempotency replay; `pipeline repair` |
| 4 | LLM API downtime | M | M | 3-provider fallback; exponential backoff; local heuristic |
| 5 | Over-engineering pipeline engine | H | M | Python functions only Sprint 1; no YAML DSL; max 6 pipelines |
| 6 | Email body privacy leak | L | C | ADR-10: no body. Input validation on gateway. Audit all LLM calls |
| 7 | SQLite write contention | M | M | WAL mode; 1 writer N readers; post-MVP Postgres evaluation |
| 8 | Scope creep (Telegram, deals) | H | M | Strict scope: MVP = email + meetings + CLI. Each extension via ADR |
| 9 | Regression in existing CLI | M | M | 19 test files as safety net; incremental refactor per command |
| 10 | LLM cost spiral | M | M | Response caching; subject-only prompts; daily call budget in config |
| 11 | Idempotency gaps → duplicate tasks | M | H | Composite key (source + content hash); dedup before capture; audit detection |
| 12 | Ambiguous GTD classification | H | M | Multi-label output; action item takes precedence; confidence per category |

---

## 10. Assumptions

1. **Single-host deployment** — Docker Compose, not Kubernetes. One user, one SQLite.
2. **Email volume** — 50–100 emails/day, 5–10 meetings/week. Pipeline engine handles this without async workers.
3. **LLM budget** — ~$5–10/day at current Anthropic pricing for 100 classification calls.
4. **SQLite remains** — No Postgres migration in these 4 sprints. WAL mode sufficient.
5. **CLI-first** — No Telegram bot or web UI in these sprints. Future extensions via ADR.
6. **Existing ingest pipeline works** — ADR-11 implementation is stable baseline for refactoring.
7. **n8n deferred** — I/O bus integration (ADR-14) is post-Sprint 4.

---

## 11. ADR Roadmap

| ADR | Topic | Sprint | Status |
|-----|-------|--------|--------|
| ADR-12 | Pipeline Engine & Approval Gate | 1 | **Proposed** (this plan) |
| ADR-13 | Telegram channel integration | post-S4 | Deferred |
| ADR-14 | n8n integration bus boundary | post-S4 | Deferred |
| ADR-15 | Autonomy level framework | post-S4 | Deferred |

---

## 12. Success Criteria (Day 60 — End of Sprint 4)

1. `execas daily` processes emails + meetings → tasks + day plan in <5 minutes.
2. All LLM calls traced with correlation ID, cost, latency.
3. Every task creation from pipeline goes through approval gate.
4. Re-running any pipeline with same input = no duplicates (idempotency).
5. Pipeline failure → automatic retry → dead-letter if exhausted.
6. Zero data loss on crash (WAL + transactional steps).
7. Operational overhead reduced by ~40% (from ~2–3 hours to ~1–1.5 hours/day).
