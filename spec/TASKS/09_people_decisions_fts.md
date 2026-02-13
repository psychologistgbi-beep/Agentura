# TASK 09 — People + Decisions with FTS5

## Goal
Add people and decisions tables, CLI commands, and FTS5 full-text search.

## Depends on
- TASK 02 (DB + migrations infra)

## In scope
- Alembic migration adding:
  - people(id, name, org, role, notes, created_at)
  - decisions(id, title, context, choice, consequences, created_at)
  - people_fts (FTS5, columns: name, org, role, notes; content=people)
  - decisions_fts (FTS5, columns: title, context, choice, consequences; content=decisions)
  - Triggers: AFTER INSERT/UPDATE/DELETE on people -> sync people_fts; same for decisions.
- CLI commands:
  - `execas people add --name "..." [--org "..."] [--role "..."] [--notes "..."]`
  - `execas people search "query"` — FTS MATCH with prefix support.
  - `execas decision add --title "..." --context "..." --choice "..." [--consequences "..."]`
  - `execas decision search "query"`

## Out of scope
- People/decisions linking to tasks.
- Edit/delete commands.

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (people, decision groups)
- apps/executive-cli/src/executive_cli/knowledge.py
- apps/executive-cli/src/executive_cli/models.py (People, Decision models)
- Alembic migration file

## Acceptance checks (TEST_PLAN: T14, T15)
- Add person, search by name and notes -> found.
- Add decision, search by title and consequences -> found.
- FTS index updates immediately.

## Rollback
- Revert commit + migration.
