"""ML-signal-driven strategy.

Wraps a trained model from the registry. Each bar:

1. Build features for the bar's symbol from the last N bars of context.
2. Predict 1-day forward return.
3. Map prediction → target weight: ``weight = clip(alpha_scale * pred, -max_w, max_w)``.
4. Rebalance if the gap to current exceeds ``rebal_threshold_pct``.

The bar context is maintained in a ring buffer per symbol — strategies can't
hit the catalog on every bar without losing the research-to-live parity.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import polars as pl

from blackorca.data.contracts import BAR_SCHEMA, BarAggregation
from blackorca.ml.features.base import Feature
from blackorca.ml.features.microstructure import AdvRatio, IntradayRange, OvernightGap
from blackorca.ml.features.price import MomentumZ, RealizedVol, Returns
from blackorca.ml.inference import InferenceHandle, load_inference
from blackorca.strategies.base import BarEvent, BlackOrcaStrategy
from blackorca.strategies.registry import register_strategy


def default_feature_stack() -> list[Feature]:
    return [
        Returns(horizon=1),
        Returns(horizon=5),
        RealizedVol(window=20),
        MomentumZ(horizon=20, z_window=120),
        AdvRatio(window=20),
        OvernightGap(),
        IntradayRange(),
    ]


@register_strategy("ml_signal")
class MLSignal(BlackOrcaStrategy):
    """Trade according to a trained model's per-bar forecast."""

    def __init__(
        self,
        symbol: str,
        model_name: str,
        model_version: str,
        alpha_scale: float = 5.0,
        max_weight: float = 0.05,
        rebal_threshold_pct: float = 0.01,
        context_bars: int = 250,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.symbol = symbol.upper()
        self.alpha_scale = alpha_scale
        self.max_weight = max_weight
        self.rebal_threshold_pct = rebal_threshold_pct
        self.context_bars = context_bars
        self.handle: InferenceHandle = load_inference(model_name, model_version)
        self.features = default_feature_stack()
        self.context: deque[dict[str, Any]] = deque(maxlen=context_bars)

    def on_bar(self, bar: BarEvent) -> None:
        if bar.symbol != self.symbol:
            return
        self.context.append(
            {
                "symbol": bar.symbol,
                "aggregation": BarAggregation.DAY.value,
                "as_of": bar.as_of,
                "observed_at": bar.as_of,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": None,
                "trade_count": None,
            }
        )
        if len(self.context) < 60:
            return

        df = pl.from_dicts(list(self.context)).cast(BAR_SCHEMA)  # type: ignore[arg-type]
        for f in self.features:
            df = f.compute(df)
        # Take last row (today)
        row = df.tail(1)
        if any(row.get_column(c).is_null().any() for c in [f.output_column() for f in self.features]):
            return
        pred = float(self.handle.predict(row)[0])
        target_w = max(min(self.alpha_scale * pred, self.max_weight), -self.max_weight)

        equity = self.equity()
        target_qty = int(target_w * equity / bar.close)
        current = self.position(self.symbol)
        if abs(target_qty - current) * bar.close < self.rebal_threshold_pct * equity:
            return
        delta = target_qty - current
        if delta > 0:
            self.buy(self.symbol, delta)
        elif delta < 0:
            self.sell(self.symbol, -delta)
