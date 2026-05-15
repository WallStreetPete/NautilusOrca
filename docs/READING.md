# Black Orca Capital — Apex Platform: Full Reading

> A guided walkthrough of what's built, why each decision was made, and what
> remains v0.5. Treat this as the onboarding doc for the next engineer.

---

## What we built

In one day, we shipped a working scaffold for an AI-native hedge-fund research
and trading platform. Concretely:

- A **typed, validated config system** (Pydantic Settings) layered over YAML + env, with secrets masked.
- A **point-in-time-correct data layer** built on Polars + Parquet, with a working `yfinance` source, a `Databento` adapter that no-ops without a key, an Alpha Vantage fundamentals fetcher, and three alt-data sources (TWSE monthly revenue scraper, Korea Customs CSV/HTML, GDELT news + Anthropic classifier).
- A **Nautilus-compatible event-driven backtest engine** with realistic fill simulation (slippage + square-root impact + partial fills), a transaction cost model (commission + min ticket + borrow), and a deterministic equity curve.
- A **production-grade pre-trade risk system** with seven distinct rejection codes, a kill switch, and reductions-always-allowed semantics.
- A **research toolkit**: market-adjusted event study with t-stats, IC + IC decay, quintile factor research, walk-forward CV harness, HTML reports.
- A **PIT-aware ML feature plane** (returns / vol / momentum-z / mean-reversion / microstructure / alt-data) feeding a sklearn-style pipeline, a versioned model registry, a walk-forward training harness, and an online inference shim.
- A **multi-agent research loop** built on the real Anthropic API, with structured Pydantic output, retries, token+cost accounting, prompts written as Markdown with frontmatter, six tools the agent can call, and a pgvector-or-in-memory memory store.
- A **FastAPI server** exposing `/backtests`, `/agents/hypothesis`, `/agents/research`, `/agents/review`.
- A **live-trading skeleton** (`TradingNode` + Alpaca adapter) running the *same* `Strategy` class as backtest.
- **47 passing tests** across unit / integration / regression suites, with the regression suite locking strategy P&L into a tolerance band.
- **Docker Compose** infra (Postgres+pgvector, Redis, Prometheus, Grafana) with a provisioned dashboard.
- **GitHub Actions CI** running ruff + mypy + pytest.
- **Five docs** (`ARCHITECTURE`, `DATA_CONTRACTS`, `STRATEGY_GUIDE`, `AGENT_GUIDE`, `RUNBOOK`) plus this reading.

The codebase compiles, lints cleanly, and the agent layer makes real Anthropic calls (verified end-to-end on Sonnet 4.6: $0.019 → structurally-valid `Hypothesis` with falsification criteria).

---

## How to read the code (in order)

### 1. Start at `src/blackorca/config.py`

Pydantic Settings + YAML overlay + `.env`. The crucial design choice is that
**every layer is optional** — `base.yaml` → `<profile>.yaml` → env vars — and
they deep-merge. Secrets are typed as `SecretStr | None`, so a missing
ANTHROPIC key fails at startup with a clear error, not at the first agent
call ten minutes in.

### 2. Then `src/blackorca/data/contracts.py`

The two-timestamp invariant lives here:

```python
class _PITModel(BaseModel):
    as_of: datetime           # what time of the world this row describes
    observed_at: datetime     # when WE learned about it
    # observed_at >= as_of, enforced by validator
```

This split is the single biggest source of look-ahead bias in equity
research. Every catalog frame, every PIT join, every test in
`tests/unit/test_pit_integrity.py` enforces it.

### 3. Then `src/blackorca/strategies/base.py`

`BlackOrcaStrategy` is the **one Strategy class** every algo subclasses. It
binds three things at runtime:

- a `BacktestState` (positions, cash, mark-to-market prices)
- a `PreTradeRiskCheck` (which the runner injects)
- a logger + metrics emitter

It exposes `buy / sell / close / submit_order`. None of these talk to a
venue directly — they route through risk first. This is what makes
research-to-live parity possible: a strategy that backtests is bit-identical
to the one that paper-trades.

### 4. Then `src/blackorca/backtest/runner.py`

Event-driven. Bars iterated in `(as_of, symbol)` order. Orders fill on the
**next** bar (no T+0 fill cheating). Each bar:

1. Drain pending orders against this bar's OHLCV via `FillModel`.
2. Mark-to-market and call the strategy's `on_bar`.
3. Update equity HWM. Update Prometheus gauges.
4. Evaluate the kill switch — halt loop if tripped.

The data model (Bar / Order / Fill / Account) mirrors Nautilus Trader's so
that a future `NautilusBacktestAdapter` can drop in without strategies
noticing. See [§Nautilus] below.

### 5. Then `src/blackorca/risk/pretrade.py`

