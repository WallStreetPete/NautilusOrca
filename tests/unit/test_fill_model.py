"""Fill model behavior under various order/bar combinations."""

from __future__ import annotations

from blackorca.backtest.fills import FillModel, FillModelConfig
from blackorca.data.contracts import Side


def _fm(**kwargs: float | bool) -> FillModel:
    return FillModel(FillModelConfig(**kwargs))  # type: ignore[arg-type]


def test_market_buy_pays_slippage() -> None:
    fm = _fm(slippage_bps=10, impact_coef=0)
    fill = fm.simulate(
        side=Side.BUY,
        quantity=100,
        bar_open=100, bar_high=102, bar_low=98, bar_close=101, bar_volume=10_000,
    )
    assert fill is not None
    mid = (100 + 102 + 98 + 101) / 4
    # 10 bps slippage above mid, but clamped to bar high
    assert fill.price > mid
    assert fill.price <= 102
    assert fill.quantity_filled == 100


def test_market_sell_receives_slippage() -> None:
    fm = _fm(slippage_bps=10, impact_coef=0)
    fill = fm.simulate(
        side=Side.SELL,
        quantity=100,
        bar_open=100, bar_high=102, bar_low=98, bar_close=101, bar_volume=10_000,
    )
    assert fill is not None
    mid = (100 + 102 + 98 + 101) / 4
    assert fill.price < mid
    assert fill.price >= 98


def test_partial_fill_by_participation() -> None:
    fm = _fm(slippage_bps=0, impact_coef=0, max_bar_participation=0.05)
    fill = fm.simulate(
        side=Side.BUY,
        quantity=10_000,
        bar_open=100, bar_high=100, bar_low=100, bar_close=100, bar_volume=10_000,
    )
    assert fill is not None
    assert fill.quantity_filled == 500   # 5% participation cap


def test_limit_not_crossed_no_fill() -> None:
    fm = _fm(slippage_bps=0, impact_coef=0)
    fill = fm.simulate(
        side=Side.BUY,
        quantity=10,
        bar_open=100, bar_high=102, bar_low=98, bar_close=101, bar_volume=10_000,
        limit_price=95,
    )
    assert fill is None


def test_impact_increases_with_participation() -> None:
    fm = _fm(slippage_bps=0, impact_coef=100, max_bar_participation=1.0)
    small = fm.simulate(
        side=Side.BUY, quantity=10,
        bar_open=100, bar_high=100, bar_low=100, bar_close=100, bar_volume=10_000,
    )
    large = fm.simulate(
        side=Side.BUY, quantity=1_000,
        bar_open=100, bar_high=100, bar_low=100, bar_close=100, bar_volume=10_000,
    )
    assert small and large
    # large order should pay strictly more bps
    assert large.slippage_bps > small.slippage_bps


def test_zero_quantity_no_fill() -> None:
    fm = _fm()
    fill = fm.simulate(
        side=Side.BUY, quantity=0,
        bar_open=100, bar_high=100, bar_low=100, bar_close=100, bar_volume=10_000,
    )
    assert fill is None
