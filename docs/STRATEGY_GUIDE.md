# Strategy Guide

How to add a strategy and ship it through paper to live.

## 1. Subclass `BlackOrcaStrategy`

```python
from blackorca.strategies.base import BarEvent, BlackOrcaStrategy
from blackorca.strategies.registry import register_strategy

@register_strategy("my_strat")
class MyStrat(BlackOrcaStrategy):
    def __init__(self, symbol: str, threshold: float = 0.02, **kwargs):
        super().__init__(**kwargs)
        self.symbol = symbol.upper()
        self.threshold = threshold
        self.prev_close: float | None = None

    def on_bar(self, bar: BarEvent) -> None:
        if bar.symbol != self.symbol:
            return
        if self.prev_close is not None:
            day_ret = (bar.close - self.prev_close) / self.prev_close
            if day_ret < -self.threshold and self.position(self.symbol) == 0:
                qty = self.size_by_target_weight(0.05, bar.close)
                self.buy(self.symbol, qty)
            elif day_ret > self.threshold and self.position(self.symbol) > 0:
                self.close(self.symbol)
        self.prev_close = bar.close
```

## 2. Rules of the road

- **Never** access data with `as_of > now`. Use only what's on this bar's `BarEvent`, the rolling state you've maintained yourself, or features computed with the PIT pipelines.
- **Always** submit orders via `self.buy / self.sell / self.close / self.submit_order`. They route through the risk gate.
- **Sizing** — prefer `size_by_target_weight` or `size_by_volatility_target`. Don't hardcode share counts.
- **State** — keep per-symbol state in instance attributes (dicts keyed by symbol). The runner resets you between backtests; live runs keep you running across days.

## 3. Backtest

```bash
uv run python scripts/run_backtest.py --strategy my_strat --symbol NVDA --params-json '{"threshold":0.03}'
```

## 4. Walk-forward

```bash
uv run python scripts/run_walk_forward.py --strategy my_strat --symbol NVDA
```

A real strategy should be stable across windows. If the per-window Sharpe std is more than 2× the mean, it's overfit.

## 5. Code review (agent)

```bash
uv run python -c "from blackorca.agents.graphs.strategy_review import review_strategy; \
print(review_strategy('blackorca.strategies.examples.sma_cross').model_dump())"
```

## 6. Regression baseline

Add an entry to `tests/regression/test_strategy_baselines.py` with the expected metrics. The CI will catch any unintentional drift.

## 7. Promote to paper

```bash
BLACKORCA_PROFILE=paper uv run python scripts/start_paper_trading.py --strategy=my_strat --symbol=NVDA
```

Watch the Grafana board for an hour. If clean, leave it running.
