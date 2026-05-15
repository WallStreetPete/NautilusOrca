"""Databento market data source.

Real implementation when ``DATABENTO_API_KEY`` is set; a no-op stub otherwise
so the codebase remains importable in dev. Supports ``XNAS.ITCH`` (equities)
and ``OPRA.PILLAR`` (options) schemas at minimum via the ``mbp-1`` /
``ohlcv-1d`` datasets.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import polars as pl

from blackorca.config import get_settings
from blackorca.data.contracts import BarAggregation
from blackorca.data.sources.base import MarketDataSource
from blackorca.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    pass

log = get_logger(__name__)


class DatabentoSource(MarketDataSource):
    name = "databento"

    def __init__(self, dataset: str = "XNAS.ITCH") -> None:
        self.dataset = dataset
        self._client: object | None = None

    def is_available(self) -> bool:
        return get_settings().databento_api_key is not None

    def _ensure_client(self) -> object:
        if self._client is not None:
            return self._client
        try:
            import databento as db
        except ImportError as e:
            raise RuntimeError(
                "databento not installed; `uv sync --extra databento` to enable."
            ) from e

        key = get_settings().databento_api_key
        if key is None:
            raise RuntimeError("DATABENTO_API_KEY not set")

        self._client = db.Historical(key=key.get_secret_value())
        return self._client

    def fetch_bars(
        self,
        symbols: list[str],
        start: date | datetime,
        end: date | datetime,
        aggregation: BarAggregation = BarAggregation.DAY,
    ) -> pl.DataFrame:
        if not self.is_available():
            log.warning("databento.unavailable", reason="DATABENTO_API_KEY missing")
            return MarketDataSource.empty_bar_frame()

        schema = {
            BarAggregation.DAY: "ohlcv-1d",
            BarAggregation.HOUR: "ohlcv-1h",
            BarAggregation.MINUTE: "ohlcv-1m",
        }.get(aggregation)
        if schema is None:
            raise ValueError(f"databento adapter does not support {aggregation}")

        client = self._ensure_client()
        try:
            response = client.timeseries.get_range(  # type: ignore[attr-defined]
                dataset=self.dataset,
                schema=schema,
                symbols=symbols,
                start=str(start),
                end=str(end),
            )
        except Exception as e:  # network / auth — surface but don't crash callers
            log.error("databento.fetch_failed", error=str(e))
            return MarketDataSource.empty_bar_frame()

        df_pandas = response.to_df()
        if df_pandas.empty:
            return MarketDataSource.empty_bar_frame()

        df_pandas = df_pandas.reset_index().rename(
            columns={"ts_event": "as_of", "symbol": "symbol"}
        )
        df_pandas["observed_at"] = df_pandas["as_of"]
        df_pandas["aggregation"] = aggregation.value
        df_pandas["vwap"] = df_pandas.get("vwap")
        df_pandas["trade_count"] = df_pandas.get("count")
        cols = [
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
        df_pandas = df_pandas[[c for c in cols if c in df_pandas.columns]]
        out = pl.from_pandas(df_pandas)
        return out.with_columns(
            pl.col("as_of").cast(pl.Datetime("us", time_zone="UTC")),
            pl.col("observed_at").cast(pl.Datetime("us", time_zone="UTC")),
        )


__all__ = ["DatabentoSource"]
