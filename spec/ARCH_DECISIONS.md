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
