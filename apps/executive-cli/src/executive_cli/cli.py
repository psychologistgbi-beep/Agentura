import typer
from rich import print

from executive_cli.db import initialize_database

app = typer.Typer(
    name="execas",
    help="Executive Assistant CLI.",
    no_args_is_help=True,
)


@app.callback()
def root() -> None:
    """Executive Assistant CLI entrypoint."""


@app.command()
def init() -> None:
    """Initialize DB, run migrations, and seed defaults."""
    db_path = initialize_database()
    print(f"[green]Initialized database:[/green] {db_path}")


def main() -> None:
    app()
