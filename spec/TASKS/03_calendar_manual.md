# TASK 03 — Manual busy blocks (add/list) + merge logic

## Goal
Implement manual calendar busy management for the primary calendar:
- `execas busy add` to create busy blocks
- `execas busy list` to view busy blocks for a date
- deterministic merge of overlapping busy blocks (and documented policy for adjacency)
- all datetimes interpreted/output in Europe/Moscow

## In scope
- CLI commands:
  - `execas busy add --date YYYY-MM-DD --start HH:MM --end HH:MM --title "..."`
  - `execas busy list --date YYYY-MM-DD`
- Use the primary calendar (slug="primary") automatically.
- Merge logic:
  - Overlap => merge into a single interval deterministically.
  - Adjacency policy: choose one (merge or keep separate) and document it; implement consistently.
- Validation:
  - start < end
  - blocks within the planning day still allowed even if outside planning window (busy can be outside; planner later decides what to use).

## Out of scope
- CalDAV/MCP sync.
- Day planning algorithm.
- Task scheduling.

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (busy command group)
- apps/executive-cli/src/executive_cli/busy.py (service layer for busy blocks)
- apps/executive-cli/src/executive_cli/db.py (session helpers)
- apps/executive-cli/README.md (document busy commands + merge policy)
- tests/ (optional, but preferred): at least unit tests for merge logic

## Steps (commands)
1) Implement busy add:
   - parse date + start/end into tz-aware datetimes (Europe/Moscow)
   - insert busy block for primary calendar
2) Implement busy list:
   - query busy blocks overlapping that date range
   - present sorted by start_dt
3) Implement merge function:
   - input: list of intervals
   - output: merged list
   - deterministic title handling (e.g., keep earliest title or concat with "; " — must be documented)
4) Integrate merge into list output (and optionally into storage by normalizing on insert)

## Acceptance checks (map to TEST_PLAN)
- T06: add/list works and prints correct times
- T07: overlap merge works (10:00–11:00 + 10:30–12:00 => 10:00–12:00)
- T08: adjacency policy is consistent and documented
- All outputs in Europe/Moscow

## Rollback
- Revert commit; busy commands are isolated; DB remains compatible.
