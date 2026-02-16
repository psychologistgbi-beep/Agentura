# TASK: Task Ingestion Pipeline — Architecture Design

**Author:** Chief Architect + System Analyst
**Date:** 2026-02-16
**ADR reference:** ADR-11 (this design motivates ADR-11 in `spec/ARCH_DECISIONS.md`)
**Depends on:** ADR-10 (email schema), R1 (schema migration), R3 (mail sync)

---

## 1. Problem Statement

GTD backlog is populated only via manual `execas task capture`. Tasks are lost between meetings, email threads, and assistant conversations. The system needs automatic extraction of actionable items from unstructured input channels.

---

## 2. Input Channels

### C1: Meeting Protocols

| Aspect | Detail |
|--------|--------|
| **Format** | Markdown text (transcription output, manual notes, or structured protocol) |
| **Input method** | File path or stdin: `execas ingest meeting <file.md>` |
| **Frequency** | On-demand, after each meeting |
| **Typical content** | "Договорились: Петров готовит КП до пятницы", action items, decisions, deadlines |
| **Storage** | New table `ingest_documents` — keeps source text reference + metadata |

### C2: Assistant Dialogues

| Aspect | Detail |
|--------|--------|
| **Format** | Plain text (conversation transcript export or session summary) |
| **Input method** | File path or stdin: `execas ingest dialogue <file.txt>` |
| **Frequency** | On-demand or batch (end-of-day digest) |
| **Typical content** | "Нужно добавить валидацию в API", technical decisions, agreed next steps |
| **Storage** | Same `ingest_documents` table, different `channel` value |

### C3: Incoming Work Email

| Aspect | Detail |
|--------|--------|
| **Format** | Email metadata already in `emails` table (ADR-10: subject, sender, received_at) |
| **Input method** | Automatic after `execas mail sync` (R3) or manual: `execas ingest email [--since YYYY-MM-DD]` |
| **Frequency** | After each `mail sync` run (hourly target) or on-demand |
| **Typical content** | "Re: Контракт — прошу подписать", requests, follow-ups, FYI |
| **Storage** | Reuses existing `emails` table — no duplication |

### IngestSource Abstraction

```python
class IngestSource(Protocol):
    """Common interface for all ingestion channels."""

    @property
    def channel(self) -> str:
        """Channel identifier: 'meeting_notes' | 'assistant_dialogue' | 'yandex_imap'"""
        ...

    def fetch_unprocessed(self) -> list[IngestItem]:
        """Return items not yet processed by the pipeline."""
        ...

@dataclass
class IngestItem:
    source_channel: str          # 'meeting_notes' | 'assistant_dialogue' | 'yandex_imap'
    source_ref: str              # document id or email id
    raw_text: str                # text to send to LLM for extraction
    context: dict[str, str]      # channel-specific metadata (sender, date, participants, etc.)
```

**Extensibility:** Adding a new channel means:
1. Implement `IngestSource` protocol.
2. Register channel name in `ingest_channels` setting (or table).
3. No changes to Extract/Classify/Deduplicate/Route stages.

---

## 3. Pipeline Architecture

```
┌──────────┐    ┌───────────┐    ┌─────────────┐    ┌─────────┐    ┌─────────┐
│  Source   │───>│  Extract  │───>│  Classify   │───>│  Dedup  │───>│  Route  │
│ (C1/C2/C3)│   │  (LLM)    │    │ (LLM+heur.) │    │ (determ.)│   │ (determ.)│
└──────────┘    └───────────┘    └─────────────┘    └─────────┘    └─────────┘
                                                                        │
                                                          ┌─────────────┼──────────────┐
                                                          ▼             ▼              ▼
                                                    task_drafts    tasks (auto)    skipped
                                                   (review queue)  (high confidence) (logged)
```

### Stage 1: Extract (LLM-required)

**Input:** `IngestItem.raw_text` + `IngestItem.context`

**LLM task:** From the source text, extract zero or more task candidates. Each candidate is a structured object:

```json
{
  "title": "Подготовить КП для ООО Ромашка",
  "suggested_status": "WAITING",
  "suggested_priority": "P2",
  "estimate_min": 60,
  "due_date": "2026-02-21",
  "waiting_on": "Петров",
  "ping_at": "2026-02-21T10:00:00+03:00",
  "commitment_hint": "YC-1",
  "project_hint": "Agentura",
  "confidence": 0.85,
  "rationale": "Явное поручение с дедлайном из протокола встречи"
}
```

