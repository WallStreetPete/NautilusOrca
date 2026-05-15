"""Reference strategy: SMA crossover.

A textbook fast/slow simple moving average crossover for a single symbol.
Useful as:

- end-to-end smoke test for the backtest engine
- regression baseline (its P&L on NVDA 2020-2024 is locked in by CI)
- minimal example for the strategy guide

Not intended to be a money-maker.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from blackorca.strategies.base import BarEvent, BlackOrcaStrategy
from blackorca.strategies.registry import register_strategy


@register_strategy("sma_cross")
class SmaCross(BlackOrcaStrategy):
    """Fast SMA crosses above slow SMA → long; below → flat."""

    def __init__(
        self,
        symbol: str,
        fast: int = 10,
        slow: int = 30,
        target_weight: float = 0.95,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.symbol = symbol.upper()
        self.fast_n = fast
        self.slow_n = slow
        self.target_weight = target_weight
        self.fast_win: deque[float] = deque(maxlen=fast)
        self.slow_win: deque[float] = deque(maxlen=slow)
        self.prev_signal: int = 0  # -1 / 0 / +1

    def on_bar(self, bar: BarEvent) -> None:
        if bar.symbol != self.symbol:
            return
        self.fast_win.append(bar.close)
        self.slow_win.append(bar.close)
        if len(self.slow_win) < self.slow_n:
            return
        fast_ma = sum(self.fast_win) / len(self.fast_win)
        slow_ma = sum(self.slow_win) / len(self.slow_win)
        signal = 1 if fast_ma > slow_ma else 0  # long-only reference
        if signal == self.prev_signal:
            return

        pos = self.position(self.symbol)
        price = bar.close

        if signal == 1 and pos == 0:
            qty = self.size_by_target_weight(self.target_weight, price)
            if qty > 0:
                self.buy(self.symbol, qty)
        elif signal == 0 and pos > 0:
            self.close(self.symbol)

        self.prev_signal = signal
