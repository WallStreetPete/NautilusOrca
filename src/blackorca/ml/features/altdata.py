"""Features derived from alt-data sources.

Operates on the alt-data tables in the catalog. Returns features keyed by
``[symbol, as_of]``. Uses ``observed_at`` for the PIT join into prices.
"""

from __future__ import annotations

import polars as pl

from blackorca.data.pit import pit_asof_join


def taiwan_revenue_yoy(twse_df: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    """Add a ``twse_rev_yoy`` feature to prices.

    Expects ``twse_df`` with columns ``[symbol, as_of, observed_at, value]``
    where ``value`` is monthly revenue. Computes 12-month YoY % change,
    then joins on the observation date (~10th of the next month).
    """
    if twse_df.is_empty():
        return prices
    yoy = twse_df.sort(["symbol", "as_of"]).with_columns(
        (
            pl.col("value")
            / pl.col("value").shift(12).over("symbol")
            - 1
        ).alias("twse_rev_yoy")
    )
    return pit_asof_join(
        prices,
        yoy.select(["symbol", "observed_at", "twse_rev_yoy"]),
        left_time="as_of",
        right_time="observed_at",
        by="symbol",
    )


def korea_export_yoy(korea_df: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    if korea_df.is_empty():
        return prices
    yoy = korea_df.sort("as_of").with_columns(
        (pl.col("value") / pl.col("value").shift(36) - 1).alias("kr_semis_export_yoy")
    )
    return pit_asof_join(
        prices,
        yoy.select(["observed_at", "kr_semis_export_yoy"]),
        left_time="as_of",
        right_time="observed_at",
    )


def news_sentiment_daily(news_df: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    if news_df.is_empty():
        return prices
    daily = (
        news_df.with_columns(
            pl.col("observed_at").dt.truncate("1d").alias("obs_day")
        )
        .group_by(["symbol", "obs_day"])
        .agg(pl.col("sentiment").mean().alias("news_sentiment_d"))
        .rename({"obs_day": "observed_at"})
    )
    return pit_asof_join(
        prices,
        daily.select(["symbol", "observed_at", "news_sentiment_d"]),
        left_time="as_of",
        right_time="observed_at",
        by="symbol",
    )


__all__ = ["korea_export_yoy", "news_sentiment_daily", "taiwan_revenue_yoy"]
