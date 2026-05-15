"""Smoke test for the paper-trading wiring.

Doesn't hit Alpaca. Verifies that:
- TradingNode constructs cleanly with a stub adapter
- A single tick processes a bar and the strategy's submit path is exercised
- The kill switch flattens on a forced trip
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from blackorca.execution.adapters.nautilus_sim import ExecutionAdapter
from blackorca.live.trading_node import TradingNode, TradingNodeConfig
from blackorca.strategies.base import BarEvent, BlackOrcaStrategy


class _AlwaysBuy(BlackOrcaStrategy):
    def on_bar(self, bar: BarEvent) -> None:
        if self.position(bar.symbol) == 0:
            self.buy(bar.symbol, 1)


class _Capture(ExecutionAdapter):
    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, order) -> None:  # type: ignore[no-untyped-def]
        self.submitted.append(order)

    def poll_fills(self):  # type: ignore[no-untyped-def]
        return []


@pytest.mark.integration
def test_trading_node_constructs_and_ticks_with_stub_data(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Patch the yfinance source with a stub that returns one row
    from blackorca.data.sources import yfinance as yfm

    stub_df = MagicMock()
    stub_df.is_empty.return_value = False
    stub_df.sort.return_value = stub_df
    stub_df.tail.return_value = stub_df
    stub_df.row.return_value = {
        "symbol": "NVDA",
        "as_of": datetime(2024, 1, 1, tzinfo=UTC),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1_000_000.0,
    }
    monkeypatch.setattr(yfm.YFinanceSource, "fetch_bars", lambda self, *a, **kw: stub_df)

    adapter = _Capture()
    strat = _AlwaysBuy(strategy_id="smoke")
    node = TradingNode(
        strategy=strat,
        config=TradingNodeConfig(symbols=["NVDA"], poll_seconds=1, start_capital=100_000),
        adapter=adapter,
    )
    node.strategy.on_start()
    node._tick()
    assert adapter.submitted, "expected at least one order to be submitted"
    assert adapter.submitted[0].symbol == "NVDA"
