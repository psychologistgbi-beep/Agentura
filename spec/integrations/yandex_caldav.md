# Integration Plan: Yandex Calendar via CalDAV

**Status:** Draft

**Date:** 2026-02-14

**Related ADR:** ADR-10

---

## 1. Overview

- **Service:** Yandex Calendar (CalDAV endpoint)
- **Protocol:** CalDAV (WebDAV REPORT/PROPFIND)
- **Direction:** Read-only (external -> local)
- **Trigger:** Scheduled hourly pull on laptop (`execas calendar sync` by scheduler)

Goal: keep local `busy_blocks` aligned with external calendar to improve day planning while preserving manual fallback and deterministic behavior.

## 2. Sync strategy

### 2.1 Pull model

- Run once per hour.
- Use bounded lookback/lookahead window:
  - lookback: last 14 days (catch late edits/cancellations)
  - lookahead: next 90 days (planning horizon)
- Sync is pull-only for MVP. No outbound writes.

### 2.2 Incremental model

- Store per-source watermark in a sync cursor table (`sync_state` in ADR-10):
  - `source = yandex_caldav`
  - `cursor_kind = sync_token` if server supports WebDAV sync-collection (RFC 6578)
  - fallback `cursor_kind = ctag` using collection `getctag` property
- On each run:
  1. Load cursor.
  2. Query deltas since cursor.
  3. Upsert changed events and tombstone deletions.
  4. Advance cursor only after successful transaction commit.

### 2.3 Identity and dedup

- Canonical identity for external event row:
  - `source = yandex_caldav`
  - `external_id = UID[:RECURRENCE-ID]`
- Store event provenance on `busy_blocks` (ADR-10):
  - `source`, `external_id`, `external_etag`, `external_modified_at`, `is_deleted`
- Unique index for externally-synced rows:
  - `(calendar_id, source, external_id)`
- Dedup rules:
  - Same identity + same etag => skip write.
  - Same identity + new etag => update row.
  - External cancellation/delete => set `is_deleted=1` (soft delete for audit).
- Manual blocks remain separate (`source = manual`) and are never overwritten by CalDAV sync.

## 3. Data mapping

Inbound mapping into `busy_blocks`:

- `DTSTART` -> `start_dt`
- `DTEND` (or DTSTART + DURATION) -> `end_dt`
- `SUMMARY` -> `title`
- `UID/RECURRENCE-ID` -> `external_id`
- `ETag` -> `external_etag`
- `LAST-MODIFIED` -> `external_modified_at`
- connector constant -> `source = yandex_caldav`

All values are persisted by EA as single writer (ADR-09).

## 4. Timezone and offsets policy

- Internal invariant: datetimes stored as ISO-8601 with explicit offset (ADR-01).
- Input handling:
  - If CalDAV returns UTC (`Z`), convert to offset-aware datetime and store as UTC offset.
  - If CalDAV returns tz-aware local time (`TZID`), resolve through `zoneinfo` and persist offset-aware instant.
  - Floating timestamps (no zone) are interpreted in calendar timezone from CalDAV metadata, then converted to offset-aware datetime.
- Display/output timezone remains `settings.timezone` (ADR-02).
- Cross-timezone safety:
  - comparisons in sync engine are done in UTC instants,
  - display conversion happens at read/render only.

## 5. Failure modes and recovery

| Failure | Detection | Impact | Mitigation |
|---|---|---|---|
| Endpoint unavailable | timeout / DNS error | no refresh | keep prior data, print warning, retry next hourly run |
| Invalid credentials | 401/403 | no refresh | fail fast, redacted error, instruct credential refresh |
| Partial response | parsing/report inconsistency | stale subset | transaction rollback + retry with same cursor |
| Cursor invalidated | 409 / token mismatch | incremental fails | full resync inside bounded window, then replace cursor |
| Rate limit | 429 | delayed sync | exponential backoff with jitter, preserve cursor |

## 6. Manual fallback

If sync is unavailable, user keeps workflow via CLI:

1. `uv run execas busy add --date <YYYY-MM-DD> --start <HH:MM> --end <HH:MM> --title "..."`
2. `uv run execas busy list --date <YYYY-MM-DD>`

## 7. Security constraints

- Read-only calendar scope only.
- Credentials live in env vars or local secure storage, never in SQLite and never in repo.
- No sensitive payloads in logs (no full event bodies, no secrets).
- Connector can be disabled without breaking core CLI.
