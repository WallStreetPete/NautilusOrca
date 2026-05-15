"""Microstructure-ish features computable from daily bars.

(True intraday microstructure features would need tick data — we use what
we have: volume profile, dollar volume, ADV ratios, gap stats.)
"""

from __future__ import annotations

import polars as pl

from blackorca.ml.features.base import Feature, FeatureSpec


class DollarVolume(Feature):
    def __init__(self) -> None:
        self.spec = FeatureSpec(name="dollar_volume", lookback_days=0, needs_columns=("close", "volume"))

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns((pl.col("close") * pl.col("volume")).alias(self.spec.name))


class AdvRatio(Feature):
    """Today's volume / mean(volume, N)."""

    def __init__(self, window: int = 20) -> None:
        self.window = window
        self.spec = FeatureSpec(
            name=f"adv_ratio_{window}d", lookback_days=window, needs_columns=("volume",)
        )

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.sort(["symbol", "as_of"]).with_columns(
            (
                pl.col("volume")
                / pl.col("volume").rolling_mean(window_size=self.window).over("symbol")
            ).alias(self.spec.name)
        )


class OvernightGap(Feature):
    """Today's open vs. prior close."""

    def __init__(self) -> None:
        self.spec = FeatureSpec(
            name="overnight_gap", lookback_days=1, needs_columns=("open", "close")
        )

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.sort(["symbol", "as_of"]).with_columns(
            (
                pl.col("open") / pl.col("close").shift(1).over("symbol") - 1
            ).alias(self.spec.name)
        )


class IntradayRange(Feature):
    """(high - low) / close as a daily volatility proxy."""

    def __init__(self) -> None:
        self.spec = FeatureSpec(
            name="intraday_range", lookback_days=0, needs_columns=("high", "low", "close")
        )

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias(self.spec.name)
        )


__all__ = ["AdvRatio", "DollarVolume", "IntradayRange", "OvernightGap"]
