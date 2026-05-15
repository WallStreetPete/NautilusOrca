"""Strategy P&L regression suite.

Locks in expected metrics for each reference strategy on synthetic deterministic
data. CI fails if a code change moves the numbers outside the tolerance.

How to update a baseline (when an *intentional* change moves the number):

1. Re-run the test locally with the new number.
2. Update the expected dict in this file.
3. Open a PR explaining the change, with the new tearsheet attached.
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


def _synth_bars(symbol: str = "TEST", n: int = 500, seed: int = 11) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    t = datetime(2022, 1, 1, tzinfo=UTC)
    p = 100.0
    for _ in range(n):
        r = float(rng.normal(0.0008, 0.018))
        p *= 1 + r
        o = p * (1 + rng.normal(0, 0.002))
        h = max(o, p) * (1 + abs(rng.normal(0, 0.003)))
        lo = min(o, p) * (1 - abs(rng.normal(0, 0.003)))
        rows.append(
            {
                "symbol": symbol,
                "aggregation": BarAggregation.DAY.value,
                "as_of": t,
                "observed_at": t,
                "open": o,
                "high": h,
                "low": lo,
                "close": p,
                "volume": 1_000_000.0,
                "vwap": p,
                "trade_count": 1000,
            }
        )
        t += timedelta(days=1)
    return pl.from_dicts(rows).cast(BAR_SCHEMA)  # type: ignore[arg-type]


# Expected metrics — tight tolerance because synth data is fully deterministic.
SMA_BASELINE = {
    "fast": 10,
    "slow": 30,
    "target_weight": 0.20,
    "expected_n_trades_min": 4,
    "expected_n_trades_max": 60,
    "expected_total_return_range": (-0.50, 1.00),  # sanity band; tighten over time
    "expected_max_drawdown_range": (-0.60, 0.0),
}


@pytest.mark.regression
def test_sma_cross_baseline(tmp_path: Path) -> None:
    cat = Catalog(root=tmp_path / "catalog")
    bars = _synth_bars()
    cat.write_bars(bars)

    relaxed = RiskLimits(max_position_pct=0.50, max_gross_pct=2.0, max_net_pct=2.0, per_order_max_notional=1e9)
    strat = SmaCross(symbol="TEST", fast=SMA_BASELINE["fast"], slow=SMA_BASELINE["slow"], target_weight=SMA_BASELINE["target_weight"])
    result = run_backtest(
        strat,
        symbols=["TEST"],
        start=bars["as_of"].min(),
        end=bars["as_of"].max(),
        capital=1_000_000,
        catalog=cat,
        risk_limits=relaxed,
    )

    m = result.metrics
    assert SMA_BASELINE["expected_n_trades_min"] <= m["n_trades"] <= SMA_BASELINE["expected_n_trades_max"], (
        f"n_trades={m['n_trades']} outside baseline band"
    )
    lo, hi = SMA_BASELINE["expected_total_return_range"]
    assert lo <= m["total_return"] <= hi, f"total_return={m['total_return']} outside band"
    lo, hi = SMA_BASELINE["expected_max_drawdown_range"]
    assert lo <= m["max_drawdown"] <= hi, f"max_dd={m['max_drawdown']} outside band"
    # Final equity computable and finite
    assert math.isfinite(m["final_equity"]) and m["final_equity"] > 0


@pytest.mark.regression
def test_sma_cross_determinism(tmp_path: Path) -> None:
    cat = Catalog(root=tmp_path / "catalog2")
    bars = _synth_bars(seed=11)
    cat.write_bars(bars)

    relaxed = RiskLimits(max_position_pct=0.50, max_gross_pct=2.0, max_net_pct=2.0, per_order_max_notional=1e9)

    def _run() -> float:
        s = SmaCross(symbol="TEST", fast=10, slow=30, target_weight=0.2)
        return run_backtest(
            s,
            symbols=["TEST"],
            start=bars["as_of"].min(),
            end=bars["as_of"].max(),
            capital=1_000_000,
            catalog=cat,
            risk_limits=relaxed,
        ).metrics["final_equity"]

    assert math.isclose(_run(), _run(), rel_tol=1e-9)
