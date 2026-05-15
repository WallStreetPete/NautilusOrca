"""Transaction cost model.

- Commission: ``per_share + min_ticket``, capped at a max % of notional.
- Borrow cost for shorts: annualized bps applied per overnight hold.
- Financing: optional — set ``financing_bps`` if you mark to a margin rate.
"""

from __future__ import annotations

from dataclasses import dataclass

from blackorca.data.contracts import Side


@dataclass(slots=True)
class CostModelConfig:
    per_share: float = 0.005
    min_ticket: float = 1.00
    max_pct_notional: float = 0.005  # 50 bps
    borrow_bps_annual: float = 50.0
    financing_bps: float = 0.0


class CostModel:
    def __init__(self, config: CostModelConfig | None = None) -> None:
        self.config = config or CostModelConfig()

    def commission(self, side: Side, quantity: float, price: float) -> float:
        """Per-trade commission. ``side`` is unused today but reserved for
        venue-specific fee schedules later."""
        del side
        notional = quantity * price
        c = max(self.config.per_share * quantity, self.config.min_ticket)
        return min(c, self.config.max_pct_notional * notional)

    def daily_borrow_cost(self, short_value_usd: float) -> float:
        return (self.config.borrow_bps_annual / 10_000) / 252 * max(short_value_usd, 0.0)

    def daily_financing_cost(self, long_value_usd: float) -> float:
        return (self.config.financing_bps / 10_000) / 252 * max(long_value_usd, 0.0)


__all__ = ["CostModel", "CostModelConfig"]
