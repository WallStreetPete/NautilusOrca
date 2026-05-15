"""CLI: ingest market data into the catalog.

Examples:

    uv run python scripts/ingest_market_data.py --tickers NVDA,AMD --start 2020-01-01
    uv run python scripts/ingest_market_data.py --universe semis --years 5
    uv run python scripts/ingest_market_data.py --tickers NVDA --source databento
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import typer

from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.data.ingest import ingest_bars
from blackorca.data.sources.base import MarketDataSource
from blackorca.data.sources.databento import DatabentoSource
from blackorca.data.sources.yfinance import YFinanceSource
from blackorca.logging import configure_logging, get_logger
from blackorca.universe.semis import symbols as universe_symbols

app = typer.Typer(no_args_is_help=True, add_completion=False)
log = get_logger("ingest_market_data")


@app.command()
def main(
    tickers: Annotated[str, typer.Option(help="Comma-separated tickers")] = "",
    universe: Annotated[str, typer.Option(help="Named universe: 'semis'")] = "",
    years: Annotated[int, typer.Option(help="Years of history")] = 5,
    start: Annotated[str, typer.Option(help="ISO start date (overrides --years)")] = "",
    end: Annotated[str, typer.Option(help="ISO end date")] = "",
    source: Annotated[str, typer.Option(help="yfinance | databento")] = "yfinance",
    aggregation: Annotated[str, typer.Option(help="1d, 1h, 1m, ...")] = "1d",
) -> None:
    configure_logging(level="INFO", json=False)

    if not tickers and not universe:
        raise typer.BadParameter("must specify --tickers or --universe")

    if universe == "semis":
        syms = universe_symbols()
    else:
        syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]

    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else (end_d - timedelta(days=365 * years))

    src: MarketDataSource
    if source == "yfinance":
        src = YFinanceSource()
    elif source == "databento":
        src = DatabentoSource()
    else:
        raise typer.BadParameter(f"unknown source: {source}")

    if not src.is_available():
        log.error("source.unavailable", source=source)
        raise typer.Exit(code=2)

    catalog = Catalog()
    n = ingest_bars(
        src, catalog, syms, start_d, end_d, aggregation=BarAggregation(aggregation)
    )
    log.info("ingest.complete", symbols=syms, rows=n, source=source)


if __name__ == "__main__":
    app()
