"""Simulated execution adapter.

In live trading the runner submits orders to an Alpaca adapter; in backtest
it submits to this. The two implement the same :class:`ExecutionAdapter`
protocol, so the same Strategy code runs on both.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from blackorca.strategies.base import FillEvent, OrderRequest


class ExecutionAdapter(ABC):
    @abstractmethod
    def submit(self, order: OrderRequest) -> None: ...

    @abstractmethod
    def poll_fills(self) -> list[FillEvent]: ...


class SimulatedAdapter(ExecutionAdapter):
    """No-op pass-through adapter. The backtest engine fills orders directly,
    so this exists for interface parity only."""

    def submit(self, order: OrderRequest) -> None:
        return None

    def poll_fills(self) -> list[FillEvent]:
        return []


__all__ = ["ExecutionAdapter", "SimulatedAdapter"]
