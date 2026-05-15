# Black Orca Capital — Apex Research Platform

AI-native hedge fund research & trading platform. Backtest, paper, and live use **identical** Strategy code paths; every data row is point-in-time correct; risk and execution are interface-driven; agents drive the research loop end-to-end.

> Status: **Phase 0 → 8 scaffolded in one pass**. See `docs/READING.md` for the full guided tour.

---

## Quickstart

```bash
# 1. Install
uv sync --all-extras --dev

# 2. Configure
cp .env.example .env       # then fill in keys

# 3. Sanity check
uv run blackorca version
uv run blackorca health
uv run pytest -m "not live and not integration"

# 4. First backtest (no API keys needed — uses yfinance)
uv run python scripts/ingest_market_data.py --tickers NVDA,AMD --start 2020-01-01
uv run python scripts/run_backtest.py --strategy sma_cross --symbol NVDA
```

## Architecture at a glance

```
                         ┌──────────────────┐
                         │  Agent Loop      │
                         │ (LangGraph +     │
                         │  Anthropic API)  │
                         └────────┬─────────┘
                                  │ proposes hypotheses, reviews code
                                  ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────────┐
│  Data    │→ │  Features  │→ │  Strategy    │→ │  Execution   │
│  (PIT)   │  │  (PIT)     │  │  (one class) │  │ (sim|paper|  │
│ Polars   │  │ sklearn    │  │ + Risk gate  │  │  live)       │
│ Parquet  │  │ pipelines  │  │              │  │              │
└──────────┘  └────────────┘  └──────────────┘  └──────────────┘
       ▲              ▲              ▲                 ▲
       │              │              │                 │
       └──── structlog + prometheus + opentelemetry ───┘
```

Every strategy implements the same `BlackOrcaStrategy` interface. The backtest engine is event-driven and Nautilus-compatible in design so a `nautilus_trader` adapter can drop in later without changing strategies.

## Repository layout

See `docs/ARCHITECTURE.md` for the canonical tour. Top-level:

```
src/blackorca/
  config.py logging.py metrics.py cli.py
  data/        contracts, sources (yfinance, databento, alt-data), catalog, PIT
  universe/    semi basket, supplier dependency graph
  research/    event study, IC, factor research, walk-forward
  ml/          PIT-aware features, sklearn pipelines, model registry, training
  strategies/  base class, registry, examples
  risk/        limits, pre-trade checks, kill switch
  execution/   simulated and live broker adapters
  backtest/    event-driven engine, fill model, costs, analyzer
  agents/      Anthropic client, prompts, tools, LangGraph graphs
  server/      FastAPI app
  live/        paper / live trading entrypoints
```

## Operating principles (do not violate)

1. Research-to-live parity — no `if backtest: ...` branches in strategies.
2. PIT by construction. `as_of` is a first-class column.
3. Strict mypy + ruff at the boundary; messy notebooks fine inside `notebooks/`.
4. Tests cover the things that lose money: risk, PIT, fills, position sizing.
5. Observability from minute zero.

## Tests

```bash
uv run pytest                   # all
uv run pytest -m "not live"     # skip live-API tests
uv run pytest -m regression     # P&L baseline regression
```

## Phase status

| Phase | Scope                                | Status |
|------:|--------------------------------------|:------:|
| 0     | Foundation                           |   ✅   |
| 1     | Data plane                           |   ✅   |
| 2     | Strategy / Backtest / Risk           |   ✅   |
| 3     | Research + walk-forward              |   ✅   |
| 4     | Agentic research layer               |   ✅   |
| 5     | ML feature plane                     |   ✅   |
| 6     | Alt-data ingestion                   |   ✅   |
| 7     | Paper trading scaffold               |   ✅   |
| 8     | Hardening / regression / docs        |   ✅   |

See `docs/READING.md` for the comprehensive guided walkthrough.
