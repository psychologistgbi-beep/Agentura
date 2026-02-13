# TASK 12 — FTS tests + final integration check

## Goal
Automated tests for FTS5 and end-to-end CLI smoke test.

## Depends on
- TASK 09 (FTS5)
- TASK 08 (test infra)

## In scope
- pytest tests:
  - `test_people_fts`: add person, search by name/org/notes, verify results.
  - `test_decisions_fts`: add decision, search by title/consequences, verify.
  - `test_fts_update`: update person, search reflects new data.
  - `test_fts_prefix`: search "And*" matches "Andy".
- CLI smoke test (can be shell script or pytest subprocess):
  - `execas init` -> `config show` -> `area add` -> `project add` -> `task capture` -> `busy add` -> `plan day` -> verify exit codes.

## Out of scope
- Performance testing.
- MCP integration testing.

## Files to touch (expected)
- apps/executive-cli/tests/test_fts.py
- apps/executive-cli/tests/test_smoke.py (optional)

## Acceptance checks
- `uv run pytest` all green.
- FTS tests cover insert + search + update scenarios.

## Rollback
- Revert commit.
