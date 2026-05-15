"""Price-based features (returns, momentum, vol, mean-reversion)."""

from __future__ import annotations

import polars as pl

from blackorca.ml.features.base import Feature, FeatureSpec


class ForwardLookingError(ValueError):
    """Raised if a feature would access future data."""


class Returns(Feature):
    """Past-window simple returns."""

    def __init__(self, horizon: int = 1) -> None:
        self.horizon = horizon
        self.spec = FeatureSpec(
            name=f"ret_{horizon}d", lookback_days=horizon, needs_columns=("close",)
        )

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.sort(["symbol", "as_of"]).with_columns(
            (
                pl.col("close") / pl.col("close").shift(self.horizon).over("symbol") - 1
            ).alias(self.spec.name)
        )


class RealizedVol(Feature):
    """Annualized realized volatility from log-returns over a rolling window."""

    def __init__(self, window: int = 20, periods_per_year: int = 252) -> None:
        self.window = window
        self.periods_per_year = periods_per_year
        self.spec = FeatureSpec(
            name=f"realvol_{window}d", lookback_days=window, needs_columns=("close",)
        )

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.sort(["symbol", "as_of"]).with_columns(
            (
                (pl.col("close") / pl.col("close").shift(1).over("symbol")).log()
                .rolling_std(window_size=self.window)
                .over("symbol")
                * (self.periods_per_year ** 0.5)
            ).alias(self.spec.name)
        )


class MomentumZ(Feature):
    """Z-score of N-day return within its own rolling history."""

    def __init__(self, horizon: int = 20, z_window: int = 252) -> None:
        self.horizon = horizon
        self.z_window = z_window
        self.spec = FeatureSpec(name=f"momz_{horizon}d", lookback_days=horizon + z_window)

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        ret_col = f"_ret_{self.horizon}"
        df = df.sort(["symbol", "as_of"]).with_columns(
            (
                pl.col("close") / pl.col("close").shift(self.horizon).over("symbol") - 1
            ).alias(ret_col)
        )
        df = df.with_columns(
            (
                (
                    pl.col(ret_col)
                    - pl.col(ret_col).rolling_mean(window_size=self.z_window).over("symbol")
                )
                / pl.col(ret_col).rolling_std(window_size=self.z_window).over("symbol")
            ).alias(self.spec.name)
        )
        return df.drop(ret_col)


class MeanReversionZ(Feature):
    """Z-score of *negative* short-window return — high when oversold."""

    def __init__(self, horizon: int = 5, z_window: int = 60) -> None:
        self.horizon = horizon
        self.z_window = z_window
        self.spec = FeatureSpec(name=f"mrz_{horizon}d", lookback_days=horizon + z_window)

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        ret_col = f"_mr_ret_{self.horizon}"
        df = df.sort(["symbol", "as_of"]).with_columns(
            (
                -(pl.col("close") / pl.col("close").shift(self.horizon).over("symbol") - 1)
            ).alias(ret_col)
        )
        df = df.with_columns(
            (
                (
                    pl.col(ret_col)
                    - pl.col(ret_col).rolling_mean(window_size=self.z_window).over("symbol")
                )
                / pl.col(ret_col).rolling_std(window_size=self.z_window).over("symbol")
            ).alias(self.spec.name)
        )
        return df.drop(ret_col)


__all__ = ["ForwardLookingError", "MeanReversionZ", "MomentumZ", "RealizedVol", "Returns"]
