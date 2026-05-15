"""Fill model.

Configurable slippage (basis points off mid), square-root market impact
(scales by qty / ADV), and partial fills when an order is larger than the
liquidity available in the bar.

Default coefficients are conservative; calibrate per-instrument later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from blackorca.data.contracts import Side


@dataclass(slots=True)
class FillModelConfig:
    slippage_bps: float = 2.0
    impact_coef: float = 10.0       # bps when participation = 1.0
    max_bar_participation: float = 0.10  # cap how much of bar volume we can take
    partial_fills: bool = True


@dataclass(slots=True)
class SimulatedFill:
    price: float
    quantity_filled: float
    slippage_bps: float


class FillModel:
    def __init__(self, config: FillModelConfig | None = None) -> None:
        self.config = config or FillModelConfig()

    def simulate(
        self,
        *,
        side: Side,
        quantity: float,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_volume: float,
        limit_price: float | None = None,
    ) -> SimulatedFill | None:
        """Simulate a single-bar fill. Returns ``None`` if completely unfilled."""

        if quantity <= 0:
            return None

        # Use VWAP-ish mid = (open + close + high + low) / 4
        ref = (bar_open + bar_close + bar_high + bar_low) / 4.0
        if ref <= 0:
            return None

        # Liquidity-bounded fill quantity
        max_qty = (
            self.config.max_bar_participation * bar_volume
            if self.config.partial_fills
            else quantity
        )
        if max_qty <= 0:
            return None
        filled = min(quantity, max_qty)

        participation = filled / max(bar_volume, 1.0)
        impact_bps = self.config.impact_coef * math.sqrt(participation)
        bps = self.config.slippage_bps + impact_bps

        sign = 1.0 if side is Side.BUY else -1.0
        price = ref * (1 + sign * bps / 10_000)

        # If limit order, gate by limit
        if limit_price is not None:
            if side is Side.BUY and price > limit_price:
                return None
            if side is Side.SELL and price < limit_price:
                return None

        # Clamp to bar range — never fill outside the printed high/low
        price = min(max(price, bar_low), bar_high)
        return SimulatedFill(price=price, quantity_filled=filled, slippage_bps=bps)


__all__ = ["FillModel", "FillModelConfig", "SimulatedFill"]
