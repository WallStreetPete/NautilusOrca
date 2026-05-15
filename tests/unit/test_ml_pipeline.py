"""Tests for the ML feature plane.

Specifically: that features don't leak future information, that training
produces a usable model, and that inference loads it back.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from blackorca.data.contracts import BAR_SCHEMA, BarAggregation
from blackorca.ml.features.price import MomentumZ, RealizedVol, Returns
from blackorca.ml.inference import load_inference
from blackorca.ml.models import ModelRegistry
from blackorca.ml.pipelines import PITPipeline
from blackorca.ml.train import train_model


def _synth_bars(n: int = 600, seed: int = 1) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    t = datetime(2022, 1, 1, tzinfo=UTC)
    p = 100.0
    for i in range(n):
        r = float(rng.normal(0.0008, 0.018))
        p *= 1 + r
        o = p * (1 + rng.normal(0, 0.002))
        h = max(o, p) * (1 + abs(rng.normal(0, 0.003)))
        lo = min(o, p) * (1 - abs(rng.normal(0, 0.003)))
        rows.append(
            {
                "symbol": "X",
                "aggregation": BarAggregation.DAY.value,
                "as_of": t,
                "observed_at": t,
                "open": o,
                "high": h,
                "low": lo,
                "close": p,
                "volume": 1_000_000.0 + abs(rng.normal(0, 100_000)),
                "vwap": p,
                "trade_count": 1000,
            }
        )
        t += timedelta(days=1)
    return pl.from_dicts(rows).cast(BAR_SCHEMA)  # type: ignore[arg-type]


def test_returns_feature_has_no_lookahead() -> None:
    bars = _synth_bars(n=50)
    df = Returns(horizon=1).compute(bars)
    # The last row's ret_1d should equal (close[-1]/close[-2] - 1), not depend on close[-1] alone.
    last = df.row(-1, named=True)
    prev = df.row(-2, named=True)
    expected = last["close"] / prev["close"] - 1
    assert abs(last["ret_1d"] - expected) < 1e-12


def test_realized_vol_window_respected() -> None:
    bars = _synth_bars(n=100)
    df = RealizedVol(window=20).compute(bars)
    # Rows before window=20 should be null
    nulls = df["realvol_20d"].is_null().sum()
    assert nulls >= 20


def test_momentum_z_is_finite_on_late_rows() -> None:
    bars = _synth_bars(n=400)
    df = MomentumZ(horizon=20, z_window=120).compute(bars)
    tail = df.tail(20)["momz_20d"].drop_nulls().to_numpy()
    assert len(tail) > 0
    assert np.all(np.isfinite(tail))


def test_pipeline_build_supervised_no_leakage() -> None:
    bars = _synth_bars(n=400)
    pipeline = PITPipeline([Returns(1), Returns(5), RealizedVol(20)])
    sup, info = pipeline.build_supervised(bars, target_horizon=1)
    # The supervised frame must not contain any forward returns in feature columns
    assert "fwd_ret" in sup.columns
    # All feature columns are computable from the bar at or before each row's as_of
    assert info.feature_columns == ["ret_1d", "ret_5d", "realvol_20d"]
    # No nulls left after drop_nulls in build_supervised
    for c in [*info.feature_columns, "fwd_ret"]:
        assert sup[c].is_null().sum() == 0


def test_train_and_inference_roundtrip(tmp_path: Path) -> None:
    bars = _synth_bars(n=500)
    pipeline = PITPipeline([Returns(1), Returns(5), RealizedVol(20)])
    registry = ModelRegistry(root=tmp_path / "models")
    result = train_model(
        bars,
        pipeline,
        name="test",
        framework="ridge",  # ridge for speed in CI
        target_horizon=1,
        n_splits=3,
        registry=registry,
    )
    assert result.n_train_rows > 200
    handle = load_inference("test", result.version, registry=registry)
    features = pipeline.transform(bars).tail(10).drop_nulls()
    preds = handle.predict(features)
    assert preds.shape[0] == features.height
    assert np.all(np.isfinite(preds))
