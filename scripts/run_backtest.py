"""CLI: run a backtest from the registry."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from blackorca.backtest.analyzer import render_html_tearsheet
from blackorca.backtest.runner import run_backtest
from blackorca.config import get_settings
from blackorca.data.catalog import Catalog
from blackorca.logging import configure_logging
from blackorca.strategies.registry import StrategyRegistry

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def main(
    strategy: Annotated[str, typer.Option(help="Registered strategy name")] = "sma_cross",
    symbol: Annotated[str, typer.Option(help="Primary symbol")] = "NVDA",
    start: Annotated[str, typer.Option()] = "",
    end: Annotated[str, typer.Option()] = "",
    capital: Annotated[float, typer.Option()] = 0.0,
    params_json: Annotated[str, typer.Option(help="JSON dict for strategy kwargs")] = "{}",
    out: Annotated[str, typer.Option(help="HTML tearsheet output path")] = "data/reports/last.html",
) -> None:
    configure_logging(level="INFO", json=False)
    settings = get_settings()
    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else (end_d - timedelta(days=365 * 4))
    cap = capital if capital > 0 else settings.backtest.default_capital
    params = json.loads(params_json)
    strategy_cls = StrategyRegistry.get(strategy)
    strat = strategy_cls(symbol=symbol, **params)

    cat = Catalog()
    result = run_backtest(
        strat,
        symbols=[symbol],
        start=start_d,
        end=end_d,
        capital=cap,
        catalog=cat,
    )

    console.print({"config": result.config, "metrics": result.metrics})
    out_path = render_html_tearsheet(
        result.metrics, result.equity_curve, title=f"{strategy} on {symbol}", out_path=out
    )
    console.print(f"[green]Wrote tearsheet to[/green] {Path(out_path).resolve()}")


if __name__ == "__main__":
    app()
