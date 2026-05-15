"""Top-level CLI: ``blackorca <subcommand>``.

Subcommands are wired sparsely here — most work happens in ``scripts/`` so they
can be called directly. The CLI is a convenience entrypoint for ops.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from blackorca import __version__
from blackorca.config import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Black Orca Capital CLI")
console = Console()


@app.command()
def version() -> None:
    """Print the installed package version."""
    console.print(f"blackorca [bold]{__version__}[/bold]")


@app.command()
def config() -> None:
    """Print the resolved configuration (secrets masked)."""
    s = get_settings()
    t = Table(title=f"BlackOrca config (profile={s.profile})")
    t.add_column("Key")
    t.add_column("Value")
    data = s.model_dump(mode="json", by_alias=True)
    for k, v in data.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                t.add_row(f"{k}.{sk}", str(sv))
        else:
            t.add_row(k, "***" if k.endswith("_key") or k.endswith("_secret") else str(v))
    console.print(t)


@app.command()
def health() -> None:
    """Quick environment sanity check."""
    s = get_settings()
    ok = True
    rows: list[tuple[str, str]] = []
    rows.append(("profile", s.profile))
    rows.append(("anthropic", "set" if s.anthropic_api_key else "MISSING"))
    rows.append(("databento", "set" if s.databento_api_key else "missing (optional)"))
    rows.append(("alpaca", "set" if s.alpaca_api_key else "missing (optional)"))
    rows.append(("catalog_path", str(s.catalog_path)))
    if not s.anthropic_api_key:
        ok = False
    t = Table(title="Health")
    t.add_column("Component")
    t.add_column("Status")
    for k, v in rows:
        t.add_row(k, v)
    console.print(t)
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":
    app()
