"""Alpaca paper/live trading adapter.

Uses the official ``alpaca-py`` SDK. Falls back to a stub when keys aren't
configured so test code can import this module safely.

Order model:

- Market orders translate straight to ``MarketOrderRequest``.
- Limit orders use ``LimitOrderRequest`` with the provided ``limit_price``.
- TIF defaults to DAY; GTC supported.
- Client order IDs are propagated for reconciliation.

Fill polling is best-effort via the orders endpoint; live deployments
should subscribe to the trade-update websocket — that's the v0.5 follow-up.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from blackorca.config import get_settings
from blackorca.data.contracts import Side
from blackorca.execution.adapters.nautilus_sim import ExecutionAdapter
from blackorca.logging import get_logger
from blackorca.strategies.base import FillEvent, OrderRequest, OrderType, TimeInForce

log = get_logger(__name__)


class AlpacaAdapter(ExecutionAdapter):
    def __init__(self, paper: bool = True) -> None:
        self.paper = paper
        self._client: Any = None
        self._submitted_ids: dict[str, OrderRequest] = {}
        self._reported_fills: set[str] = set()

    def is_available(self) -> bool:
        s = get_settings()
        return s.alpaca_api_key is not None and s.alpaca_api_secret is not None

    def _ensure(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.is_available():
            raise RuntimeError("ALPACA_API_KEY / ALPACA_API_SECRET not set")
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as e:
            raise RuntimeError("alpaca-py not installed; `uv sync --extra alpaca`") from e
        s = get_settings()
        self._client = TradingClient(
            api_key=s.alpaca_api_key.get_secret_value() if s.alpaca_api_key else "",
            secret_key=s.alpaca_api_secret.get_secret_value() if s.alpaca_api_secret else "",
            paper=self.paper,
        )
        return self._client

    def submit(self, order: OrderRequest) -> None:
        try:
            from alpaca.trading.enums import OrderSide
            from alpaca.trading.enums import TimeInForce as AlpacaTIF
            from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        except ImportError:
            log.warning("alpaca.unavailable", reason="alpaca-py not installed; order skipped")
            return

        client = self._ensure()
        side = OrderSide.BUY if order.side is Side.BUY else OrderSide.SELL
        tif = AlpacaTIF.GTC if order.time_in_force is TimeInForce.GTC else AlpacaTIF.DAY
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            req = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=tif,
                limit_price=order.limit_price,
                client_order_id=order.client_order_id,
            )
        else:
            req = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=tif,
                client_order_id=order.client_order_id,
            )
        try:
            placed = client.submit_order(req)
            self._submitted_ids[str(placed.id)] = order
            log.info(
                "alpaca.order_submitted",
                client_id=order.client_order_id,
                broker_id=str(placed.id),
                symbol=order.symbol,
                qty=order.quantity,
            )
        except Exception as e:
            log.error("alpaca.submit_failed", error=str(e))

    def poll_fills(self) -> list[FillEvent]:
        try:
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest
        except ImportError:
            return []
        client = self._ensure()
        out: list[FillEvent] = []
        try:
            orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50))
        except Exception as e:
            log.warning("alpaca.poll_failed", error=str(e))
            return out

        for o in orders:
            broker_id = str(o.id)
            if broker_id in self._reported_fills:
                continue
            if o.filled_qty is None or float(o.filled_qty) <= 0:
                continue
            req = self._submitted_ids.get(broker_id)
            if req is None:
                continue
            out.append(
                FillEvent(
                    order_id=req.client_order_id,
                    symbol=o.symbol,
                    side=Side.BUY if str(o.side).lower().endswith("buy") else Side.SELL,
                    quantity=float(o.filled_qty),
                    price=float(o.filled_avg_price or 0.0),
                    timestamp=o.filled_at or datetime.now(UTC),
                )
            )
            self._reported_fills.add(broker_id)
        return out


__all__ = ["AlpacaAdapter"]
