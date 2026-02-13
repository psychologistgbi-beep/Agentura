# TASK 01 — Bootstrap executive-cli project

## Goal
Create the initial runnable CLI project under `apps/executive-cli/` with:
- Python project scaffolding (uv-based)
- Typer-based CLI entrypoint `execas`
- `execas init` command stub
- basic repo docs for setup/run
- no business logic yet (no DB schema required in this task)

## In scope
- Create `apps/executive-cli/` directory with a minimal Python package layout.
- Add dependencies:
  - typer
  - rich
  - (optional now or next task) sqlmodel/sqlalchemy, alembic
- Provide `execas --help` and `execas init --help`.
- `execas init` must exit successfully (even if it only prints "not implemented" for now).
- Add minimal README for the app explaining how to run.

## Out of scope
- Any SQLite schema, migrations, or data model.
- Planning algorithm.
- Yandex/MCP integrations.

## Files to touch (expected)
- apps/executive-cli/pyproject.toml
- apps/executive-cli/README.md
- apps/executive-cli/src/executive_cli/__init__.py
- apps/executive-cli/src/executive_cli/cli.py (or main.py)
- apps/executive-cli/src/executive_cli/__main__.py (if needed)
- (optional) apps/executive-cli/uv.lock

## Steps (commands)
1) Create directory:
   - `mkdir -p apps/executive-cli`
2) Initialize python project (uv):
   - `cd apps/executive-cli`
   - `uv init --package executive-cli` (or equivalent uv workflow)
3) Add deps:
   - `uv add typer rich`
4) Implement CLI skeleton:
   - `execas --help` lists subcommands.
   - `execas init` exists and runs (stub).
5) Document:
   - `apps/executive-cli/README.md` with install/run instructions.

## Acceptance checks
- From repo root:
  - `cd apps/executive-cli`
  - `uv run execas --help` works
  - `uv run execas init --help` works
  - `uv run execas init` exits with code 0 and prints a clear message

## Rollback
- Revert commit; no other tasks depend on this beyond having a runnable CLI.
