"""Information coefficient (IC) analysis.

- ``compute_ic`` — pointwise Pearson or rank (Spearman) correlation between
  a factor and forward returns over a horizon.
- ``compute_ic_decay`` — IC as a function of horizon ∈ {1, 3, 5, 10, 20}.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy import stats


@dataclass(slots=True)
class ICResult:
    horizon: int
    mean_ic: float
    ic_std: float
    ic_ir: float            # IC information ratio = mean / std
    rank_mean_ic: float
    n_periods: int


def _forward_return(prices: pl.DataFrame, horizon: int, price_col: str = "close") -> pl.DataFrame:
    return prices.sort(["symbol", "as_of"]).with_columns(
        fwd_ret=(
            pl.col(price_col).shift(-horizon).over("symbol") / pl.col(price_col) - 1
        )
    )


def compute_ic(
    factor: pl.DataFrame,
    prices: pl.DataFrame,
    *,
    horizon: int = 1,
    factor_col: str = "value",
    price_col: str = "close",
) -> ICResult:
    """Cross-sectional IC computed per date, then averaged.

    Both frames need ``[symbol, as_of]`` plus their value columns.
    """
    px = _forward_return(prices, horizon, price_col)
    df = factor.join(px.select(["symbol", "as_of", "fwd_ret"]), on=["symbol", "as_of"])
    df = df.drop_nulls([factor_col, "fwd_ret"])

    daily: list[float] = []
    daily_rank: list[float] = []
    for _, day_df in df.group_by("as_of", maintain_order=True):
        if day_df.height < 5:
            continue
        f = day_df[factor_col].to_numpy()
        r = day_df["fwd_ret"].to_numpy()
        if np.std(f) > 0 and np.std(r) > 0:
            daily.append(float(np.corrcoef(f, r)[0, 1]))
            daily_rank.append(float(stats.spearmanr(f, r).correlation))

    if not daily:
        return ICResult(horizon=horizon, mean_ic=0.0, ic_std=0.0, ic_ir=0.0, rank_mean_ic=0.0, n_periods=0)

    mean = float(np.mean(daily))
    std = float(np.std(daily, ddof=1)) if len(daily) > 1 else 0.0
    ir = mean / std if std > 0 else 0.0
    return ICResult(
        horizon=horizon,
        mean_ic=mean,
        ic_std=std,
        ic_ir=ir,
        rank_mean_ic=float(np.mean(daily_rank)),
        n_periods=len(daily),
    )


def compute_ic_decay(
    factor: pl.DataFrame,
    prices: pl.DataFrame,
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10, 20),
    factor_col: str = "value",
    price_col: str = "close",
) -> pl.DataFrame:
    rows: list[dict[str, float | int]] = []
    for h in horizons:
        r = compute_ic(factor, prices, horizon=h, factor_col=factor_col, price_col=price_col)
        rows.append(
            {
                "horizon": r.horizon,
                "mean_ic": r.mean_ic,
                "ic_std": r.ic_std,
                "ic_ir": r.ic_ir,
                "rank_mean_ic": r.rank_mean_ic,
                "n_periods": r.n_periods,
            }
        )
    return pl.from_dicts(rows)


__all__ = ["ICResult", "compute_ic", "compute_ic_decay"]
