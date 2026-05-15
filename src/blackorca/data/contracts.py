"""Pydantic schemas for every data type that flows through the system.

Every contract carries two timestamps:

- ``as_of``       — the moment of the world the row describes. For an EOD bar
                    that is the close timestamp (e.g. 2024-03-15 16:00 ET).
                    For fundamentals it is the period-end date.
- ``observed_at`` — when *we* learned about the row. For a daily bar that is
                    the same as ``as_of`` because the close is the disclosure.
                    For fundamentals it is the filing timestamp (10-Q release).
                    For Taiwan monthly revenue, the 10th of the following month.

Strategies and ML features may only join on ``observed_at <= now``. The
``data.pit`` module enforces this.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BarAggregation(StrEnum):
    SECOND = "1s"
    MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"


class AssetClass(StrEnum):
    EQUITY = "equity"
    OPTION = "option"
    FUTURE = "future"
    CRYPTO = "crypto"
    FX = "fx"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class _PITModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    as_of: datetime
    observed_at: datetime

    @model_validator(mode="after")
    def _validate_observed_at(self) -> _PITModel:
        if self.observed_at < self.as_of:
            raise ValueError(
                f"observed_at ({self.observed_at}) must be >= as_of ({self.as_of}); "
                "we cannot observe something before it happened."
            )
        return self


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


class BarData(_PITModel):
    """OHLCV bar with explicit aggregation and PIT timestamps."""

    symbol: str
    aggregation: BarAggregation = BarAggregation.DAY
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    trade_count: int | None = None

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _check_ohlc(self) -> BarData:
        if self.low > self.high:
            raise ValueError(f"low ({self.low}) > high ({self.high}) on {self.symbol}")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"open out of [low, high] on {self.symbol} @ {self.as_of}")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"close out of [low, high] on {self.symbol} @ {self.as_of}")
        if self.volume < 0:
            raise ValueError(f"negative volume on {self.symbol}")
        return self


class TradeData(_PITModel):
    symbol: str
    price: float
    size: float
    aggressor_side: Side | None = None


class QuoteData(_PITModel):
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float

    @model_validator(mode="after")
    def _check_quote(self) -> QuoteData:
        if self.ask_price < self.bid_price:
            raise ValueError("ask < bid")
        return self


# ---------------------------------------------------------------------------
# Fundamentals & alt-data
# ---------------------------------------------------------------------------


class FundamentalData(_PITModel):
    """Period-end fundamentals. ``as_of`` is the period end; ``observed_at`` is
    the filing timestamp. This split is the single biggest source of look-ahead
    bias in equity research — keep them separate."""

    symbol: str
    field: str
    value: float
    period: str = Field(description="e.g. '2024Q1', '2024-FY'")
    source: str = "unknown"


class AltDataPoint(_PITModel):
    """Generic alt-data slot. Use ``kind`` to namespace
    (``twse_monthly_rev``, ``korea_export_10d``, etc.) and ``payload`` for
    source-native fields."""

    symbol: str | None
    kind: str
    value: float | None = None
    payload: dict[str, str | float | int | bool | None] = Field(default_factory=dict)
    source: str = "unknown"


class NewsItem(_PITModel):
    """A news event. ``as_of`` is the article timestamp; ``observed_at`` is
    when we ingested it (typically equal for live feeds)."""

    symbol: str | None = None
    headline: str
    body: str | None = None
    url: str | None = None
    sentiment: float | None = Field(default=None, ge=-1.0, le=1.0)
    classification: str | None = None
    source: str = "unknown"


# ---------------------------------------------------------------------------
# Polars schemas (canonical column types for catalog Parquet)
# ---------------------------------------------------------------------------

BAR_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8(),
    "aggregation": pl.Utf8(),
    "as_of": pl.Datetime("us", time_zone="UTC"),
    "observed_at": pl.Datetime("us", time_zone="UTC"),
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
    "volume": pl.Float64(),
    "vwap": pl.Float64(),
    "trade_count": pl.Int64(),
}

FUNDAMENTAL_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8(),
    "field": pl.Utf8(),
    "value": pl.Float64(),
    "period": pl.Utf8(),
    "as_of": pl.Datetime("us", time_zone="UTC"),
    "observed_at": pl.Datetime("us", time_zone="UTC"),
    "source": pl.Utf8(),
}

ALT_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8(),
    "kind": pl.Utf8(),
    "value": pl.Float64(),
    "payload_json": pl.Utf8(),
    "as_of": pl.Datetime("us", time_zone="UTC"),
    "observed_at": pl.Datetime("us", time_zone="UTC"),
    "source": pl.Utf8(),
}


def quantize_price(value: float, tick: float = 0.01) -> float:
    """Snap a price to a tick grid. Returns float (not Decimal) for performance.

    Use Decimal in the contract layer only when accounting accuracy matters
    (e.g. cash ledger), not for OHLCV or signal computation.
    """
    d = Decimal(str(value))
    t = Decimal(str(tick))
    return float((d / t).quantize(Decimal("1")) * t)


__all__ = [
    "ALT_SCHEMA",
    "BAR_SCHEMA",
    "FUNDAMENTAL_SCHEMA",
    "AltDataPoint",
    "AssetClass",
    "BarAggregation",
    "BarData",
    "FundamentalData",
    "NewsItem",
    "QuoteData",
    "Side",
    "TradeData",
    "quantize_price",
]
