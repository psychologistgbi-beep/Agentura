# executive-cli

Bootstrap CLI app for Executive Assistant.

## Chosen structure

The simplest setup is used:
- one Typer app in `src/executive_cli/cli.py`
- entrypoint `execas` from `[project.scripts]`
- optional module runner via `python -m executive_cli`

## Run

From repository root:

```bash
cd apps/executive-cli
uv run execas --help
uv run execas init --help
uv run execas init
```

Expected `init` output is a clear stub message and exit code `0`.
