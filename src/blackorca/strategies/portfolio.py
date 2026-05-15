"""Multi-strategy portfolio combiner.

Aggregates target weights from several sub-strategies into a single
order stream. Each sub-strategy publishes a per-symbol target weight via
:meth:`SubStrategySignal`; the combiner nets positions and rebalances to the
weighted blend respecting a per-strategy capital allocation.

Trade-off: this is a *target-weight blender*, not a true multi-strategy
trading node. A full implementation would run each strategy in its own
account and reconcile at the end. For day-0 it's enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from blackorca.strategies.base import BarEvent, BlackOrcaStrategy


@dataclass(slots=True)
class StrategyWeight:
    strategy: BlackOrcaStrategy
    allocation: float            # fraction of total capital
    target_weights: dict[str, float] = field(default_factory=dict)


class PortfolioCombiner(BlackOrcaStrategy):
    """Owns multiple sub-strategies; submits net orders."""

    def __init__(
        self,
        components: list[StrategyWeight],
        rebalance_threshold: float = 0.01,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.components = components
        self.rebalance_threshold = rebalance_threshold
        if not np.isclose(sum(c.allocation for c in components), 1.0):
            raise ValueError("component allocations must sum to 1.0")

    def on_bar(self, bar: BarEvent) -> None:
        # Update each sub-strategy's last_price view
        for comp in self.components:
            comp.strategy._bind(self.state, self._risk)
            comp.strategy.on_bar(bar)

        # Build blended target weights
        blended: dict[str, float] = {}
        for comp in self.components:
            for sym, w in comp.target_weights.items():
                blended[sym] = blended.get(sym, 0.0) + comp.allocation * w

        # Translate to share targets and rebalance
        equity = self.equity()
        for sym, target_w in blended.items():
            px = self.price(sym)
            if px is None or px <= 0:
                continue
            target_qty = int(target_w * equity / px)
            current = self.position(sym)
            if abs(target_qty - current) * px > self.rebalance_threshold * equity:
                delta = target_qty - current
                if delta > 0:
                    self.buy(sym, delta)
                elif delta < 0:
                    self.sell(sym, -delta)
