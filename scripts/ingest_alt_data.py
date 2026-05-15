"""CLI: refresh alt-data sources into the catalog."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import typer
from rich.console import Console

from blackorca.data.catalog import Catalog
from blackorca.data.sources.alt.korea_customs import KoreaCustomsSource
from blackorca.data.sources.alt.news import NewsSource
from blackorca.data.sources.alt.taiwan_twse import TaiwanTwseSource
from blackorca.logging import configure_logging

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def main(
    source: Annotated[str, typer.Option(help="twse | korea | news | all")] = "all",
    days: Annotated[int, typer.Option()] = 365,
    symbols: Annotated[str, typer.Option(help="Comma-separated for news source")] = "NVDA,AMD,TSM",
) -> None:
    configure_logging(level="INFO", json=False)
    cat = Catalog()
    end = date.today()
    start = end - timedelta(days=days)

    sources = {"twse": TaiwanTwseSource(), "korea": KoreaCustomsSource(), "news": NewsSource(classify=False)}
    chosen = list(sources) if source == "all" else [source]

    for key in chosen:
        src = sources[key]
        if key == "news":
            df = src.fetch([s.strip() for s in symbols.split(",")], start, end)
        else:
            df = src.fetch(None, start, end)
        if df.is_empty():
            console.print(f"[yellow]{key}: no rows[/yellow]")
            continue
        n = cat.write_alt(df)
        console.print(f"[green]{key}[/green]: wrote {n} rows")


if __name__ == "__main__":
    app()
