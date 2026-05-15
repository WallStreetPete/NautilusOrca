"""yfinance market data source.

Notes:
    - Handles the MultiIndex column gotcha that bites everyone the first time.
    - Normalizes timestamps to UTC with microsecond precision.
    - Sets ``observed_at = as_of`` for daily bars: for EOD data the close *is*
      the disclosure, so the close timestamp is also when we learn the close.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from typing import Any

import polars as pl

from blackorca.data.contracts import BarAggregation
from blackorca.data.sources.base import MarketDataSource
from blackorca.logging import get_logger
from blackorca.metrics import BARS_INGESTED, DATA_FETCH_LATENCY

log = get_logger(__name__)


_INTERVAL_MAP = {
    BarAggregation.MINUTE: "1m",
    BarAggregation.FIVE_MINUTE: "5m",
    BarAggregation.FIFTEEN_MINUTE: "15m",
    BarAggregation.HOUR: "1h",
    BarAggregation.DAY: "1d",
    BarAggregation.WEEK: "1wk",
}


class YFinanceSource(MarketDataSource):
    name = "yfinance"

    def __init__(self, auto_adjust: bool = True, threads: bool = True) -> None:
        self.auto_adjust = auto_adjust
        self.threads = threads

    def is_available(self) -> bool:
        try:
            import yfinance  # noqa: F401
        except ImportError:
            return False
        return True

    def fetch_bars(
        self,
        symbols: list[str],
        start: date | datetime,
        end: date | datetime,
        aggregation: BarAggregation = BarAggregation.DAY,
    ) -> pl.DataFrame:
        import yfinance as yf  # local import — yfinance is heavy

        interval = _INTERVAL_MAP.get(aggregation)
        if interval is None:
            raise ValueError(f"yfinance does not support aggregation {aggregation}")

        t0 = time.perf_counter()
        log.info(
            "yfinance.fetch_bars.start",
            symbols=symbols,
            start=str(start),
            end=str(end),
            interval=interval,
        )

        raw = yf.download(
            tickers=" ".join(symbols),
            start=str(start),
            end=str(end),
            interval=interval,
            auto_adjust=self.auto_adjust,
            progress=False,
            group_by="ticker",
            threads=self.threads,
        )

        DATA_FETCH_LATENCY.labels(source="yfinance").observe(time.perf_counter() - t0)

        if raw is None or raw.empty:
            log.warning("yfinance.fetch_bars.empty", symbols=symbols)
            return MarketDataSource.empty_bar_frame()

        frames: list[pl.DataFrame] = []
        if len(symbols) == 1:
            df = self._single_symbol_to_polars(symbols[0], raw, aggregation)
            frames.append(df)
        else:
            for sym in symbols:
                if sym not in raw.columns.get_level_values(0).unique():
                    log.warning("yfinance.symbol_missing", symbol=sym)
                    continue
                sub = raw[sym].dropna(how="all")
                if sub.empty:
                    continue
                frames.append(self._single_symbol_to_polars(sym, sub, aggregation))

        if not frames:
            return MarketDataSource.empty_bar_frame()

        out = pl.concat(frames, how="vertical_relaxed").sort(["symbol", "as_of"])
        for sym in out["symbol"].unique().to_list():
            n = out.filter(pl.col("symbol") == sym).height
            BARS_INGESTED.labels(source="yfinance", instrument=sym).inc(n)
        log.info("yfinance.fetch_bars.done", rows=out.height)
        return out

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _single_symbol_to_polars(
        symbol: str, frame: Any, aggregation: BarAggregation
    ) -> pl.DataFrame:
        # Build a clean pandas frame first because yfinance returns pandas,
        # then convert. We're at an IO boundary — pandas is OK here.
        df = frame.reset_index()
        # The first column is either "Date" or "Datetime" depending on interval.
        ts_col = df.columns[0]
        df = df.rename(columns={ts_col: "as_of"})
        # Convert TZ -> UTC
        as_of = df["as_of"]
        if hasattr(as_of.dt, "tz") and as_of.dt.tz is not None:
            df["as_of"] = as_of.dt.tz_convert("UTC")
        else:
            df["as_of"] = as_of.dt.tz_localize("UTC")

        df["symbol"] = symbol.upper()
        df["aggregation"] = aggregation.value
        df["observed_at"] = df["as_of"]
        # yfinance recent versions have columns Open/High/Low/Close/Volume
        rename = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        df = df.rename(columns=rename)
        if "vwap" not in df.columns:
            df["vwap"] = None
        if "trade_count" not in df.columns:
            df["trade_count"] = None
        df = df[
            [
                "symbol",
                "aggregation",
                "as_of",
                "observed_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "vwap",
                "trade_count",
            ]
        ]
        out = pl.from_pandas(df)
        # Enforce the canonical schema dtypes
        out = out.with_columns(
            pl.col("as_of").cast(pl.Datetime("us", time_zone="UTC")),
            pl.col("observed_at").cast(pl.Datetime("us", time_zone="UTC")),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
            pl.col("vwap").cast(pl.Float64),
            pl.col("trade_count").cast(pl.Int64),
        )
        # Drop any all-NaN rows defensively
        return out.drop_nulls(subset=["open", "high", "low", "close"]).with_columns(
            pl.when(pl.col("as_of").dt.time() == datetime.min.time())
            .then(pl.col("as_of") + pl.duration(hours=20))  # 16:00 ET ≈ 20:00 UTC
            .otherwise(pl.col("as_of"))
            .alias("as_of")
        ).with_columns(pl.col("as_of").alias("observed_at"))


__all__ = ["YFinanceSource"]


# Force timezone import in case linter strips it
_TZ_UTC = UTC
