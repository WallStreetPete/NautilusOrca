"""Pre-trade risk checks.

Every order — backtest, paper, or live — goes through :meth:`PreTradeRiskCheck.check`
before the venue sees it. The intent is failure transparency: if an order is
rejected, the strategy knows *exactly* which limit tripped and why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from blackorca.data.contracts import Side
from blackorca.risk.limits import RiskLimits

if TYPE_CHECKING:
    from blackorca.backtest.runner import BacktestState
    from blackorca.strategies.base import OrderRequest


@dataclass(frozen=True, slots=True)
class RiskRejection:
    approved: bool
    reason: str | None = None
    code: str | None = None


_APPROVED = RiskRejection(approved=True)


class PreTradeRiskCheck:
    """Composable pre-trade checks. Add new ones by subclassing or extending."""

    def __init__(
        self,
        limits: RiskLimits,
        *,
        sector_map: dict[str, str] | None = None,
    ) -> None:
        self.limits = limits
        self.sector_map = sector_map or {}

    # ------------------------------------------------------------------
    # public entry
    # ------------------------------------------------------------------

    def check(self, order: OrderRequest, state: BacktestState) -> RiskRejection:
        price = state.last_price.get(order.symbol)
        if price is None or price <= 0:
            return RiskRejection(False, "no reference price", "NO_PRICE")

        equity = max(state.equity(), 1.0)  # avoid div-by-zero in edge cases
        notional = order.quantity * price

        # 1) Per-order notional cap
        if notional > self.limits.per_order_max_notional:
            return RiskRejection(False, f"order notional {notional:.0f} > cap", "ORDER_NOTIONAL")

        # 2) Single-name cap (post-trade position size).
        # Reductions (post-trade |position| < pre-trade |position|) are always
        # allowed — even if the position is *already* over-cap, we should let
        # the strategy bring it down.
        pre_qty = state.positions.get(order.symbol, 0.0)
        signed_after = pre_qty + (
            order.quantity if order.side is Side.BUY else -order.quantity
        )
        increasing = abs(signed_after) > abs(pre_qty)
        if increasing and abs(signed_after) * price > self.limits.max_position_pct * equity:
            return RiskRejection(
                False,
                f"position {order.symbol} would be {abs(signed_after) * price / equity:.1%} > "
                f"{self.limits.max_position_pct:.1%}",
                "POSITION_CAP",
            )

        # 3) Symbol share caps
        cap = self.limits.symbol_share_caps.get(order.symbol)
        if cap is not None and abs(signed_after) > cap:
            return RiskRejection(False, f"share cap {cap} for {order.symbol}", "SHARE_CAP")

        # 4) Gross / net exposure caps (post-trade)
        gross, net = self._exposures_after(order, price, state)
        if gross > self.limits.max_gross_pct * equity:
            return RiskRejection(
                False,
                f"gross {gross / equity:.2f} > cap {self.limits.max_gross_pct:.2f}",
                "GROSS_CAP",
            )
        if net > self.limits.max_net_pct * equity:
            return RiskRejection(
                False,
                f"net {net / equity:.2f} > cap {self.limits.max_net_pct:.2f}",
                "NET_CAP",
            )

        # 5) Sector caps (if mapping provided)
        sector = self.sector_map.get(order.symbol)
        if sector is not None:
            sector_notional = 0.0
            for sym, qty in state.positions.items():
                if self.sector_map.get(sym) == sector:
                    sector_notional += abs(qty) * (state.last_price.get(sym) or 0.0)
            sym_sector = self.sector_map.get(order.symbol)
            if sym_sector is not None and sym_sector == sector:
                sector_notional += abs(signed_after - state.positions.get(order.symbol, 0.0)) * price
            cap_pct = self.limits.sector_caps.get(sector, self.limits.max_sector_pct)
            if sector_notional > cap_pct * equity:
                return RiskRejection(
                    False,
                    f"sector {sector} {sector_notional / equity:.1%} > cap {cap_pct:.1%}",
                    "SECTOR_CAP",
                )

        # 6) Daily loss limit
        if state.equity_hwm > 0:
            daily_dd = (state.equity_hwm - state.equity()) / state.equity_hwm
            if daily_dd > self.limits.max_daily_loss_pct:
                return RiskRejection(
                    False,
                    f"daily drawdown {daily_dd:.2%} > cap {self.limits.max_daily_loss_pct:.2%}",
                    "DAILY_LOSS",
                )

        return _APPROVED

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _exposures_after(
        self, order: OrderRequest, price: float, state: BacktestState
    ) -> tuple[float, float]:
        signed_delta = order.quantity if order.side is Side.BUY else -order.quantity
        positions = dict(state.positions)
        positions[order.symbol] = positions.get(order.symbol, 0.0) + signed_delta

        gross = 0.0
        net = 0.0
        for sym, qty in positions.items():
            mark = state.last_price.get(sym, price if sym == order.symbol else 0.0) or 0.0
            gross += abs(qty) * mark
            net += qty * mark
        return gross, abs(net)


__all__ = ["PreTradeRiskCheck", "RiskRejection"]
