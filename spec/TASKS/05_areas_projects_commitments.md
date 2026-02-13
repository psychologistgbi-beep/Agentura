# TASK 05 — Areas, Projects, Commitments CRUD

## Goal
Implement reference data management: areas, projects (linked to areas), and commitments with import.

## Depends on
- TASK 02 (schema)

## In scope
- `execas area add "name"` / `execas area list`
- `execas project add "name" [--area "area_name"]` / `execas project list`
- `execas commitment add --id YC-N --title "..." --metric "..." --due YYYY-MM-DD --difficulty DN [--notes "..."]`
- `execas commitment list`
- `execas commitment import` — seeds YC-1, YC-2, YC-3 from TECH_SPEC §6; idempotent (skip if exists).
- Duplicate name detection for areas/projects (UNIQUE constraint).

## Out of scope
- Task linking (TASK 06).
- Planning algorithm.

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (area, project, commitment groups)
- apps/executive-cli/src/executive_cli/areas.py
- apps/executive-cli/src/executive_cli/commitments.py

## Acceptance checks (TEST_PLAN: T03, ACCEPTANCE: E4, F1-F3)
- Create area "Work", project "Agentura" linked to "Work"; list shows them.
- `execas commitment import` creates YC-1..YC-3; second run is no-op.
- `execas commitment list` shows all commitments with fields.

## Rollback
- Revert commit; DB rows are local data.
