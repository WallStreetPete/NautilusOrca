"""Execution algorithms.

Stubs for TWAP / VWAP child-order slicers. Strategies emit a parent
``OrderRequest``; an algo wrapper slices it into child orders submitted over
time. v0 emits the parent verbatim — slicing is a follow-up once we have
intraday data.
"""

from __future__ import annotations

from dataclasses import dataclass

from blackorca.strategies.base import OrderRequest


@dataclass(slots=True)
class TWAPParams:
    duration_minutes: int = 15
    slices: int = 5


@dataclass(slots=True)
class VWAPParams:
    duration_minutes: int = 30


def twap_slice(order: OrderRequest, params: TWAPParams) -> list[OrderRequest]:
    if params.slices <= 1:
        return [order]
    qty_per = order.quantity / params.slices
    return [
        OrderRequest(
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty_per,
            order_type=order.order_type,
            limit_price=order.limit_price,
            time_in_force=order.time_in_force,
            client_order_id=f"{order.client_order_id}-{i}",
            metadata={**order.metadata, "algo": "twap", "slice": i},
        )
        for i in range(params.slices)
    ]


def vwap_slice(order: OrderRequest, params: VWAPParams) -> list[OrderRequest]:
    # Without intraday volume profile, fall back to TWAP-ish slicing.
    _ = params  # reserved
    return twap_slice(order, TWAPParams(slices=5))


__all__ = ["TWAPParams", "VWAPParams", "twap_slice", "vwap_slice"]
