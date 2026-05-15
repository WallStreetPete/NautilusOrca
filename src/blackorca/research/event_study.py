"""Event study framework.

Standard market-model CAR/AAR methodology:

1. For each (symbol, event_time), compute abnormal returns around the event
   over a window ``[-pre, +post]`` trading days.
2. Use a market-adjusted model: ``AR_t = R_t - R_market_t``. If a market
   series isn't provided, fall back to a constant-mean model.
3. Aggregate across events into AAR (average abnormal return) and CAAR
   (cumulative average abnormal return) curves, with t-stats.

This is intentionally simple — it's the workhorse, not a research paper.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import polars as pl
from scipy import stats


@dataclass(slots=True)
class EventStudyResult:
    aar: pl.DataFrame              # ["day", "aar", "t_stat", "p_value"]
    caar: pl.DataFrame             # ["day", "caar"]
    n_events: int
    pre_window: int
    post_window: int
    per_event: pl.DataFrame        # ["symbol", "event_date", "car"]


def run_event_study(
    prices: pl.DataFrame,
    events: pl.DataFrame,
    *,
    pre_window: int = 5,
    post_window: int = 20,
    price_col: str = "close",
    market_col: str | None = None,
    market_prices: pl.DataFrame | None = None,
) -> EventStudyResult:
    """Run a market-adjusted event study.

    Parameters
    ----------
    prices : DataFrame with columns ``[symbol, as_of, close]`` (sorted).
    events : DataFrame with columns ``[symbol, event_date]``.
    market_prices : optional benchmark DataFrame with columns ``[as_of, close]``.
    """
    if "symbol" not in prices.columns or "as_of" not in prices.columns:
        raise ValueError("prices needs [symbol, as_of, close]")
    if "symbol" not in events.columns or "event_date" not in events.columns:
        raise ValueError("events needs [symbol, event_date]")

    prices = prices.sort(["symbol", "as_of"]).with_columns(
        ret=pl.col(price_col).pct_change().over("symbol")
    )

    if market_prices is not None:
        market = market_prices.sort("as_of").with_columns(
            mkt_ret=pl.col(market_col or "close").pct_change()
        )
        prices = prices.join(market.select(["as_of", "mkt_ret"]), on="as_of", how="left")
        prices = prices.with_columns(ar=pl.col("ret") - pl.col("mkt_ret").fill_null(0.0))
    else:
        # constant-mean: subtract the per-symbol mean over the pre-event window
        prices = prices.with_columns(ar=pl.col("ret") - pl.col("ret").mean().over("symbol"))

    per_event_rows: list[dict[str, object]] = []
    ar_by_day: dict[int, list[float]] = {d: [] for d in range(-pre_window, post_window + 1)}

    for ev in events.iter_rows(named=True):
        sym = ev["symbol"]
        et = ev["event_date"]
        sub = prices.filter(pl.col("symbol") == sym).sort("as_of")
        if sub.is_empty():
            continue
        days = sub["as_of"].to_list()
        if et not in days:
            # use the first trading day >= event date
            candidates = [d for d in days if d >= et]
            if not candidates:
                continue
            et = candidates[0]
        idx = days.index(et)
        lo = idx - pre_window
        hi = idx + post_window
        if lo < 0 or hi >= len(days):
            continue
        ars = sub["ar"].to_list()[lo : hi + 1]
        for offset, ar in zip(range(-pre_window, post_window + 1), ars, strict=False):
            if ar is None or np.isnan(ar):
                continue
            ar_by_day[offset].append(float(ar))
        car = float(np.nansum(ars))
        per_event_rows.append({"symbol": sym, "event_date": et, "car": car})

    aar_rows = []
    caar_rows = []
    cum = 0.0
    for d in range(-pre_window, post_window + 1):
        sample = ar_by_day.get(d, [])
        if sample:
            mean = float(np.mean(sample))
            se = float(np.std(sample, ddof=1) / np.sqrt(len(sample))) if len(sample) > 1 else 0.0
            t = mean / se if se > 0 else 0.0
            p = float(2 * (1 - stats.norm.cdf(abs(t)))) if se > 0 else 1.0
        else:
            mean = 0.0
            t = 0.0
            p = 1.0
        cum += mean
        aar_rows.append({"day": d, "aar": mean, "t_stat": t, "p_value": p, "n": len(sample)})
        caar_rows.append({"day": d, "caar": cum})

    return EventStudyResult(
        aar=pl.from_dicts(aar_rows),
        caar=pl.from_dicts(caar_rows),
        n_events=len(per_event_rows),
        pre_window=pre_window,
        post_window=post_window,
        per_event=pl.from_dicts(per_event_rows) if per_event_rows else pl.DataFrame(),
    )


def _now_utc() -> datetime:

    return datetime.now(UTC)


__all__ = ["EventStudyResult", "run_event_study"]
