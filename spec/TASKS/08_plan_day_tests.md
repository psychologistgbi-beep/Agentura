# TASK 08 — Unit tests for planner + busy merge

## Goal
Automated unit tests covering planning invariants, merge logic, and datetime conversions.

## Depends on
- TASK 07 (planner module)
- TASK 03 (merge logic)

## In scope
- pytest test suite under `apps/executive-cli/tests/`
- Tests:
  - `test_merge_intervals`: overlap, adjacency, no-overlap, empty list, single block.
  - `test_free_windows`: planning window minus busy = correct free slots.
  - `test_lunch_placement`: default, shifted, no room.
  - `test_task_ranking`: P1+commitment > P1 > P2.
  - `test_variant_fill`: minimal < realistic < aggressive fill %.
  - `test_tiny_gap_no_focus`: gap < min_focus_block -> buffer.
  - `test_determinism`: same input -> same output.
  - `test_datetime_roundtrip`: MSK -> DB TEXT -> MSK.

## Out of scope
- Integration/CLI tests (manual for MVP).

## Files to touch (expected)
- apps/executive-cli/tests/test_merge.py
- apps/executive-cli/tests/test_planner.py
- apps/executive-cli/tests/test_datetime.py
- apps/executive-cli/pyproject.toml (add pytest dev dep)

## Acceptance checks
- `uv run pytest` passes all tests.
- Coverage of merge + planner core functions >= 80%.

## Rollback
- Revert commit; tests are additive.
