"""``BlackOrcaStrategy`` — the one Strategy class every algo subclasses.

Designed to be Nautilus-Trader-compatible in shape so a future Nautilus
adapter can drop in without touching subclasses. The contract:

- Strategy lifecycle: ``on_start`` → many ``on_bar`` (or ``on_trade``/
  ``on_quote``) → ``on_stop``.
- Strategies never call broker APIs directly. They emit :class:`OrderRequest`
  objects via :meth:`submit_order` / :meth:`buy` / :meth:`sell`.
- Pre-trade risk and execution adapter are injected by the runner.
- Position sizing helpers live here so subclasses don't reinvent them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from blackorca.data.contracts import Side
from blackorca.logging import get_logger
from blackorca.metrics import (
    GROSS_EXPOSURE_GAUGE,
    NET_EXPOSURE_GAUGE,
    ORDERS_REJECTED,
    ORDERS_SUBMITTED,
)

if TYPE_CHECKING:
    from blackorca.backtest.runner import BacktestState
    from blackorca.risk.pretrade import PreTradeRiskCheck


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(StrEnum):
    DAY = "DAY"
    GTC = "GTC"


@dataclass(slots=True)
class OrderRequest:
    """Strategy-emitted order. Risk-checked and translated to a venue order."""

    strategy_id: str
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    client_order_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def signed_qty(self) -> float:
        return self.quantity if self.side is Side.BUY else -self.quantity


@dataclass(slots=True)
class BarEvent:
    symbol: str
    as_of: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class FillEvent:
    order_id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0


class BlackOrcaStrategy(ABC):
    """Base class. Subclasses override ``on_bar`` (and optionally other hooks)."""

    #: optional config dict passed via the runner
    params: dict[str, Any]

    def __init__(self, strategy_id: str | None = None, **params: Any) -> None:
        self.strategy_id = strategy_id or self.__class__.__name__
        self.params = params
        self._risk: PreTradeRiskCheck | None = None
        self._state: BacktestState | None = None
        self._submitted: list[OrderRequest] = []
        self.log = get_logger(self.strategy_id)

    # ------------------------------------------------------------------
    # injection by runner
    # ------------------------------------------------------------------

    def _bind(self, state: BacktestState, risk: PreTradeRiskCheck | None) -> None:
        self._state = state
        self._risk = risk

    # ------------------------------------------------------------------
    # lifecycle hooks (override as needed)
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info("strategy.start", id=self.strategy_id, params=self.params)

    @abstractmethod
    def on_bar(self, bar: BarEvent) -> None: ...

    def on_fill(self, fill: FillEvent) -> None:
        self.log.debug(
            "strategy.fill", symbol=fill.symbol, side=fill.side.value, qty=fill.quantity
        )

    def on_stop(self) -> None:
        self.log.info("strategy.stop", submitted=len(self._submitted))

    # ------------------------------------------------------------------
    # state access (read-only handles into the engine)
    # ------------------------------------------------------------------

    @property
    def state(self) -> BacktestState:
        if self._state is None:
            raise RuntimeError("strategy not bound to a state; use the runner")
        return self._state

    def position(self, symbol: str) -> float:
        return self.state.positions.get(symbol, 0.0)

    def equity(self) -> float:
        return self.state.equity()

    def price(self, symbol: str) -> float | None:
        return self.state.last_price.get(symbol)

    # ------------------------------------------------------------------
    # sizing helpers
    # ------------------------------------------------------------------

    def size_by_target_dollar(self, dollars: float, price: float) -> float:
        """Whole-share count for a target dollar exposure."""
        if price <= 0:
            return 0.0
        return float(int(dollars / price))

    def size_by_target_weight(self, weight: float, price: float) -> float:
        """Whole-share count for a target portfolio weight (0..1)."""
        dollars = self.equity() * weight
        return self.size_by_target_dollar(dollars, price)

    def size_by_volatility_target(
        self,
        annualized_vol: float,
        target_vol: float,
        price: float,
        max_weight: float = 0.10,
    ) -> float:
        """Vol-target sizing: weight = clip(target_vol / annualized_vol, 0, max_weight)."""
        if annualized_vol <= 0:
            return 0.0
        weight = min(max_weight, target_vol / annualized_vol)
        return self.size_by_target_weight(weight, price)

    # ------------------------------------------------------------------
    # order helpers
    # ------------------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> bool:
        """Send an order through pre-trade risk to the execution adapter."""
        if self._risk is not None:
            decision = self._risk.check(order, self.state)
            if not decision.approved:
                ORDERS_REJECTED.labels(
                    strategy=self.strategy_id, reason=decision.reason or "unknown"
                ).inc()
                self.log.warning(
                    "order.rejected",
                    symbol=order.symbol,
                    side=order.side.value,
                    qty=order.quantity,
                    reason=decision.reason,
                )
                return False

        ORDERS_SUBMITTED.labels(
            strategy=self.strategy_id, symbol=order.symbol, side=order.side.value
        ).inc()
        self._submitted.append(order)
        self.state.pending_orders.append(order)
        return True

    def buy(self, symbol: str, quantity: float, **kwargs: Any) -> bool:
        return self.submit_order(
            OrderRequest(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side=Side.BUY,
                quantity=abs(quantity),
                **kwargs,
            )
        )

    def sell(self, symbol: str, quantity: float, **kwargs: Any) -> bool:
        return self.submit_order(
            OrderRequest(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side=Side.SELL,
                quantity=abs(quantity),
                **kwargs,
            )
        )

    def close(self, symbol: str) -> bool:
        """Flatten the position in ``symbol`` at market."""
        qty = self.position(symbol)
        if qty == 0:
            return False
        side = Side.SELL if qty > 0 else Side.BUY
        return self.submit_order(
            OrderRequest(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side=side,
                quantity=abs(qty),
            )
        )

    # ------------------------------------------------------------------
    # observability
    # ------------------------------------------------------------------

    def emit_exposure_metrics(self) -> None:
        gross = sum(abs(q) * (self.price(s) or 0.0) for s, q in self.state.positions.items())
        net = sum(q * (self.price(s) or 0.0) for s, q in self.state.positions.items())
        GROSS_EXPOSURE_GAUGE.labels(strategy=self.strategy_id).set(gross)
        NET_EXPOSURE_GAUGE.labels(strategy=self.strategy_id).set(net)


__all__ = [
    "BarEvent",
    "BlackOrcaStrategy",
    "FillEvent",
    "OrderRequest",
    "OrderType",
    "TimeInForce",
]
