import typer
from rich import print

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
    """Initialize application resources (stub)."""
    print("[yellow]execas init stub: not implemented yet.[/yellow]")


def main() -> None:
    app()
