# executive-cli

CLI for the Executive Assistant MVP.

## Requirements
- Python (managed by uv)
- sqlite3 available in PATH

## Install / Run
cd apps/executive-cli
uv run execas --help
uv run execas init

## Database location
By default, the SQLite database is created at:
apps/executive-cli/.data/execas.sqlite

You can override the path with:
EXECAS_DB_PATH=/absolute/path/to/execas.sqlite

Example:
cd apps/executive-cli
EXECAS_DB_PATH="$PWD/.data/execas.sqlite" uv run execas init

## Verification
cd apps/executive-cli
rm -f .data/execas.sqlite
uv run execas init
sqlite3 .data/execas.sqlite ".tables"
sqlite3 .data/execas.sqlite "SELECT key, value FROM settings ORDER BY key;"
sqlite3 .data/execas.sqlite "SELECT slug, COUNT(*) FROM calendars GROUP BY slug;"