**LLM prompt strategy:**
- System prompt defines the GTD model (statuses, priorities, what constitutes an actionable item).
- Few-shot examples for each channel type (meeting → WAITING pattern, email → NEXT pattern).
- Structured output via JSON schema constraint (or function-call mode).
- Temperature = 0 for reproducibility.

**What is sent to LLM:**
- C1 (meeting): full protocol text (user's own notes — low PII risk).
- C2 (dialogue): full transcript text (user's own conversation — low PII risk).
- C3 (email): **subject + sender only** (ADR-10 line 236: no body stored; no body sent to LLM). If subject is too terse for extraction, the candidate gets low confidence.

**What is NOT sent to LLM:**
- Email body (never stored, never sent).
- Credentials, tokens, internal IDs.
- Any data from other users' accounts.

**Fallback if LLM unavailable:**
- Pipeline pauses. Source items remain in `ingest_documents` with `status='pending'`.
- User can manually process: `execas task capture` as before.
- No data loss — unprocessed items are retried on next run.

### Stage 2: Classify (LLM-assisted + heuristic)

**Input:** Task candidates from Stage 1.

**LLM-assisted mapping:**
- `project_hint` → resolve against existing projects (`projects` table, FTS or exact match).
- `commitment_hint` → resolve against existing commitments (`commitments` table, prefix match on "YC-N").
- `waiting_on` → resolve against `people` table (FTS match on name).

**Heuristic rules (deterministic, no LLM):**
- If `suggested_status` = WAITING and `waiting_on` is set → validate that `ping_at` is also set. If not, set `ping_at` = `due_date` or `now + 7d`.
- If `estimate_min` is missing → default to 30 (same as `task capture --from-email` default).
- If `suggested_priority` is missing → default to P2.
- If `confidence` < 0.3 → skip (log only, do not create draft).

**Output:** Enriched task candidates with resolved FKs (project_id, area_id, commitment_id) or NULL if no match.

### Stage 3: Deduplicate (deterministic, no LLM)

**Goal:** Prevent creating a task that already exists or is already in the draft queue.

**Algorithm:**
1. **Exact title match:** Compare `candidate.title` against `tasks.title` WHERE `status NOT IN ('DONE', 'CANCELED')`. Case-insensitive. If exact match → skip, log as "duplicate of task #N".

2. **Fuzzy title match:** Normalize titles (lowercase, strip punctuation, collapse whitespace). If normalized Levenshtein distance < 0.2 (i.e., 80%+ similar) → mark candidate with `dedup_flag='possible_duplicate'` and reference the existing task ID. Route to review queue (not auto-create).

3. **Source-specific dedup:**
   - C3 (email): check `task_email_links` — if an `origin` link already exists for this `email_id`, skip.
   - C1/C2: check `ingest_log` — if same `document_id` + similar title already processed → skip.

4. **Draft queue dedup:** Compare against `task_drafts` with `status='pending'`. If near-duplicate already in queue → skip.

**No LLM needed.** Dedup is string-based and deterministic. Future: optional embedding-based similarity (ADR-deferred).

### Stage 4: Route (deterministic, no LLM)

**Decision tree based on confidence:**

| Confidence | Action | Destination |
|-----------|--------|-------------|
| >= 0.8 | **Auto-create** | `tasks` table via EA writer (status = suggested_status or NEXT) |
| 0.3 – 0.79 | **Draft for review** | `task_drafts` table (status = 'pending') |
| < 0.3 | **Skip** | `ingest_log` only (reason = 'low_confidence') |
| any + `dedup_flag` | **Draft for review** | `task_drafts` with dedup warning |

**Auto-create rules:**
- EA is the single writer (ADR-09). The ingest pipeline calls the same `task_create()` service function that `task capture` uses.
- Auto-created tasks get `source_channel` metadata in a new nullable column `tasks.ingest_source` (or via `ingest_log` FK).
- For C3 (email): auto-creates `task_email_links` row with `link_type='origin'` (same as `task capture --from-email`).

**Confidence threshold is configurable:**
- Setting `ingest_auto_threshold` in `settings` table (default: `0.8`).
- User can set to `1.0` to disable auto-create entirely (all candidates go to review).

---

## 4. Human-in-the-Loop Policy

### Review flow

```
execas ingest review [--limit N]
```

Displays pending task drafts in a ranked list:

```
 #  | Confidence | Title                              | Source     | Action
 1  | 0.72       | Подготовить КП для Ромашка         | meeting    | [accept/edit/skip]
 2  | 0.55       | Check contract terms                | email      | [accept/edit/skip]
 3  | 0.45 ⚠dup  | Проверить API валидацию            | dialogue   | [accept/edit/skip]
```

**User actions per draft:**
- **Accept** (`a` or `--accept N`): creates task in `tasks` table with draft's fields. Moves draft to `status='accepted'`.
- **Edit** (`e` or `--edit N`): opens draft for editing (title, priority, estimate, status, project, etc.), then creates task. Moves draft to `status='accepted'`.
- **Skip** (`s` or `--skip N`): moves draft to `status='skipped'`. Logged but not created.
- **Accept all** (`--accept-all`): batch-accept all pending drafts with confidence >= threshold.

### When auto-create vs. review

| Scenario | Route | Rationale |
|----------|-------|-----------|
| Meeting note with explicit "TODO: X by Friday" | Auto-create (high confidence) | Clear action item with deadline |
| Email subject "Re: Контракт — подписать" | Draft (medium confidence) | Actionable but needs human judgment on priority/project |
| Dialogue fragment "может стоит..." | Skip or low-confidence draft | Speculative, not a clear action item |
| Duplicate of existing task | Draft with ⚠dup warning | Human decides: same task or different? |

### Policy summary

1. **Default: conservative.** `ingest_auto_threshold=0.8` means only very clear action items are auto-created.
2. **User can go fully manual** by setting threshold to `1.0`.
3. **User can go fully automatic** by setting threshold to `0.0` (not recommended — dedup may miss edge cases).
4. **All decisions are auditable** via `ingest_log`.

---

## 5. Data Model Extensions

### New table: `ingest_documents`

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK | Auto-increment |
| `channel` | TEXT NOT NULL | | `'meeting_notes'` / `'assistant_dialogue'` / `'yandex_imap'` |
| `source_ref` | TEXT NOT NULL | | File path (C1/C2) or `emails.id` as string (C3) |
| `title` | TEXT NULL | | Document title / email subject (for display) |
| `status` | TEXT NOT NULL | DEFAULT `'pending'` | `'pending'` / `'processed'` / `'failed'` |
| `items_extracted` | INTEGER NULL | | Count of task candidates found |
| `created_at` | TEXT NOT NULL | | ISO-8601 with offset (ADR-01) |
| `processed_at` | TEXT NULL | | When pipeline finished |

**Note:** For C3 (email), `source_ref` points to `emails.id`. The actual text (subject) is read from `emails` table at extraction time — no duplication. For C1/C2, the raw text is NOT stored in this table (it may be large and contain PII). Only the file path is stored; the file must be accessible at processing time.

### New table: `task_drafts`

Mirrors `tasks` fields but adds pipeline metadata:

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK | Auto-increment |
| `title` | TEXT NOT NULL | | Proposed task title |
| `suggested_status` | TEXT NOT NULL | | `'NEXT'` / `'WAITING'` / `'NOW'` |
| `suggested_priority` | TEXT NOT NULL | | `'P1'` / `'P2'` / `'P3'` |
| `estimate_min` | INTEGER NOT NULL | | Proposed estimate |
| `due_date` | TEXT NULL | | `YYYY-MM-DD` or NULL |
| `waiting_on` | TEXT NULL | | For WAITING drafts |
| `ping_at` | TEXT NULL | | ISO-8601 for WAITING |
| `project_hint` | TEXT NULL | | Suggested project name (not FK — may not resolve) |
| `commitment_hint` | TEXT NULL | | Suggested commitment ID |
| `confidence` | REAL NOT NULL | | 0.0–1.0 |
| `rationale` | TEXT NULL | | LLM's explanation of why this is a task |
| `dedup_flag` | TEXT NULL | | `'possible_duplicate'` + reference, or NULL |
| `source_channel` | TEXT NOT NULL | | Channel identifier |
| `source_document_id` | INTEGER NULL | FK → `ingest_documents.id` | Traceability to source |
| `source_email_id` | INTEGER NULL | FK → `emails.id` | For C3: direct email link |
| `status` | TEXT NOT NULL | DEFAULT `'pending'` | `'pending'` / `'accepted'` / `'skipped'` |
| `created_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |
| `reviewed_at` | TEXT NULL | | When user acted on draft |

### New table: `ingest_log`

Audit trail for every pipeline run:

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PK | Auto-increment |
| `document_id` | INTEGER NOT NULL | FK → `ingest_documents.id` | Which source was processed |
| `action` | TEXT NOT NULL | | `'extracted'` / `'auto_created'` / `'drafted'` / `'skipped'` / `'dedup_hit'` |
| `task_id` | INTEGER NULL | FK → `tasks.id` | If auto-created or accepted |
| `draft_id` | INTEGER NULL | FK → `task_drafts.id` | If routed to review |
| `confidence` | REAL NULL | | Extraction confidence |
| `details_json` | TEXT NULL | | Structured log (dedup reason, skip reason, etc.) |
| `created_at` | TEXT NOT NULL | | ISO-8601 (ADR-01) |

### Relationship to existing schema

```
emails (ADR-10)          ingest_documents
    │                         │
    │  ┌──────────────────────┘
    ▼  ▼
task_drafts ──review──> tasks
    │                     │
    └─── ingest_log ──────┘
              │
              └──> task_email_links (ADR-10, for C3)
```

- **`emails`** → reused as-is for C3. No schema changes.
- **`task_email_links`** → reused for C3 auto-created tasks. No schema changes.
- **`sync_state`** → not used by ingestion pipeline (sync_state is for external sync cursors; ingestion tracks state via `ingest_documents.status`).
- **`tasks`** → no schema changes. Optional: add `ingest_source` TEXT NULL column for traceability (alternative: rely on `ingest_log` FK).

**Decision: no new column on `tasks`.** Traceability is via `ingest_log.task_id` join. Keeps `tasks` table clean and avoids migration for a non-essential column.

---

## 6. LLM Integration Boundary

### What requires LLM

| Stage | LLM role | Deterministic fallback |
|-------|---------|----------------------|
| Extract | Parse unstructured text → structured task candidates | None (extraction is inherently NLP). Without LLM, items stay `pending` |
| Classify (partial) | Resolve ambiguous project/commitment hints | Heuristic: exact-match lookup in `projects`/`commitments` tables; NULL if no match |

### What is deterministic (no LLM)

| Stage | Logic |
|-------|-------|
| Classify (defaults) | Missing fields get defaults: priority=P2, estimate=30, status=NEXT |
| Deduplicate | String comparison, Levenshtein distance, `task_email_links` lookup |
| Route | Confidence threshold comparison, auto-create vs. draft vs. skip |
| Review UI | Display drafts, accept/edit/skip — pure CLI |

### LLM isolation

```
┌──────────────────────────────────────────────────────┐
│  executive_cli/                                       │
│                                                       │
│  ingest/                                              │
│  ├── pipeline.py       # orchestration (deterministic)│
│  ├── extractor.py      # LLM calls (isolated)        │
│  ├── classifier.py     # heuristic + LLM-assisted    │
│  ├── dedup.py          # deterministic                │
│  └── router.py         # deterministic                │
│                                                       │
│  llm/                                                 │
│  └── client.py         # LLM API wrapper (isolated)  │
└──────────────────────────────────────────────────────┘
```

- **`extractor.py`** is the ONLY module that calls the LLM.
- **`client.py`** wraps the LLM API (Anthropic, OpenAI, or local). Credentials from env vars (`LLM_API_KEY`). Never stored in DB or repo.
- **EA writer boundary (ADR-09):** The pipeline produces candidates. Only `router.py` calls the task-creation service (same code path as `task capture`). Pipeline code does NOT write to `tasks` directly — it calls `task_service.create_task()`.

### LLM API configuration

New settings in `settings` table:

| Key | Default | Purpose |
|-----|---------|---------|
| `ingest_auto_threshold` | `0.8` | Confidence threshold for auto-create |
| `ingest_llm_provider` | `anthropic` | LLM provider (`anthropic` / `openai` / `local`) |
| `ingest_llm_model` | `claude-sonnet-4-5-20250929` | Model ID for extraction |
| `ingest_llm_temperature` | `0` | Temperature for reproducibility |

Credentials: `LLM_API_KEY` env var (same pattern as CalDAV/IMAP credentials — env-only, per AGENTS.md section 5).

---

## 7. Privacy and Security

### Data sent to LLM by channel

| Channel | Sent to LLM | NOT sent |
|---------|------------|----------|
| C1 (meeting) | Full protocol text | File path, internal IDs |
| C2 (dialogue) | Full transcript text | Session metadata, internal IDs |
| C3 (email) | Subject + sender ONLY | Body (never stored), recipients, attachments, email ID, IMAP UID |

### PII considerations

- **C1/C2:** User's own notes/transcripts. User consents by running `execas ingest meeting/dialogue`. Content is sent to LLM API via HTTPS.
- **C3:** Only `emails.subject` + `emails.sender` are sent. This is metadata already stored locally (ADR-10). No new PII exposure beyond what `mail sync` already captured.
- **LLM output is NOT stored verbatim.** Only the structured candidates (title, status, priority, etc.) are stored in `task_drafts`. The raw LLM response is discarded after parsing.

### Security constraints

1. LLM API key in env var only (`LLM_API_KEY`). Never in DB, never in repo.
2. No email body sent to LLM. No email body stored. (ADR-10 line 236).
3. `ingest_documents` stores file paths, not file contents. Files must be local.
4. All `created_at`/`processed_at` via `dt_to_db()` (ADR-01).
5. R4 security guardrails (credential redaction, TLS, log discipline) apply to LLM calls too.

---

## 8. CLI Contract

### New commands (Phase 7)

```
Ingest:
- execas ingest meeting <file.md> [--title "Meeting title"]
  Processes meeting protocol, extracts task candidates.

- execas ingest dialogue <file.txt> [--title "Session summary"]
  Processes assistant dialogue transcript.

- execas ingest email [--since YYYY-MM-DD] [--limit N]
  Processes unprocessed emails from `emails` table.
  Default: all emails with no `ingest_documents` entry yet.

- execas ingest review [--limit N]
  Shows pending task drafts for human review.
  Interactive: accept/edit/skip per draft.

- execas ingest accept <draft_id>
  Accepts a specific draft (creates task).

- execas ingest skip <draft_id>
  Skips a specific draft (marks as skipped).

- execas ingest status
  Shows pipeline statistics: pending documents, pending drafts, auto-created count.
```

### Integration with existing commands

- `execas task list` — no change. Auto-created tasks appear like any other task.
- `execas task show <id>` — if task was auto-created from email, shows linked email (via `task_email_links`, already planned in R3).
- `execas review week` — auto-created tasks participate in weekly review scoring like any other task.

---

## 9. Implementation Phases

| Sub-phase | Scope | Depends on |
|-----------|-------|------------|
| **I1: Schema** | Migration: `ingest_documents`, `task_drafts`, `ingest_log` tables | R1 (ADR-10 schema) |
| **I2: Extract** | `extractor.py` + LLM client wrapper + C1 (meeting) channel | I1 |
| **I3: Pipeline core** | `classifier.py`, `dedup.py`, `router.py`, `pipeline.py` | I1 + I2 |
| **I4: CLI commands** | `ingest meeting/dialogue/email/review/accept/skip/status` | I3 |
| **I5: Email channel** | C3 integration with `emails` table + `task_email_links` | I4 + R3 (mail sync) |
| **I6: Tests** | Unit tests for each stage + integration test for full pipeline | I4 |

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM hallucinated tasks (false positives) | High | Medium (bad tasks in backlog) | Conservative threshold (0.8), draft review queue, low-confidence skip |
| LLM unavailable (API down) | Medium | Low (pipeline pauses) | Items stay `pending`, manual fallback via `task capture` |
| Dedup false negatives (duplicates created) | Medium | Low (user removes duplicates) | Multi-level dedup (exact + fuzzy + source-specific), dedup_flag in review |
| Meeting notes contain sensitive info | Low | Medium (PII sent to external LLM) | User-initiated only, HTTPS, configurable local LLM option |
| Email subject too terse for extraction | High | Low (low confidence → skip/draft) | Confidence scoring handles this; user reviews low-confidence drafts |
| High LLM API cost for large ingest batches | Medium | Low (cost, not data) | Batch size limits, configurable model (cheaper model for bulk) |
