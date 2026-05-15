"""Point-in-time integrity tests.

These are the tests that protect us from the most common (and most expensive)
class of research bug: using data we wouldn't have known at decision time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from blackorca.data.contracts import BAR_SCHEMA, BarAggregation, BarData
from blackorca.data.pit import PITViolation, assert_no_lookahead, pit_asof_join

UTC = UTC


def _make_bar_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.from_dicts(rows).cast(BAR_SCHEMA)  # type: ignore[arg-type]


class TestBarContract:
    def test_well_formed_bar_passes(self) -> None:
        bar = BarData(
            symbol="nvda",
            as_of=datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
            observed_at=datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1_000_000,
        )
        assert bar.symbol == "NVDA"

    def test_observed_before_as_of_rejected(self) -> None:
        with pytest.raises(ValueError, match="observed_at"):
            BarData(
                symbol="NVDA",
                as_of=datetime(2024, 1, 2, tzinfo=UTC),
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                open=100, high=101, low=99, close=100.5, volume=1,
            )

    def test_ohlc_invariant_low_gt_high(self) -> None:
        with pytest.raises(ValueError, match="low"):
            BarData(
                symbol="X",
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                open=100, high=99, low=101, close=100, volume=1,
            )

    def test_close_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="close"):
            BarData(
                symbol="X",
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                open=100, high=101, low=99, close=102, volume=1,
            )


class TestAssertNoLookahead:
    def test_clean_frame_passes(self) -> None:
        df = _make_bar_frame(
            [
                {
                    "symbol": "X",
                    "aggregation": BarAggregation.DAY.value,
                    "as_of": datetime(2024, 1, 1, tzinfo=UTC),
                    "observed_at": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                    "volume": 1.0, "vwap": None, "trade_count": None,
                }
            ]
        )
        assert_no_lookahead(df, source="test")

    def test_observed_before_as_of_raises(self) -> None:
        df = _make_bar_frame(
            [
                {
                    "symbol": "X",
                    "aggregation": "1d",
                    "as_of": datetime(2024, 1, 2, tzinfo=UTC),
                    "observed_at": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                    "volume": 1.0, "vwap": None, "trade_count": None,
                }
            ]
        )
        with pytest.raises(PITViolation):
            assert_no_lookahead(df, source="test")

    def test_lag_threshold_enforced(self) -> None:
        df = _make_bar_frame(
            [
                {
                    "symbol": "X",
                    "aggregation": "1d",
                    "as_of": datetime(2024, 1, 1, tzinfo=UTC),
                    "observed_at": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=2),
                    "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                    "volume": 1.0, "vwap": None, "trade_count": None,
                }
            ]
        )
        with pytest.raises(PITViolation):
            assert_no_lookahead(df, source="test", max_observation_lag=timedelta(hours=1))

    def test_missing_columns_raises(self) -> None:
        df = pl.DataFrame({"as_of": [datetime(2024, 1, 1, tzinfo=UTC)]})
        with pytest.raises(PITViolation, match="observed_at"):
            assert_no_lookahead(df)

    def test_empty_frame_ok(self) -> None:
        df = pl.DataFrame(schema=BAR_SCHEMA)
        assert_no_lookahead(df)


class TestPitAsofJoin:
    def test_join_uses_observed_at_not_as_of(self) -> None:
        # Decision times (left)
        left = pl.DataFrame(
            {
                "as_of": [
                    datetime(2024, 1, 5, tzinfo=UTC),
                    datetime(2024, 1, 10, tzinfo=UTC),
                ]
            }
        )
        # Right has a row that *describes* Jan 1 but was *observed* on Jan 8.
        # At decision time Jan 5 we cannot use it; at Jan 10 we can.
        right = pl.DataFrame(
            {
                "as_of": [datetime(2024, 1, 1, tzinfo=UTC)],
                "observed_at": [datetime(2024, 1, 8, tzinfo=UTC)],
                "value": [42.0],
            }
        )

        out = pit_asof_join(left, right)
        assert out.height == 2
        # First left row (Jan 5) sees no right row yet
        assert out["value"][0] is None
        # Second left row (Jan 10) sees the value
        assert out["value"][1] == 42.0
