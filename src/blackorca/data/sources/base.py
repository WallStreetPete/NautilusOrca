"""Abstract data source interfaces.

Concrete implementations live alongside (e.g. ``yfinance.py``,
``databento.py``). All public methods return Polars DataFrames matching the
canonical schemas in :mod:`blackorca.data.contracts`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Protocol

import polars as pl

from blackorca.data.contracts import BAR_SCHEMA, BarAggregation


class MarketDataSource(ABC):
    """Source of OHLCV market data."""

    name: str = "abstract"

    @abstractmethod
    def fetch_bars(
        self,
        symbols: list[str],
        start: date | datetime,
        end: date | datetime,
        aggregation: BarAggregation = BarAggregation.DAY,
    ) -> pl.DataFrame:
        """Fetch bars. Returns a frame matching :data:`BAR_SCHEMA`."""

    def is_available(self) -> bool:
        """Whether the source can be used at runtime (e.g. credentials set)."""
        return True

    @staticmethod
    def empty_bar_frame() -> pl.DataFrame:
        return pl.DataFrame(schema=BAR_SCHEMA)


class AltDataSource(ABC):
    """Source of non-price data (fundamentals, alt-data, news)."""

    name: str = "abstract"
    kind: str = "generic"

    @abstractmethod
    def fetch(
        self,
        symbols: list[str] | None,
        start: date | datetime,
        end: date | datetime,
    ) -> pl.DataFrame:
        """Fetch rows. Returns a frame with at minimum
        ``[symbol, kind, value, as_of, observed_at, source]`` columns."""

    def is_available(self) -> bool:
        return True


class SupportsCalendar(Protocol):
    """Optional capability for sources that know the trading calendar."""

    def is_trading_day(self, d: date) -> bool: ...


__all__ = ["AltDataSource", "MarketDataSource", "SupportsCalendar"]
