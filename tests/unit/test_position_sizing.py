"""Position sizing helpers on the strategy base class."""

from __future__ import annotations

from blackorca.backtest.runner import BacktestState
from blackorca.risk.limits import RiskLimits
from blackorca.risk.pretrade import PreTradeRiskCheck
from blackorca.strategies.base import BarEvent, BlackOrcaStrategy


class _NoOp(BlackOrcaStrategy):
    def on_bar(self, bar: BarEvent) -> None:
        return None


def _bind() -> _NoOp:
    s = _NoOp()
    state = BacktestState(cash=1_000_000)
    state.last_price["NVDA"] = 100.0
    s._bind(state, PreTradeRiskCheck(RiskLimits()))
    return s


def test_dollar_sizing_rounds_down() -> None:
    s = _bind()
    assert s.size_by_target_dollar(10_005, 100) == 100  # int(100.05)


def test_weight_sizing_uses_equity() -> None:
    s = _bind()
    # equity = 1M, weight=0.10 → $100k / $100 = 1000 shares
    assert s.size_by_target_weight(0.10, 100) == 1000


def test_vol_target_caps_at_max_weight() -> None:
    s = _bind()
    # very low realized vol → would want huge weight; capped at 0.10
    qty = s.size_by_volatility_target(
        annualized_vol=0.01, target_vol=0.20, price=100.0, max_weight=0.10
    )
    assert qty == 1000  # 10% of $1M / $100


def test_vol_target_scales_inversely_with_vol() -> None:
    s = _bind()
    low_vol = s.size_by_volatility_target(annualized_vol=0.10, target_vol=0.10, price=100, max_weight=1.0)
    hi_vol = s.size_by_volatility_target(annualized_vol=0.40, target_vol=0.10, price=100, max_weight=1.0)
    assert low_vol > hi_vol


def test_dollar_sizing_zero_price() -> None:
    s = _bind()
    assert s.size_by_target_dollar(10_000, 0) == 0
