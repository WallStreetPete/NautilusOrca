"""Live trading node.

Glues together: a data source (live), the same Strategy class used in
backtest, the same risk system, and an execution adapter. The loop is
deliberately simple: pull latest bar → call ``on_bar`` → drain pending
orders → submit via adapter → poll fills → mark.

A future Nautilus TradingNode adapter can replace this loop; the public
contract (configure-and-run with a Strategy) stays the same.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from blackorca.backtest.runner import BacktestState
from blackorca.config import get_settings
from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.data.sources.yfinance import YFinanceSource
from blackorca.execution.adapters.alpaca import AlpacaAdapter
from blackorca.execution.adapters.nautilus_sim import ExecutionAdapter
from blackorca.logging import get_logger
from blackorca.metrics import NAV_GAUGE, start_metrics_server
from blackorca.risk.kill_switch import KillSwitch
from blackorca.risk.limits import RiskLimits
from blackorca.risk.pretrade import PreTradeRiskCheck
from blackorca.strategies.base import BarEvent, BlackOrcaStrategy

log = get_logger(__name__)


@dataclass(slots=True)
class TradingNodeConfig:
    symbols: list[str]
    poll_seconds: int = 60
    start_capital: float = 1_000_000.0
    paper: bool = True


class TradingNode:
    def __init__(
        self,
        strategy: BlackOrcaStrategy,
        config: TradingNodeConfig,
        *,
        adapter: ExecutionAdapter | None = None,
        catalog: Catalog | None = None,
    ) -> None:
        self.strategy = strategy
        self.config = config
        self.adapter = adapter or AlpacaAdapter(paper=config.paper)
        self.catalog = catalog or Catalog()
        self._data = YFinanceSource()

        settings = get_settings()
        self.state = BacktestState(cash=config.start_capital)
        self.state.day_open_equity = self.state.cash
        self.risk = PreTradeRiskCheck(RiskLimits.from_config(settings.risk))
        self.kill = KillSwitch(
            max_drawdown_pct=settings.risk.max_drawdown_pct,
            max_daily_loss_pct=settings.risk.max_daily_loss_pct,
        )
        strategy._bind(self.state, self.risk)

    def start(self, max_iterations: int | None = None) -> None:
        start_metrics_server(get_settings().metrics.port)
        self.strategy.on_start()
        i = 0
        log.info("trading_node.start", symbols=self.config.symbols, paper=self.config.paper)
        try:
            while max_iterations is None or i < max_iterations:
                i += 1
                self._tick()
                time.sleep(self.config.poll_seconds)
        except KeyboardInterrupt:
            log.warning("trading_node.keyboard_interrupt")
        finally:
            self.strategy.on_stop()

    def _tick(self) -> None:
        # Fetch latest 5 days of daily bars and feed any new closes
        end = date.today()
        start = end - timedelta(days=10)
        df = self._data.fetch_bars(
            self.config.symbols, start, end, BarAggregation.DAY
        )
        if df.is_empty():
            log.info("trading_node.no_bars")
            return

        last = df.sort("as_of").tail(1).row(0, named=True)
        bar = BarEvent(
            symbol=last["symbol"],
            as_of=last["as_of"],
            open=last["open"],
            high=last["high"],
            low=last["low"],
            close=last["close"],
            volume=last["volume"],
        )
        self.state.last_price[bar.symbol] = bar.close
        self.strategy.on_bar(bar)

        # Submit pending orders
        while self.state.pending_orders:
            order = self.state.pending_orders.pop(0)
            self.adapter.submit(order)

        # Poll fills
        for fill in self.adapter.poll_fills():
            self._apply_fill(fill)

        # Mark NAV
        eq = self.state.equity()
        self.state.equity_hwm = max(self.state.equity_hwm, eq)
        NAV_GAUGE.labels(account="paper" if self.config.paper else "live").set(eq)

        # Kill switch
        if self.kill.evaluate(eq, self.state.equity_hwm, self.state.day_open_equity, datetime.now(UTC)):
            log.error("trading_node.kill_switch_tripped", reason=self.kill.state.reason)
            # Flatten everything
            for sym, qty in list(self.state.positions.items()):
                if qty != 0:
                    self.strategy.close(sym)
            raise SystemExit(2)

    def _apply_fill(self, fill) -> None:  # type: ignore[no-untyped-def]
        from blackorca.data.contracts import Side

        signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
        self.state.cash -= signed * fill.price + fill.commission
        self.state.positions[fill.symbol] = self.state.positions.get(fill.symbol, 0.0) + signed
        self.strategy.on_fill(fill)


__all__ = ["TradingNode", "TradingNodeConfig"]
