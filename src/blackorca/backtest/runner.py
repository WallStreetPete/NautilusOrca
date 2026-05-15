"""Event-driven backtest runner.

Nautilus-compatible in shape:

- A single in-process loop iterates ``BarEvent``s in chronological order.
- Strategies see one bar at a time; they emit :class:`OrderRequest`s.
- Orders are filled on the *next* bar (T+1 fill — no look-ahead).
- The same ``BlackOrcaStrategy`` subclass runs in backtest, paper, and live.

A future :class:`NautilusBacktestAdapter` can swap into ``run_backtest`` without
strategies noticing — that's the whole point of the design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import polars as pl

from blackorca.backtest.costs import CostModel, CostModelConfig
from blackorca.backtest.fills import FillModel, FillModelConfig
from blackorca.config import get_settings
from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation, Side
from blackorca.logging import get_logger
from blackorca.metrics import FILLS, PNL_GAUGE
from blackorca.risk.kill_switch import KillSwitch
from blackorca.risk.limits import RiskLimits
from blackorca.risk.pretrade import PreTradeRiskCheck
from blackorca.strategies.base import (
    BarEvent,
    BlackOrcaStrategy,
    FillEvent,
    OrderRequest,
    OrderType,
)

log = get_logger(__name__)


@dataclass(slots=True)
class BacktestState:
    """Mutable engine state strategies can read."""

    cash: float
    positions: dict[str, float] = field(default_factory=dict)
    last_price: dict[str, float] = field(default_factory=dict)
    pending_orders: list[OrderRequest] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    equity_hwm: float = 0.0
    day_open_equity: float = 0.0
    current_day: date | None = None

    def equity(self) -> float:
        mtm = sum(q * self.last_price.get(s, 0.0) for s, q in self.positions.items())
        return self.cash + mtm


@dataclass(slots=True)
class TradeRecord:
    timestamp: datetime
    symbol: str
    side: Side
    quantity: float
    price: float
    commission: float
    slippage_bps: float


@dataclass(slots=True)
class BacktestResult:
    equity_curve: pl.DataFrame
    trades: pl.DataFrame
    metrics: dict[str, float]
    config: dict[str, Any]

    @property
    def total_return(self) -> float:
        return float(self.metrics.get("total_return", 0.0))

    @property
    def sharpe(self) -> float:
        return float(self.metrics.get("sharpe", 0.0))

    @property
    def max_drawdown(self) -> float:
        return float(self.metrics.get("max_drawdown", 0.0))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def run_backtest(
    strategy: BlackOrcaStrategy,
    *,
    symbols: list[str],
    start: date | datetime,
    end: date | datetime,
    capital: float | None = None,
    catalog: Catalog | None = None,
    risk_limits: RiskLimits | None = None,
    fill_config: FillModelConfig | None = None,
    cost_config: CostModelConfig | None = None,
    aggregation: BarAggregation = BarAggregation.DAY,
    sector_map: dict[str, str] | None = None,
) -> BacktestResult:
    """Run a backtest. Returns a :class:`BacktestResult`."""
    settings = get_settings()
    catalog = catalog or Catalog()
    capital = capital if capital is not None else settings.backtest.default_capital

    # Pull data
    df = catalog.read_bars(symbols, start, end, aggregation)
    if df.is_empty():
        raise RuntimeError(
            f"no bars found for {symbols} in [{start}, {end}]; ingest data first"
        )

    risk = PreTradeRiskCheck(
        risk_limits or RiskLimits.from_config(settings.risk),
        sector_map=sector_map,
    )
    fill_model = FillModel(fill_config)
    cost_model = CostModel(cost_config)
    kill = KillSwitch(
        max_drawdown_pct=settings.risk.max_drawdown_pct,
        max_daily_loss_pct=settings.risk.max_daily_loss_pct,
    )

    state = BacktestState(cash=float(capital))
    state.day_open_equity = state.equity()

    strategy._bind(state, risk)
    strategy.on_start()

    trades: list[TradeRecord] = []

    # Bar timeline: process bars in (as_of, symbol) order
    df = df.sort(["as_of", "symbol"])
    bars_by_time = df.group_by("as_of", maintain_order=True)

    for ts, sub in bars_by_time:
        timestamp = ts[0] if isinstance(ts, tuple) else ts
        if not isinstance(timestamp, datetime):
            timestamp = _to_dt(timestamp)

        # Update day boundary BEFORE evaluating bars so kill-switch uses today's
        day = timestamp.date()
        if state.current_day is None or day != state.current_day:
            state.current_day = day
            state.day_open_equity = state.equity()

        # 1) Fill pending orders against this bar (T+1 fill)
        if state.pending_orders:
            remaining: list[OrderRequest] = []
            for order in state.pending_orders:
                bar_row = sub.filter(pl.col("symbol") == order.symbol)
                if bar_row.is_empty():
                    remaining.append(order)
                    continue
                row = bar_row.row(0, named=True)
                fill = fill_model.simulate(
                    side=order.side,
                    quantity=order.quantity,
                    bar_open=row["open"],
                    bar_high=row["high"],
                    bar_low=row["low"],
                    bar_close=row["close"],
                    bar_volume=row["volume"],
                    limit_price=order.limit_price if order.order_type is OrderType.LIMIT else None,
                )
                if fill is None:
                    remaining.append(order)
                    continue
                commission = cost_model.commission(order.side, fill.quantity_filled, fill.price)
                signed_qty = (
                    fill.quantity_filled if order.side is Side.BUY else -fill.quantity_filled
                )
                # Apply cash + position
                state.cash -= signed_qty * fill.price
                state.cash -= commission
                state.positions[order.symbol] = (
                    state.positions.get(order.symbol, 0.0) + signed_qty
                )
                FILLS.labels(
                    strategy=strategy.strategy_id, symbol=order.symbol, side=order.side.value
                ).inc()
                trades.append(
                    TradeRecord(
                        timestamp=timestamp,
                        symbol=order.symbol,
                        side=order.side,
                        quantity=fill.quantity_filled,
                        price=fill.price,
                        commission=commission,
                        slippage_bps=fill.slippage_bps,
                    )
                )
                strategy.on_fill(
                    FillEvent(
                        order_id=order.client_order_id,
                        symbol=order.symbol,
                        side=order.side,
                        quantity=fill.quantity_filled,
                        price=fill.price,
                        timestamp=timestamp,
                        commission=commission,
                        slippage=fill.slippage_bps,
                    )
                )
                # Partial?
                if fill.quantity_filled < order.quantity:
                    order_remainder = OrderRequest(
                        strategy_id=order.strategy_id,
                        symbol=order.symbol,
                        side=order.side,
                        quantity=order.quantity - fill.quantity_filled,
                        order_type=order.order_type,
                        limit_price=order.limit_price,
                        time_in_force=order.time_in_force,
                        client_order_id=order.client_order_id + "-rem",
                        metadata=order.metadata,
                    )
                    remaining.append(order_remainder)
            state.pending_orders = remaining

        # 2) Mark to market with the *close* of this bar
        for row in sub.iter_rows(named=True):
            state.last_price[row["symbol"]] = row["close"]
            strategy.on_bar(
                BarEvent(
                    symbol=row["symbol"],
                    as_of=row["as_of"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
            )

        # 3) Update equity curve
        eq = state.equity()
        state.equity_hwm = max(state.equity_hwm, eq)
        state.equity_curve.append((timestamp, eq))
        PNL_GAUGE.labels(strategy=strategy.strategy_id).set(eq - capital)

        # 4) Kill switch
        if kill.evaluate(eq, state.equity_hwm, state.day_open_equity, timestamp):
            log.error("backtest.halted_by_kill_switch", reason=kill.state.reason)
            state.pending_orders.clear()
            break

    strategy.on_stop()

    # Build outputs
    eq_df = pl.DataFrame(
        {
            "timestamp": [t for t, _ in state.equity_curve],
            "equity": [e for _, e in state.equity_curve],
        }
    )
    trades_df = pl.from_dicts(
        [
            {
                "timestamp": t.timestamp,
                "symbol": t.symbol,
                "side": t.side.value,
                "quantity": t.quantity,
                "price": t.price,
                "commission": t.commission,
                "slippage_bps": t.slippage_bps,
            }
            for t in trades
        ]
    ) if trades else pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", time_zone="UTC"),
            "symbol": pl.Utf8,
            "side": pl.Utf8,
            "quantity": pl.Float64,
            "price": pl.Float64,
            "commission": pl.Float64,
            "slippage_bps": pl.Float64,
        }
    )

    from blackorca.backtest.analyzer import compute_metrics

    metrics = compute_metrics(eq_df, trades_df, initial_capital=capital)
    return BacktestResult(
        equity_curve=eq_df,
        trades=trades_df,
        metrics=metrics,
        config={
            "strategy_id": strategy.strategy_id,
            "symbols": symbols,
            "start": str(start),
            "end": str(end),
            "capital": capital,
            "aggregation": aggregation.value,
        },
    )


def _to_dt(x: object) -> datetime:
    if isinstance(x, datetime):
        return x
    if isinstance(x, date):
        return datetime(x.year, x.month, x.day, tzinfo=UTC)
    return datetime.fromisoformat(str(x)).replace(tzinfo=UTC)


__all__ = ["BacktestResult", "BacktestState", "TradeRecord", "run_backtest"]
