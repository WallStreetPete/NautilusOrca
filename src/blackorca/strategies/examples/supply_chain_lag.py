"""Tier-1 catalyst → tier-2 drift strategy.

Hypothesis: when a tier-1 semi name (e.g. NVDA) prints a large move, the
tier-2/3 names in the curated dependency graph drift in the same direction
over the next ``edge.expected_lag_days``. This strategy looks for the trigger
and rotates into the downstream basket weighted by edge confidence.

Sizing: equal-weight across downstream names, capped at ``per_name_weight``.
Holding period: ``edge.expected_lag_days``.
Exit: time-based.

This is a meaningful strategy worth backtesting, not a toy. Calibration of
the catalyst threshold and the holding period is the research job.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from blackorca.strategies.base import BarEvent, BlackOrcaStrategy
from blackorca.strategies.registry import register_strategy
from blackorca.universe.dependency_graph import DEPENDENCY_GRAPH, SupplierEdge


@dataclass(slots=True)
class _OpenLeg:
    symbol: str
    entry_date: datetime
    exit_after: datetime
    qty: float


@dataclass(slots=True)
class _State:
    last_close: dict[str, float] = field(default_factory=dict)
    ma_window: dict[str, deque[float]] = field(default_factory=dict)
    open_legs: list[_OpenLeg] = field(default_factory=list)


@register_strategy("supply_chain_lag")
class SupplyChainLag(BlackOrcaStrategy):
    """Catalyst-driven downstream basket trade."""

    def __init__(
        self,
        catalyst_threshold: float = 0.05,
        min_confidence: float = 0.4,
        per_name_weight: float = 0.04,
        catalysts: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.catalyst_threshold = catalyst_threshold
        self.min_confidence = min_confidence
        self.per_name_weight = per_name_weight
        catalyst_list = list(catalysts) if catalysts else [e.upstream for e in DEPENDENCY_GRAPH]
        self.catalysts = sorted(set(catalyst_list))
        self.state = _State()

    def on_start(self) -> None:
        super().on_start()
        for sym in self.catalysts:
            self.state.ma_window[sym] = deque(maxlen=2)  # need only t-1 close

    def on_bar(self, bar: BarEvent) -> None:
        sym = bar.symbol

        # Track for catalysts
        if sym in self.catalysts:
            prev_close = self.state.last_close.get(sym)
            self.state.last_close[sym] = bar.close
            if prev_close is not None and prev_close > 0:
                day_ret = (bar.close - prev_close) / prev_close
                if abs(day_ret) >= self.catalyst_threshold:
                    self._fire(sym, direction=1 if day_ret > 0 else -1, now=bar.as_of)

        # Exit time-based legs
        self._maybe_close_legs(bar.as_of, bar.symbol, bar.close)

    def _fire(self, catalyst: str, direction: int, now: datetime) -> None:
        edges: list[SupplierEdge] = [
            e for e in DEPENDENCY_GRAPH
            if e.upstream == catalyst and e.confidence >= self.min_confidence
        ]
        if not edges:
            return
        weights = {e.downstream: self.per_name_weight * e.confidence for e in edges}
        for edge in edges:
            sym = edge.downstream
            px = self.price(sym)
            if px is None or px <= 0:
                continue
            target_shares = self.size_by_target_weight(weights[sym], px) * direction
            current = self.position(sym)
            delta = target_shares - current
            if abs(delta) < 1:
                continue
            ok = (self.buy if delta > 0 else self.sell)(sym, abs(delta))
            if ok:
                from datetime import timedelta

                self.state.open_legs.append(
                    _OpenLeg(
                        symbol=sym,
                        entry_date=now,
                        exit_after=now + timedelta(days=edge.expected_lag_days),
                        qty=delta,
                    )
                )

    def _maybe_close_legs(self, now: datetime, symbol: str, _close: float) -> None:
        remaining: list[_OpenLeg] = []
        for leg in self.state.open_legs:
            if leg.symbol == symbol and now >= leg.exit_after:
                if self.position(symbol) != 0:
                    self.close(symbol)
            else:
                remaining.append(leg)
        self.state.open_legs = remaining