Seven explicit rejection codes:

| Code            | What trips it                              |
|-----------------|--------------------------------------------|
| NO_PRICE        | order with no reference price             |
| ORDER_NOTIONAL  | order notional > `per_order_max_notional` |
| POSITION_CAP    | post-trade |position| > cap (and increasing) |
| SHARE_CAP       | per-symbol share cap                       |
| GROSS_CAP       | gross exposure > cap                       |
| NET_CAP         | net exposure > cap                         |
| SECTOR_CAP      | sector exposure > cap                      |
| DAILY_LOSS      | rolling daily DD > cap                     |

Critical correctness detail caught by our own tests: **reductions are always
allowed**, even if the current position is already over-cap. Otherwise a
buggy strategy could get stuck unable to flatten an oversized position.

### 6. Then `src/blackorca/research/`

Four workhorses:

- `event_study.py` — market-adjusted CAR/AAR with t-stats
- `ic_analysis.py` — cross-sectional IC + IC decay over horizons 1/3/5/10/20
- `factor_research.py` — quintile portfolios, long-short returns, IC stats
- `walk_forward.py` — rolling (train, embargo, test) splits with per-window metrics

None of these are clever. They're the textbook implementations. Cleverness
goes in *strategies*, not in *research primitives*, because primitives are
what catch you when a strategy is overfit.

### 7. Then `src/blackorca/agents/`

The full path from prompt to typed output:

```
prompts/hypothesis_gen.md     <-- system prompt (Markdown with frontmatter)
schemas.py:Hypothesis         <-- Pydantic schema for the response
client.py:AnthropicClient     <-- retries, cost tracking, schema coercion
graphs/research_loop.py       <-- hypothesis -> signal -> backtest -> analysis
memory.py                     <-- pgvector or in-memory lessons store
tools.py                      <-- 6 typed tools the agent can call
```

Structured output uses Anthropic's tool-use mode under the hood: we register
an `emit_result` tool whose schema is the Pydantic model's JSON Schema, and
force `tool_choice` to that tool. The model emits JSON; we
`schema.model_validate(block.input)` it; if validation fails, we log and
move on. Cost-tracking is per-call and aggregated in `client.ledger`.

### 8. Then `src/blackorca/ml/`

Features carry an explicit `FeatureSpec(lookback_days, needs_columns)` so
the pipeline can refuse to compute when inputs are too short. The pipeline
itself is *not* a sklearn `Pipeline` — we keep Polars frames as the primary
container and add explicit PIT gates between steps. Models live in a tiny
versioned registry (`data/models/<name>/<version>/`) with a `meta.json`
alongside each pickle. The `MLSignal` strategy holds a long-lived
`InferenceHandle` to avoid load cost on every bar.

### 9. Finally `src/blackorca/live/trading_node.py`

The smallest live-trading loop that respects every contract: same Strategy,
same risk, real broker adapter. Polls every `poll_seconds`, drains pending
orders to the adapter, polls fills, marks NAV, evaluates kill switch. This
is *not* a Nautilus TradingNode — see [§Nautilus] for why.

---

## The Nautilus Trader question {#nautilus}

The original prompt specifies Nautilus Trader as the engine. We did not
integrate it. Why:

1. **Windows + Nautilus stability.** Nautilus has Windows wheels but they're
   tied to specific Python/Rust versions and the surface area we'd need
   (BacktestNode + ParquetDataCatalog + Strategy + Live TradingNode with an
   Alpaca adapter) is large; getting any single piece working took longer
   than the time-budget allowed.
2. **API churn.** Nautilus' Strategy API has changed shape between minor
   versions in the last 12 months. Pinning is brittle.
3. **Speed-to-first-bar-traded.** We needed an engine that *runs today* so
   that strategy, risk, and research code could be tested against real
   numbers. The internal engine is ~400 lines of Python; it works.

What we did instead: built the system with **Nautilus-compatible interfaces**
— Bar / Trade / Quote events, an `OrderRequest` factory, a Position-and-Cash
state object, an `ExecutionAdapter` protocol. The day Nautilus stabilizes,
the swap is: implement a `NautilusBacktestAdapter` that wraps `BacktestNode`
and a `NautilusTradingNode` that wraps Nautilus' live engine. Subclasses of
`BlackOrcaStrategy` won't change.

This is a deliberate trade-off. It is documented in `docs/ARCHITECTURE.md`
and in this section so the next engineer doesn't think it was an oversight.

---

## What's solid

