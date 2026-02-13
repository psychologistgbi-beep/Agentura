# TASK 07 — Deterministic plan day (3 variants)

## Goal
Implement `execas plan day --date YYYY-MM-DD --variant minimal|realistic|aggressive` producing time-blocked schedule stored in DB.

## Depends on
- TASK 03 (busy blocks + merge logic)
- TASK 04 (config: planning window, lunch, buffer, min_focus_block)
- TASK 06 (tasks to schedule)

## In scope
- Planning algorithm per TECH_SPEC §11 and ADR-06:
  1. Build free windows from planning_window minus merged busy blocks.
  2. Reserve lunch (shift if conflict).
  3. Rank tasks by deterministic score (priority + commitment + due urgency).
  4. Fill variant-specific % of free time.
  5. Insert buffer_min between blocks.
- Store result: day_plans + time_blocks tables.
- Upsert policy (ADR-05): replace previous (date, variant) plan.
- Output: formatted time-block schedule with block types (busy, focus, admin, lunch, buffer).
- Rationale output: which tasks chosen, what didn't fit.

## Out of scope
- LLM-based suggestions.
- Task splitting.

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/planner.py (core algorithm)
- apps/executive-cli/src/executive_cli/cli.py (plan command group)
- Alembic migration for UNIQUE constraint on day_plans(date, variant) if not yet present.

## Acceptance checks (TEST_PLAN: T09, T10, T11, T12, T13)
- T09: minimal variant produces valid schedule with busy, lunch, focus blocks.
- T10: 25-min gap not used for focus.
- T11: lunch moves when default slot busy.
- T12: two runs produce identical output.
- T13: full day busy -> no focus blocks, suggestions output.

## Rollback
- Revert commit; planner is isolated module.
