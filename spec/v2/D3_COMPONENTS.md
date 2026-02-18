# D3. COMPONENTS — Компоненты и контракты

## 1. Карта компонентов

```
n8n (external)
  │ HTTP POST / shell exec
  ▼
CLI (cli.py)
  │ function calls
  ├──→ ingest_service.py ──→ extractor.py ──→ llm_gateway.py
  │         │                                      │
  │         ├──→ classifier.py                     ├──→ Ollama (localhost:11434)
  │         ├──→ dedup.py                          ├──→ Anthropic API
  │         └──→ router.py ──→ task_service.py     └──→ local heuristic
  │
  ├──→ planner.py
  ├──→ connectors/imap.py ──→ Yandex IMAP
  └──→ connectors/caldav.py ──→ Yandex CalDAV
         │
         ▼
     SQLite (models.py)
```

## 2. Компоненты

### CLI (`cli.py`)

**Ответственность:** Typer-команды, parse args, вызов domain service, print output. Zero business logic.

**Команды:**

| Команда | Вызывает | Output |
|---------|----------|--------|
| `execas init` | `db.init_db()` | "Initialized database: {path}" |
| `execas task capture <title> [opts]` | `task_service.create_task_record()` | "Created task id={id}" |
| `execas ingest email [--since] [--limit]` | `ingest_service.ingest_emails()` | summary (processed, auto, drafted, skipped) |
| `execas daily [--date] [--variant]` | `ingest_service.ingest_emails()` + `planner.plan_day()` | summary + plan |
| `execas approve batch [--limit]` | interactive loop: `approve_draft()` / `reject_draft()` | per-item result + totals |
| `execas dash [--since]` | `metrics.pipeline_stats()` + `metrics.llm_stats()` | dashboard text |

---

### LLM Gateway (`llm_gateway.py`)

**Contract:**

```python
def call_llm(
    session: Session | None,
    *,
    prompt: str,
    provider: str | None = None,     # None → auto fallback
    model: str | None = None,
    temperature: float = 0.0,
    correlation_id: str | None = None,
    now_iso: str | None = None,
    parse_json: bool = False,
) -> LLMResponse:
    """Call LLM. Raises LLMGatewayError if all providers fail."""

@dataclass(frozen=True)
class LLMResponse:
    text: str
    parsed: dict | list | None = None
    provider: str = ""
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
```

**Request example (Ollama):**
```json
POST http://localhost:11434/api/generate
{
  "model": "qwen2.5:7b",
  "prompt": "Extract actionable GTD tasks...",
  "stream": false,
  "options": {"temperature": 0.0}
}
```

**Response example:**
```json
{
  "text": "[{\"title\": \"Sign contract\", \"confidence\": 0.92, ...}]",
  "parsed": [{"title": "Sign contract", "confidence": 0.92, "suggested_status": "NEXT", "suggested_priority": "P1", "estimate_min": 30}],
  "provider": "ollama",
  "model": "qwen2.5:7b",
  "prompt_tokens": 156,
  "completion_tokens": 89,
  "latency_ms": 1240
}
```

**Errors:** `LLMGatewayError("All providers failed: ollama=timeout, anthropic=no_key, local=parse_error")`

---

### Ingest Service (`ingest_service.py`)

**Contract:**

```python
def ingest_emails(
    session: Session,
    *,
    since: date | None,
    limit: int = 50,
    now_iso: str,
) -> IngestSummary:
    """Process unprocessed emails. Returns summary counts."""

def ingest_file(
    session: Session,
    *,
    path: str,
    channel: str,           # "meeting_notes" | "assistant_dialogue"
    title: str | None,
    now_iso: str,
) -> IngestSummary:
    """Process a text file (meeting notes or dialogue). Returns summary."""

@dataclass(frozen=True)
class IngestSummary:
    processed: int = 0
    failed: int = 0
    extracted: int = 0
    auto_created: int = 0
    drafted: int = 0
    skipped: int = 0
```

**Внутренний flow:** `ingest_one_email(session, email_id, now_iso)`:
1. `extractor.extract(session, text, channel, context)` → `list[ExtractedCandidate]`
2. `classifier.classify(session, candidates, channel, doc_id, email_id)` → `list[ClassifiedCandidate]`
3. Per candidate: `dedup.check(session, title, doc_id, email_id)` → `DedupDecision`
4. Per candidate: `router.route(session, candidate, dedup, threshold, now_iso)` → `RouteOutcome`
5. Update IngestDocument status

---

### Task Service (`task_service.py`)

```python
def create_task_record(
    session: Session,
    *,
    title: str,
    status: TaskStatus,
    priority: TaskPriority,
    estimate_min: int,
    due_date: date | None = None,
    now_iso: str,
    area_id: int | None = None,
    project_id: int | None = None,
    commitment_id: str | None = None,
    waiting_on: str | None = None,
    ping_at: str | None = None,
    from_email_id: int | None = None,
) -> Task:
    """Create task + optional email link. Raises TaskServiceError."""
```

---

### Planner (`planner.py`)

```python
def plan_day(
    session: Session,
    *,
    date: date,
    variant: str = "realistic",  # minimal | realistic | aggressive
    now_iso: str,
) -> DayPlanResult:
    """Build day plan: merge busy blocks, rank tasks, fill time slots."""

@dataclass
class DayPlanResult:
    plan_id: int
    blocks: list[ScheduledBlock]
    total_focus_min: int
    tasks_scheduled: int
```

---

### Connectors

**IMAP (`connectors/imap.py`):**
```python
class ImapConnector:
    def fetch_headers(self, *, since_uid: int | None) -> MailSyncBatch:
        """Fetch new email headers from IMAP. Raises MailConnectorError."""
```

**CalDAV (`connectors/caldav.py`):**
```python
class CalDavConnector:
    def fetch_events(self, *, since: date, until: date) -> list[CalendarEvent]:
        """Fetch calendar events. Raises CalDavConnectorError."""
```

---

### Approval (через task_drafts)

ASSUMPTION: MVP не имеет отдельного ApprovalRequest. Используется `task_drafts`:

```python
def approve_draft(session: Session, *, draft_id: int, now_iso: str) -> Task:
    """Approve draft → create task. Raises if not pending."""

def reject_draft(session: Session, *, draft_id: int, now_iso: str) -> None:
    """Reject draft. Sets status='skipped'."""

def list_pending_drafts(session: Session, *, limit: int = 50) -> list[TaskDraft]:
    """Return pending drafts ordered by confidence desc."""
```

## Open questions

1. Нужен ли `execas ingest meeting` и `execas ingest dialogue` как отдельные команды, или достаточно `execas ingest file --channel meeting_notes <path>`?
