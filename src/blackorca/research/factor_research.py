"""Cross-sectional factor research.

Inputs: factor values + forward returns. Outputs: quintile portfolios, factor
returns, IC stats. Designed for daily cross-sections (rebalanced every day),
but works on any rebalance frequency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl


@dataclass(slots=True)
class FactorResult:
    quintile_returns: pl.DataFrame    # date x Q1..Q5
    long_short: pl.DataFrame          # date, ls_ret
    metrics: dict[str, float]


def _winsorize(s: pl.Series, p: float = 0.01) -> pl.Series:
    if s.len() == 0:
        return s
    lo = float(s.quantile(p) or 0)
    hi = float(s.quantile(1 - p) or 0)
    return s.clip(lo, hi)


def _zscore(s: pl.Series) -> pl.Series:
    mu = float(s.mean() or 0)
    sd = float(s.std() or 0)
    if sd == 0:
        return s - mu
    return (s - mu) / sd


def run_factor_study(
    factor: pl.DataFrame,
    prices: pl.DataFrame,
    *,
    horizon: int = 1,
    n_buckets: int = 5,
    factor_col: str = "value",
    price_col: str = "close",
    winsorize_p: float = 0.01,
) -> FactorResult:
    """Quintile-portfolio factor study.

    Parameters
    ----------
    factor : ``[symbol, as_of, <factor_col>]``
    prices : ``[symbol, as_of, <price_col>]``
    """
    px = prices.sort(["symbol", "as_of"]).with_columns(
        fwd_ret=(pl.col(price_col).shift(-horizon).over("symbol") / pl.col(price_col) - 1)
    )
    df = factor.join(px.select(["symbol", "as_of", "fwd_ret"]), on=["symbol", "as_of"])
    df = df.drop_nulls([factor_col, "fwd_ret"])

    quintile_rows: list[dict[str, float | object]] = []
    for date_val, day_df in df.group_by("as_of", maintain_order=True):
        if day_df.height < n_buckets:
            continue
        values = _winsorize(_zscore(day_df[factor_col]), winsorize_p)
        # Rank → bucket
        ranks = values.rank(method="dense") - 1
        buckets = (ranks / (ranks.max() or 1) * (n_buckets - 1)).cast(pl.Int64)
        scored = day_df.with_columns(bucket=buckets)
        row: dict[str, float | object] = {"as_of": date_val[0] if isinstance(date_val, tuple) else date_val}
        for b in range(n_buckets):
            sub = scored.filter(pl.col("bucket") == b)
            row[f"Q{b + 1}"] = float(sub["fwd_ret"].mean() or 0.0)
        quintile_rows.append(row)

    qdf = pl.from_dicts(quintile_rows) if quintile_rows else pl.DataFrame()
    ls_rows: list[dict[str, float | object]] = []
    if not qdf.is_empty() and f"Q{n_buckets}" in qdf.columns:
        for row in qdf.iter_rows(named=True):
            ls_rows.append(
                {"as_of": row["as_of"], "ls_ret": row[f"Q{n_buckets}"] - row["Q1"]}
            )
    ls = pl.from_dicts(ls_rows) if ls_rows else pl.DataFrame()

    metrics: dict[str, float] = {}
    if not ls.is_empty():
        r = ls["ls_ret"].to_numpy()
        metrics["mean_ls_ret"] = float(np.mean(r))
        metrics["t_stat_ls"] = (
            float(np.mean(r) / (np.std(r, ddof=1) / np.sqrt(len(r))))
            if len(r) > 1 and np.std(r) > 0
            else 0.0
        )
        metrics["sharpe_ls_daily"] = (
            float(np.mean(r) / np.std(r, ddof=1) * np.sqrt(252))
            if np.std(r) > 0
            else 0.0
        )
        metrics["n_periods"] = float(len(r))

    return FactorResult(quintile_returns=qdf, long_short=ls, metrics=metrics)


__all__ = ["FactorResult", "run_factor_study"]
