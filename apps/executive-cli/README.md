# executive-cli

Executive Assistant CLI.

## Chosen structure

The app uses a minimal Typer setup:
- one Typer app in `src/executive_cli/cli.py`
- entrypoint `execas` from `[project.scripts]`
- optional module runner via `python -m executive_cli`

## Database

`execas` uses SQLite with Alembic migrations.

- default DB path: `apps/executive-cli/.data/execas.sqlite`
- override with env var: `EXECAS_DB_PATH=/absolute/or/relative/path.sqlite`

`execas init` is idempotent and does all bootstrap steps:
- creates DB directory if needed
- applies Alembic migrations
- seeds default settings
- creates primary calendar (`slug=primary`) if missing

## Run

From repository root:

```bash
cd apps/executive-cli
uv run execas --help
uv run execas init
```

## Verification

```bash
cd apps/executive-cli
rm -f .data/execas.sqlite && uv run execas init
uv run execas init
sqlite3 .data/execas.sqlite ".tables"
sqlite3 .data/execas.sqlite "SELECT key, value FROM settings ORDER BY key;"
sqlite3 .data/execas.sqlite "SELECT slug, COUNT(*) FROM calendars GROUP BY slug;"
```