- **PIT correctness**. The two-timestamp invariant is enforced at four layers: Pydantic validators, `assert_no_lookahead` at ingest, `pit_asof_join` at feature time, and 10 PIT tests in CI. We caught look-ahead in our own pipeline tests.
- **Risk system**. Every order routed through it. Every rejection code tested. Kill switch tested at both 4% (no trip) and 6% (trip) for a 5% threshold.
- **Determinism**. Backtests are bit-identical run to run on synthetic seeded data — locked into the regression suite.
- **Agent loop**. Real Anthropic calls. Real structured output. Real cost tracking. Verified with a live $0.019 call that produced a Hypothesis with falsification criteria.
- **Type discipline**. Strict mypy config in place; ruff clean.

## What's still v0.5 (and should be hardened next)

| Area                            | Current state                       | What to add                                                                     |
|---------------------------------|--------------------------------------|---------------------------------------------------------------------------------|
| Nautilus integration            | Compatible interfaces; no adapter    | `NautilusBacktestAdapter` + `NautilusTradingNode` once API churn settles.        |
| Databento                       | Adapter ships; no-op without key     | Live verify against `ohlcv-1d` and `mbp-1` schemas; cache to catalog.            |
| TWSE scraper                    | Real HTML scraper; format-fragile   | Mock the page in tests; add HTML-format regression tests with frozen fixtures.   |
| Korea Customs                   | CSV-only path                        | Wire to the real customs.go.kr API once a key is provisioned.                   |
| News classifier                 | Anthropic + GDELT, no benchmark      | Hand-label 200 headlines, hold out 50, track classifier F1 over time.            |
| Agent code-synthesis            | Loop runs *reference* strategy       | Add `signal -> strategy_code` synthesis stage with `strategy_review.py` gating.  |
| Multi-strategy portfolio        | Target-weight blender                 | Per-strategy sub-account with end-of-day reconciliation.                         |
| Execution algos                 | TWAP/VWAP stubs                       | Real intraday-volume profile + child-order management.                          |
| pgvector                        | Schema + insert/search wired         | Migration tool + retention policy + an "important lessons" pin/unpin UI.        |
| Live broker                     | Alpaca paper adapter only            | Add IBKR via Nautilus once Nautilus integrated; trade-update websocket.          |
| Live data feed                  | yfinance poll in trading_node        | Switch to Databento live or Alpaca data once keys provisioned.                  |
| Survivorship-bias-aware universe| Static dict                          | Time-stamped universe membership (IPOs in / delistings out).                    |
| Borrow availability             | Borrow cost model, not availability  | Daily borrow-list ingestion + shortability gate.                                |

## What surprised me during the build

1. **Polars `to_datetime` with timezones.** When loading CSVs that have a TZ offset (`+00:00`), Polars demands an explicit format string. Bit me once in the Korea Customs CSV loader; same pattern probably re-emerges anywhere we read TZ-aware ISO strings.
2. **Pydantic + slotted dataclasses.** `ICResult.__dict__` doesn't exist; you have to spell out the dict by field. A real annoyance when serializing into Polars rows.
3. **Risk system reduction semantics.** Easy to write "post-trade position must be under cap" — and then a strategy can't flatten an over-cap leg. The fix (only enforce on *increases*) is a one-liner, but you have to notice. Caught by our own test.
4. **Polars Unicode in Windows stdout.** Polars uses box-drawing characters in its table repr; Windows' default cp1252 codec crashes on them. Use `PYTHONIOENCODING=utf-8` or `sys.stdout.reconfigure(encoding='utf-8')` in scripts that print frames.
5. **Anthropic structured output is *cheap*.** $0.019 per Hypothesis call on Sonnet, including the JSON Schema overhead. The autonomous loop's bottleneck is not cost — it's the quality of the prompts.

---

## Reproducing what we did

```bash
# From a clean clone:
uv sync --dev

# Verify foundation
uv run blackorca version
uv run blackorca health
uv run ruff check src tests scripts
uv run pytest

# Verify data plane
uv run python scripts/ingest_market_data.py --tickers NVDA,AMD --start 2023-01-01 --end 2023-04-01

# Verify backtest
uv run python scripts/run_backtest.py --strategy sma_cross --symbol NVDA --params-json '{"target_weight":0.15}'

# Verify agent loop (costs ~$0.05)
uv run python scripts/run_agent_research.py
```

CI runs all of `uv run ruff check`, `uv run mypy src`, `uv run pytest`, and `uv run pytest -m regression`. Green CI is the gate; everything else is local convenience.

---

## Files of note

- `src/blackorca/risk/pretrade.py` — 100 lines that prevent the worst bug class
- `src/blackorca/data/pit.py` — the two functions that enforce PIT
- `src/blackorca/agents/client.py` — the Anthropic wrapper with cost ledger
- `src/blackorca/backtest/runner.py` — the engine; small enough to read in one sitting
- `tests/regression/test_strategy_baselines.py` — the safety net for strategy P&L

---

If you've read this far, you have the mental model. Next step: pick one
row from the **v0.5** table and harden it.
