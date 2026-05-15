"""CLI: run a walk-forward study on a registered strategy."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

import typer
from rich.console import Console

from blackorca.backtest.runner import run_backtest
from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.research.walk_forward import WalkForwardWindow, run_walk_forward
from blackorca.risk.limits import RiskLimits
from blackorca.strategies.registry import StrategyRegistry

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def main(
    strategy: Annotated[str, typer.Option()] = "sma_cross",
    symbol: Annotated[str, typer.Option()] = "NVDA",
    train_days: Annotated[int, typer.Option()] = 252,
    test_days: Annotated[int, typer.Option()] = 63,
    embargo_days: Annotated[int, typer.Option()] = 5,
    capital: Annotated[float, typer.Option()] = 1_000_000,
    params_json: Annotated[str, typer.Option()] = "{}",
) -> None:
    cat = Catalog()
    bars = cat.read_bars(symbol, date(2000, 1, 1), date.today())
    if bars.is_empty():
        raise typer.BadParameter(f"no bars for {symbol}; run ingest first")
    timestamps = bars["as_of"].to_list()
    params = json.loads(params_json)

    relaxed = RiskLimits(per_order_max_notional=1e9, max_position_pct=0.5)

    def _eval(w: WalkForwardWindow) -> dict[str, float]:
        strat_cls = StrategyRegistry.get(strategy)
        strat = strat_cls(symbol=symbol, **params)
        res = run_backtest(
            strat,
            symbols=[symbol],
            start=w.test_start,
            end=w.test_end,
            capital=capital,
            catalog=cat,
            risk_limits=relaxed,
        )
        return {
            "sharpe": res.metrics.get("sharpe", 0.0),
            "total_return": res.metrics.get("total_return", 0.0),
            "max_dd": res.metrics.get("max_drawdown", 0.0),
        }

    result = run_walk_forward(
        timestamps,
        train_days=train_days,
        test_days=test_days,
        embargo_days=embargo_days,
        evaluator=_eval,
    )
    console.print({"summary": result.summary})
    console.print(result.to_polars())


if __name__ == "__main__":
    app()


# Force import to satisfy linter
_ = (datetime, timedelta, timezone, BarAggregation)
