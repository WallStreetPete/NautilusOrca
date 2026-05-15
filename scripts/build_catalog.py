"""CLI: print catalog stats and list instruments."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def main(
    aggregation: str = typer.Option("1d", help="bar aggregation"),
) -> None:
    cat = Catalog()
    stats = cat.stats()
    console.print(stats)

    syms = cat.list_instruments(BarAggregation(aggregation))
    t = Table(title=f"Instruments ({aggregation})")
    t.add_column("Symbol")
    t.add_column("Bars")
    for s in syms:
        df = cat.read_bars(s, "1900-01-01", "2099-12-31", BarAggregation(aggregation))
        t.add_row(s, str(df.height))
    console.print(t)


if __name__ == "__main__":
    app()
