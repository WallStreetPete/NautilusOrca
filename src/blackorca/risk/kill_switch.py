"""Kill switch.

Halts trading on:

- portfolio drawdown breach (peak-to-trough)
- daily P&L floor breach
- explicit operator trip via ``KillSwitch.trip()``

Once tripped, the switch stays tripped until manually reset. The runner / live
trading node polls :meth:`is_tripped` between bars; if true, no new orders are
submitted and (in live) all positions are flattened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from blackorca.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class KillSwitchState:
    tripped: bool = False
    reason: str | None = None
    tripped_at: datetime | None = None


class KillSwitch:
    def __init__(
        self,
        *,
        max_drawdown_pct: float,
        max_daily_loss_pct: float,
    ) -> None:
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.state = KillSwitchState()

    def evaluate(
        self,
        equity: float,
        equity_hwm: float,
        day_open_equity: float,
        now: datetime,
    ) -> bool:
        if self.state.tripped:
            return True
        if equity_hwm > 0:
            dd = (equity_hwm - equity) / equity_hwm
            if dd >= self.max_drawdown_pct:
                self._trip(f"drawdown {dd:.2%} >= {self.max_drawdown_pct:.2%}", now)
                return True
        if day_open_equity > 0:
            day_pnl = (equity - day_open_equity) / day_open_equity
            if -day_pnl >= self.max_daily_loss_pct:
                self._trip(f"daily loss {day_pnl:.2%} <= {-self.max_daily_loss_pct:.2%}", now)
                return True
        return False

    def trip(self, reason: str, now: datetime | None = None) -> None:
        self._trip(reason, now or datetime.now())

    def reset(self) -> None:
        log.warning("kill_switch.reset", previous_reason=self.state.reason)
        self.state = KillSwitchState()

    def is_tripped(self) -> bool:
        return self.state.tripped

    def _trip(self, reason: str, now: datetime) -> None:
        self.state.tripped = True
        self.state.reason = reason
        self.state.tripped_at = now
        log.error("kill_switch.tripped", reason=reason)


__all__ = ["KillSwitch", "KillSwitchState"]
