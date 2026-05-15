"""Paper-trading entrypoint.

Boots a :class:`TradingNode` with the Alpaca paper adapter and the chosen
strategy. Full risk system active.
"""

from __future__ import annotations

import json
import sys

from blackorca.config import get_settings
from blackorca.live.trading_node import TradingNode, TradingNodeConfig
from blackorca.logging import configure_logging, get_logger
from blackorca.strategies.registry import StrategyRegistry


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    settings = get_settings()
    configure_logging(level=settings.logging.level, json=settings.logging.json_output)
    log = get_logger("paper")

    strategy_name = "sma_cross"
    symbol = "NVDA"
    params: dict[str, object] = {}
    for arg in argv:
        if arg.startswith("--strategy="):
            strategy_name = arg.split("=", 1)[1]
        elif arg.startswith("--symbol="):
            symbol = arg.split("=", 1)[1]
        elif arg.startswith("--params="):
            params = json.loads(arg.split("=", 1)[1])

    strat_cls = StrategyRegistry.get(strategy_name)
    strat = strat_cls(symbol=symbol, **params)

    node = TradingNode(
        strategy=strat,
        config=TradingNodeConfig(
            symbols=[symbol], poll_seconds=60, start_capital=settings.backtest.default_capital, paper=True
        ),
    )
    log.info("paper.boot", strategy=strategy_name, symbol=symbol)
    node.start()


if __name__ == "__main__":
    main()
