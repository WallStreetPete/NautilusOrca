"""Tests for the pre-trade risk system.

We assemble a minimal :class:`BacktestState`, then exercise each rejection
code path. These are the tests that protect us from a strategy bug
double-clicking the order button and blowing up the book.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from blackorca.backtest.runner import BacktestState
from blackorca.data.contracts import Side
from blackorca.risk.limits import RiskLimits
from blackorca.risk.pretrade import PreTradeRiskCheck
from blackorca.strategies.base import OrderRequest


def _state(cash: float = 1_000_000, **prices: float) -> BacktestState:
    s = BacktestState(cash=cash)
    s.last_price.update(prices)
    return s


def _order(symbol: str, qty: float, side: Side = Side.BUY) -> OrderRequest:
    return OrderRequest(strategy_id="t", symbol=symbol, side=side, quantity=qty)


def test_no_reference_price_rejected() -> None:
    chk = PreTradeRiskCheck(RiskLimits())
    decision = chk.check(_order("ABC", 100), _state(cash=1_000_000))
    assert not decision.approved
    assert decision.code == "NO_PRICE"


def test_per_order_notional_cap() -> None:
    chk = PreTradeRiskCheck(RiskLimits(per_order_max_notional=10_000))
    decision = chk.check(_order("NVDA", 100), _state(NVDA=500))  # $50k notional
    assert not decision.approved
    assert decision.code == "ORDER_NOTIONAL"


def test_position_cap_blocks_oversize() -> None:
    chk = PreTradeRiskCheck(RiskLimits(max_position_pct=0.01))
    # equity=1M, 1% cap = $10k. 100 shares @ $500 = $50k → block.
    decision = chk.check(_order("NVDA", 100), _state(cash=1_000_000, NVDA=500))
    assert not decision.approved
    assert decision.code == "POSITION_CAP"


def test_position_cap_allows_within_limit() -> None:
    chk = PreTradeRiskCheck(RiskLimits(max_position_pct=0.10))
    # equity=1M, 10% cap = $100k. 100 shares @ $500 = $50k → pass.
    decision = chk.check(_order("NVDA", 100), _state(cash=1_000_000, NVDA=500))
    assert decision.approved


def test_gross_exposure_cap() -> None:
    chk = PreTradeRiskCheck(RiskLimits(max_gross_pct=0.10))
    state = _state(cash=1_000_000, NVDA=500, AMD=200)
    state.positions["AMD"] = 400  # $80k existing
    decision = chk.check(_order("NVDA", 100), state)  # would add $50k
    assert not decision.approved
    assert decision.code in {"GROSS_CAP", "POSITION_CAP"}


def test_daily_loss_blocks() -> None:
    chk = PreTradeRiskCheck(RiskLimits(max_daily_loss_pct=0.01))
    state = _state(cash=900_000, NVDA=500)
    state.equity_hwm = 1_000_000  # we're down 10% from HWM
    decision = chk.check(_order("NVDA", 1), state)
    assert not decision.approved
    assert decision.code == "DAILY_LOSS"


def test_sector_cap() -> None:
    limits = RiskLimits(max_sector_pct=0.05)
    chk = PreTradeRiskCheck(limits, sector_map={"NVDA": "semis", "AMD": "semis"})
    state = _state(cash=1_000_000, NVDA=500, AMD=100)
    state.positions["AMD"] = 100  # $10k existing semis exposure
    decision = chk.check(_order("NVDA", 100), state)  # would add $50k → semis 60k > 5% cap
    assert not decision.approved
    assert decision.code in {"SECTOR_CAP", "POSITION_CAP"}


def test_share_cap() -> None:
    limits = RiskLimits(symbol_share_caps={"NVDA": 10})
    chk = PreTradeRiskCheck(limits)
    decision = chk.check(_order("NVDA", 11), _state(cash=1_000_000, NVDA=100))
    assert not decision.approved
    assert decision.code == "SHARE_CAP"


def test_sells_dont_create_phantom_buy_breach() -> None:
    """Reducing a position should never be blocked by the position cap."""
    chk = PreTradeRiskCheck(RiskLimits(max_position_pct=0.01))
    state = _state(cash=1_000_000, NVDA=500)
    state.positions["NVDA"] = 100  # already over the 1% cap
    decision = chk.check(_order("NVDA", 50, Side.SELL), state)
    assert decision.approved


@pytest.mark.parametrize("dd_pct, should_trip", [(0.04, False), (0.06, True)])
def test_kill_switch_drawdown(dd_pct: float, should_trip: bool) -> None:
    from datetime import datetime

    from blackorca.risk.kill_switch import KillSwitch

    ks = KillSwitch(max_drawdown_pct=0.05, max_daily_loss_pct=0.99)
    now = datetime(2024, 1, 1, tzinfo=UTC)
    equity = 1_000_000 * (1 - dd_pct)
    tripped = ks.evaluate(equity, 1_000_000, 1_000_000, now)
    assert tripped is should_trip
