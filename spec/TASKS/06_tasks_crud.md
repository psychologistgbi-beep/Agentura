# TASK 06 — GTD Tasks CRUD + WAITING logic

## Goal
Implement task lifecycle: capture, list, move, done, waiting.

## Depends on
- TASK 02 (schema)
- TASK 05 (areas/projects/commitments for FK linking)

## In scope
- `execas task capture "title" --estimate 30 --priority P2 [--project X] [--area Y] [--commitment YC-1]`
  - Validates: estimate and priority required; project/area/commitment must exist if specified.
  - Default status: NEXT.
- `execas task list [--status NOW] [--project X] [--area Y] [--commitment YC-1]`
- `execas task move <id> --status <STATUS>`
  - Moving to WAITING without --on/--ping fails.
- `execas task done <id>` — shortcut for move to DONE.
- `execas task waiting <id> --on "Person" --ping "YYYY-MM-DD HH:MM"`
  - Sets status=WAITING, waiting_on, ping_at (interpreted as Europe/Moscow).

## Out of scope
- Planning algorithm (TASK 07).
- FTS on tasks.

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (task command group)
- apps/executive-cli/src/executive_cli/tasks.py (service layer)

## Acceptance checks (TEST_PLAN: T04, T05)
- Missing estimate/priority -> error.
- Capture returns task ID.
- WAITING requires waiting_on + ping_at.
- List filters work.

## Rollback
- Revert commit.
