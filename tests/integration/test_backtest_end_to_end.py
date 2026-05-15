"""End-to-end SMA cross backtest on synthetic deterministic data.

Why synthetic and not yfinance? Determinism. CI must produce the same numbers
every time, regardless of network or yfinance API changes. We seed a price
series we know is trending so the SMA cross fires predictably.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from blackorca.backtest.runner import run_backtest
from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BAR_SCHEMA, BarAggregation
from blackorca.risk.limits import RiskLimits
from blackorca.strategies.examples.sma_cross import SmaCross


def _synth_bars(symbol: str = "TEST", n: int = 300, seed: int = 7) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2022, 1, 3, 21, 0, tzinfo=UTC)
    rets = rng.normal(0.0005, 0.012, n)
    # Add a clear regime: first 100 down-drifting, next 200 up-trending
    rets[:100] -= 0.002
    rets[100:] += 0.001
    prices = 100.0 * np.exp(np.cumsum(rets))
    rows = []
    for i, p in enumerate(prices):
        ts = start + timedelta(days=i)
        o = float(p * (1 + rng.normal(0, 0.001)))
        h = float(max(o, p) * (1 + abs(rng.normal(0, 0.003))))
        lo = float(min(o, p) * (1 - abs(rng.normal(0, 0.003))))
        c = float(p)
        rows.append(
            {
                "symbol": symbol,
                "aggregation": BarAggregation.DAY.value,
                "as_of": ts,
                "observed_at": ts,
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": 1_000_000.0,
                "vwap": c,
                "trade_count": 1000,
            }
        )
    df = pl.from_dicts(rows).cast(BAR_SCHEMA)  # type: ignore[arg-type]
    # Make sure open/close are within high/low (some random pads may break that)
    df = df.with_columns(
        pl.max_horizontal("open", "close", "high").alias("high"),
        pl.min_horizontal("open", "close", "low").alias("low"),
    )
    return df


@pytest.mark.integration
def test_sma_cross_end_to_end_synthetic(tmp_path: Path) -> None:
    cat = Catalog(root=tmp_path / "catalog")
    bars = _synth_bars()
    n_written = cat.write_bars(bars)
    assert n_written == bars.height

    strat = SmaCross(symbol="TEST", fast=5, slow=20, target_weight=0.20)
    relaxed = RiskLimits(
        max_position_pct=0.50,
        max_gross_pct=2.0,
        max_net_pct=2.0,
        per_order_max_notional=10_000_000,
    )
    result = run_backtest(
        strat,
        symbols=["TEST"],
        start=bars["as_of"].min(),
        end=bars["as_of"].max(),
        capital=1_000_000,
        catalog=cat,
        risk_limits=relaxed,
    )

    # Sanity: produced an equity curve and the metrics dict has every key we
    # claim is computed.
    assert result.equity_curve.height >= 200
    for key in ("total_return", "sharpe", "max_drawdown", "n_trades"):
        assert key in result.metrics

    # The strategy traded at least once on the regime change.
    assert result.metrics["n_trades"] >= 2

    # Determinism: re-run and compare equity curves.
    strat2 = SmaCross(symbol="TEST", fast=5, slow=20, target_weight=0.20)
    result2 = run_backtest(
        strat2,
        symbols=["TEST"],
        start=bars["as_of"].min(),
        end=bars["as_of"].max(),
        capital=1_000_000,
        catalog=cat,
        risk_limits=relaxed,
    )
    assert math.isclose(
        result.metrics["final_equity"],
        result2.metrics["final_equity"],
        rel_tol=1e-9,
    )
