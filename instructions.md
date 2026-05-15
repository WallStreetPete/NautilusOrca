# Black Orca Capital — Apex Research Platform Build

You are building the foundational research and trading platform for **Black Orca Capital**, an AI-native hedge fund. This is real production infrastructure, not a tutorial project. Code quality, architectural decisions, and design discipline matter.

The platform must serve three concurrent goals over the next 90 days:
1. **Trade real capital** — starting paper, then live
2. **Generate track record and IP** — for LP pitches
3. **Validate the Apex multi-agent thesis** — empirically

---

## Operating Principles

Before writing any code, internalize these:

1. **Research-to-live parity is non-negotiable.** Every Strategy class must run identically in backtest, paper, and live. No code paths that diverge between modes.

2. **Point-in-time correctness is non-negotiable.** Every data row carries an `as_of` timestamp. No look-ahead bias is possible by construction, not by convention.

3. **Production interfaces, research internals.** Strategy, data, risk, and execution interfaces are designed as if they'll run real capital tomorrow. Notebooks and exploratory scripts can be messy. Don't confuse the two.

4. **Pluggable from day one, but don't over-abstract.** Data sources, brokers, model frameworks, and agent backends are swappable via clean interfaces. No premature factory patterns or plugin systems for needs that don't exist.

5. **Local-first, cloud-ready.** Everything runs on a local workstation today. Use containerization, env-driven config, and S3-compatible paths so a lift-and-shift to AWS later is trivial. Don't pay AWS rent now.

6. **Polars > pandas everywhere practical.** DuckDB for ad-hoc SQL. NumPy/Numba for hot loops. PyArrow Parquet for storage.

7. **Type everything.** Strict mypy. Pydantic for config and data contracts. Runtime validation at module boundaries.

8. **Test the things that would lose money if broken.** Risk system, position sizing, point-in-time data integrity, fill simulation. Don't test toy strategies.

9. **Observability from day one.** Structured logging (structlog), metrics (Prometheus-compatible), traces where useful. The day you trade real money, you need to know what's happening.

10. **No magic.** When in doubt, write explicit code. Save cleverness for places it actually pays off.

---

## Tech Stack

- **Python 3.12**, managed by **uv**
- **Nautilus Trader** as the trading engine (backtest, paper, live)
- **Polars + DuckDB + PyArrow** as the data layer
- **Anthropic API** (`claude-opus-4-7`, `claude-sonnet-4-6`) for agent layer
- **LangGraph** for agent orchestration
- **scikit-learn, LightGBM, XGBoost** for classical ML; **PyTorch** for deep learning (lazy import, only when used)
- **pgvector** (via Docker Postgres) for embedding storage
- **Alpaca-py** for initial paper/live broker (IBKR adapter via Nautilus comes later)
- **Databento** as the primary historical/live market data source (with yfinance fallback for free dev)
- **FastAPI** for internal services (agent server, dashboard backend)
- **Structlog, Prometheus client, OpenTelemetry** for observability
- **Docker Compose** for local infra (Postgres+pgvector, Redis, Prometheus, Grafana)
- **Ruff, mypy --strict, pytest, pytest-asyncio**
- **GitHub Actions** for CI

---

## Repository Structure

```
blackorca/
├── pyproject.toml
├── uv.lock
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml          # Postgres+pgvector, Redis, Prometheus, Grafana
├── Dockerfile                  # Production image for the trading node
├── .github/workflows/
│   └── ci.yml                  # ruff, mypy, pytest, backtest regression suite
├── config/
│   ├── base.yaml               # Default config
│   ├── dev.yaml                # Local development
│   ├── paper.yaml              # Paper trading
│   └── live.yaml               # Live trading (gitignored secrets)
├── src/blackorca/
│   ├── __init__.py
│   ├── config.py               # Pydantic Settings, env-driven
│   ├── logging.py              # Structlog setup
│   ├── metrics.py              # Prometheus metrics
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── contracts.py        # Pydantic schemas for all data types
│   │   ├── sources/
│   │   │   ├── base.py         # Abstract DataSource
│   │   │   ├── databento.py    # Primary market data
│   │   │   ├── yfinance.py     # Free fallback
│   │   │   ├── al
│   │   │   │   ├── base.py     # AltDataSource interface
│   │   │   │   ├── taiwan_twse.py    # Monthly revenue scraper
│   │   │   │   ├── korea_customs.py  # 10-day export prelims
│   │   │   │   └── news.py     # News NLP ingestion
│   │   │   └── fundamentals.py # Point-in-time fundamentals (Sharadar interface)
│   │   ├── catalog.py          # Nautilus ParquetDataCatalog wrapper
│   │   ├── ingest.py           # Orchestration
│   │   └── pit.py              # Point-in-time integrity checks
│   │
│   ├── universe/
│   │   ├── __init__.py
│   │   ├── semis.py            # Semi basket with tier/sub-segment metadata
│   │   └── dependency_graph.py # Supplier relationships for transmission lag strategy
│   │
│   ├── research/
│   │   ├── __init__.py
│   │   ├── event_study.py      # Standard event study framework
│   │   ├── ic_analysis.py      # IC, IC decay, rank IC
│   │   ├── factor_research.py  # Cross-sectional factor analysis
│   │   ├── walk_forward.py     # Walk-forward validation harness
│   │   └── reports.py          # Standardized HTML/PDF reports
│   │
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── features/
│   │   │   ├── base.py         # Feature interface; point-in-time aware
│   │   │   ├── price.py        # Returns, vol, momentum at multiple horizons
│   │   │   ├── microstructure.py  # Volume, spread proxies
│   │   │   └── altdata.py      # Features from alt-data sources
│   │   ├── pipelines.py        # sklearn-style Pipeline with PIT discipline
│   │   ├── models.py           # Model registry
│   │   ├── train.py            # Training harness with walk-forward CV
│   │   └── inference.py        # Online inference for Strategies
│   │
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py             # BlackOrcaStrategy(Strategy): sizing, risk, logging
│   │   ├── registry.py         # Strategy registration and discovery
│   │   ├── examples/
│   │   │   ├── sma_cross.py    # Reference: SMA cross
│   │   │   ├── supply_chain_lag.py  # Tier-1 catalyst → tier-2 drift
│   │   │   └── ml_signal.py    # Wraps an ML model as a strategy
│   │   └── portfolio.py        # Multi-strategy portfolio combiner
│   │
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── limits.py           # Position, gross/net, sector, drawdown limits
│   │   ├── pretrade.py         # Pre-trade risk checks (every order)
│   │   └── kill_switch.py      # Hard stops, exposure circuit breakers
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── adapters/
│   │   │   ├── alpaca.py       # Paper + live via Alpaca
│   │   │   └── nautilus_sim.py # Simulated venue for backtest
│   │   └── algos.py            # Execution algorithms (TWAP, VWAP scaffolds)
│   │
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── runner.py           # BacktestNode wrapper
│   │   ├── fills.py            # Realistic fill model (slippage, impact)
│   │   ├── costs.py            # Transaction cost model (commissions, borrow)
│   │   └── analyzer.py         # Tearsheet generation
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── client.py           # Anthropic API client wrapper
│   │   ├── prompts/
│   │   │   ├── hypothesis_gen.md
│   │   │   ├── code_review.md
│   │   │   ├── backtest_analyst.md
│   │   │   └── signal_proposer.md
│   │   ├── graphs/
│   │   │   ├── research_loop.py  # LangGraph: hypothesis → backtest → analysis → iterate
│   │   │   └── strategy_review.py # LangGraph: review proposed strategy code
│   │   ├── memory.py           # pgvector-backed lesson storage
│   │   └── tools.py            # Tools the agent can call (run_backtest, fetch_data, etc.)
│   │
│   ├── server/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app
│   │   └── routes/
│   │       ├── agents.py       # Agent invocations
│   │       ├── backtests.py    # Backtest CRUD
│   │       └── strategies.py   # Strategy management
│   │
│   └── live/
│       ├── __init__.py
│       ├── trading_node.py     # Nautilus TradingNode setup
│       └── paper.py            # Paper trading entrypoint
│
├── notebooks/
│   ├── 01_first_backtest.ipynb
│   ├── 02_event_study_template.ipynb
│   ├── 03_factor_research_template.ipynb
│   ├── 04_walk_forward_demo.ipynb
│   └── 05_agent_research_loop_demo.ipynb
│
├── scripts/
│   ├── ingest_market_data.py
│   ├── ingest_alt_data.py
│   ├── build_catalog.py
│   ├── run_backtest.py
│   ├── run_walk_forward.py
│   ├── train_model.py
│   ├── run_agent_research.py
│   └── start_paper_trading.py
│
├── tests/
│   ├── unit/
│   │   ├── test_pit_integrity.py
│   │   ├── test_risk_limits.py
│   │   ├── test_position_sizing.py
│   │   └── test_fill_model.py
│   ├── integration/
│   │   ├── test_backtest_end_to_end.py
│   │   └── test_paper_trading_smoke.py
│   └── regression/
│       └── test_strategy_baselines.py  # Catches strategy P&L regressions
│
└── docs/
    ├── ARCHITECTURE.md
    ├── DATA_CONTRACTS.md
    ├── STRATEGY_GUIDE.md
    ├── AGENT_GUIDE.md
    └── RUNBOOK.md              # Ops procedures for paper/live trading
```

---

## Execution Phases

Execute these in order. **Stop after each phase, report what was built, and wait for confirmation before proceeding.** Do not build all phases in one pass.

---

### Phase 0 — Foundation (must work before anything else)

- `pyproject.toml` with all dependencies, dev dependencies, ruff and mypy configuration (strict), pytest configuration
- `docker-compose.yml` with Postgres+pgvector, Redis, Prometheus, Grafana
- `.env.example`, `config/base.yaml`, `config/dev.yaml`
- `src/blackorca/config.py` (Pydantic Settings, env-driven, validates on startup)
- `src/blackorca/logging.py` (structlog with JSON output)
- `src/blackorca/metrics.py` (Prometheus client setup)
- `.github/workflows/ci.yml` running ruff + mypy --strict + pytest
- `README.md` with setup, architecture overview, phase status
- `docs/ARCHITECTURE.md` with diagrams (text-based, mermaid)
- Empty package directories with `__init__.py` matching the structure above

**Verify:** `uv sync` succeeds, `docker compose up -d` brings up infra, `uv run pytest` passes (with zero tests), `uv run mypy src/` passes, `uv run ruff check` passes.

**STOP. Report status. Wait for confirmation.**

---

### Phase 1 — Data plane

- `src/blackorca/data/contracts.py`: Pydantic schemas for `BarData`, `TradeData`, `QuoteData`, `FundamentalData`, `AltDataPoint`, `NewsItem`. Every type carries `as_of` and `observed_at` timestamps.
- `src/blackorca/data/sources/base.py`: Abstract `MarketDataSource` and `AltDataSource` interfaces
- `src/blackorca/data/sources/yfinance.py`: Working implementation, daily bars, handles MultiIndex pitfalls, timezone-aware
- `src/blackorca/data/sources/databento.py`: Working implementation if `DATABENTO_API_KEY` is set, gracefully no-op otherwise. Supports `XNAS.ITCH` (equities) and `OPRA` (options) schemas at minimum.
- `src/blackorca/data/catalog.py`: Wraps `ParquetDataCatalog`, exposes `write_bars()`, `read_bars()`, `list_instruments()`. Configurable storage backend (local path or `s3://` URI).
- `src/blackorca/data/pit.py`: Validation functions that fail loudly on any look-ahead. Used in tests and at ingestion.
- `src/blackorca/universe/semis.py`: ~25 ticker basket with metadata: tier (1/2/3), sub-segment (logic/memory/equipment/IP/optical/SiC/photomask), avg ADV, market cap bucket.
- `src/blackorca/universe/dependency_graph.py`: Static dict mapping tier-1 catalysts to tier-2/3 affected names (NVDA → CoWoS suppliers, TSM → photomask, etc.). Include rationale comments per edge.
- `scripts/ingest_market_data.py`, `scripts/build_catalog.py`: Working CLI commands.
- `tests/unit/test_pit_integrity.py`: Tests that detect look-ahead bias in fixture data.

**Verify:** Can ingest 5 years of daily bars for the semi universe from yfinance, write to ParquetDataCatalog, read back identically, PIT tests pass.

**STOP. Report status. Wait for confirmation.**

---

### Phase 2 — Strategy + Backtest + Risk

- `src/blackorca/strategies/base.py`: `BlackOrcaStrategy(Strategy)` with built-in position sizing helpers, risk-aware order submission, standardized logging, metric emission.
- `src/blackorca/strategies/registry.py`: Decorator-based strategy registration.
- `src/blackorca/strategies/examples/sma_cross.py`: Reference implementation.
- `src/blackorca/risk/limits.py`: `RiskLimits` config (max position size, max gross, max net, max sector exposure, max daily loss, max drawdown). Per-strategy and portfolio-level.
- `src/blackorca/risk/pretrade.py`: `PreTradeRiskCheck` that intercepts every order. Rejects with reason if any limit violated.
- `src/blackorca/risk/kill_switch.py`: Drawdown-triggered halt, exposure circuit breaker.
- `src/blackorca/backtest/fills.py`: Fill model with configurable slippage (basis points), market impact (square-root model), partial fills.
- `src/blackorca/backtest/costs.py`: Commission model (per-share + min ticket), borrow cost for shorts, financing.
- `src/blackorca/backtest/runner.py`: `run_backtest(strategy_config, universe, start, end, capital) -> BacktestResult`. Uses high-level Nautilus API.
- `src/blackorca/backtest/analyzer.py`: Tearsheet with total return, annualized return, Sharpe, Sortino, max DD, Calmar, hit rate, profit factor, average win/loss, trade duration distribution, exposure histogram.
- `tests/unit/test_risk_limits.py`, `tests/unit/test_position_sizing.py`, `tests/unit/test_fill_model.py`: Real tests.
- `tests/integration/test_backtest_end_to_end.py`: SMA cross runs cleanly, produces deterministic results.
- `notebooks/01_first_backtest.ipynb`: Working demo.

**Verify:** SMA cross backtest on NVDA 2020-2024 runs, produces tearsheet, risk limits actively reject orders in tests, fill model produces realistic slippage.

**STOP. Report status. Wait for confirmation.**

---

### Phase 3 — Research plane + Walk-forward

- `src/blackorca/research/event_study.py`: Standard CAR/AAR methodology, configurable event window, statistical tests, plotting helpers.
- `src/blackorca/research/ic_analysis.py`: IC, rank IC, IC decay over horizons 1/3/5/10/20 days.
- `src/blackorca/research/factor_research.py`: Cross-sectional factor framework. Inputs: factor values + forward returns. Outputs: quintile portfolios, factor returns, IC stats.
- `src/blackorca/research/walk_forward.py`: Walk-forward CV harness. Configurable train/test/embargo windows. Runs across parameter grids. Produces stability statistics (does the strategy work in all sub-periods, or only some?).
- `src/blackorca/research/reports.py`: HTML report generation for research artifacts.
- `src/blackorca/strategies/examples/supply_chain_lag.py`: Real implementation of the tier-1 catalyst → tier-2 drift strategy using the dependency graph.
- `src/blackorca/strategies/portfolio.py`: Multi-strategy portfolio combiner with position netting, capital allocation, correlation-aware risk budgeting.
- `notebooks/02_event_study_template.ipynb`, `03_factor_research_template.ipynb`, `04_walk_forward_demo.ipynb`: Working templates.
- `scripts/run_walk_forward.py`: CLI for walk-forward studies.

**Verify:** Walk-forward run on SMA cross produces stability stats. Event study on NVDA earnings produces sensible CAR curves. Supply chain lag strategy runs end-to-end.

**STOP. Report status. Wait for confirmation.**

---

### Phase 4 — Agentic research layer

- `src/blackorca/agents/client.py`: Anthropic API wrapper with structured output support, retry logic, token accounting, cost tracking. Supports both `claude-opus-4-7` and `claude-sonnet-4-6`.
- `src/blackorca/agents/prompts/`: Production prompts for each agent role. Markdown with frontmatter for metadata. Each prompt is a real, well-crafted prompt — not a stub.
  - `hypothesis_gen.md`: Generates trading hypotheses given a universe and market context. Output is structured (hypothesis statement, mechanism, testable prediction, required data, estimated edge).
  - `code_review.md`: Reviews proposed strategy code for bugs, look-ahead bias, risk issues, and Apex coding standards adherence.
  - `backtest_analyst.md`: Given a backtest result, identifies suspicious patterns (overfit signatures, regime dependence, outlier-driven results) and proposes follow-up tests.
  - `signal_proposer.md`: Given a hypothesis, proposes concrete signal definitions with data sources and feature engineering steps.
- `src/blackorca/agents/tools.py`: Tools the agent can call: `run_event_study`, `run_backtest`, `compute_ic`, `fetch_data`, `query_dependency_graph`, `read_strategy_source`. Each tool has a strict Pydantic input/output schema.
- `src/blackorca/agents/memory.py`: pgvector-backed storage for "lessons learned." Embeds hypothesis + result + analysis. Retrieves similar past experiments before proposing new ones.
- `src/blackorca/agents/graphs/research_loop.py`: LangGraph orchestration: hypothesis → signal proposal → backtest → analysis → either accept/reject/iterate. Includes human-in-the-loop checkpoint nodes.
- `src/blackorca/agents/graphs/strategy_review.py`: LangGraph orchestration for code review.
- `src/blackorca/server/app.py`, `src/blackorca/server/routes/agents.py`: FastAPI endpoints for invoking agent flows.
- `notebooks/05_agent_research_loop_demo.ipynb`: Demo of full research loop on a single hypothesis.
- `scripts/run_agent_research.py`: CLI for kicking off an autonomous research run with bounded budget.

**Verify:** Agent loop produces a valid hypothesis, generates strategy code that passes code review, runs through a backtest, and produces a written analysis. Cost per loop tracked and bounded.

**STOP. Report status. Wait for confirmation.**

---

### Phase 5 — ML feature plane

- `src/blackorca/ml/features/base.py`: `Feature` interface with mandatory `as_of` propagation. No feature can ever look at a future timestamp.
- `src/blackorca/ml/features/price.py`: Returns at horizons {1,3,5,10,20,60} days, realized vol, momentum, mean-reversion z-scores.
- `src/blackorca/ml/features/microstructure.py`: Volume profile, dollar volume, ADV ratios, gap statistics.
- `src/blackorca/ml/features/altdata.py`: Features derived from Taiwan revenue YoY surprises, Korea export YoY, news sentiment scores.
- `src/blackorca/ml/pipelines.py`: PIT-aware sklearn-compatible pipeline. Refuses to fit on data that violates PIT.
- `src/blackorca/ml/models.py`: Model registry. LightGBM and ridge as primary v1 models. Versioned model artifacts in `data/models/`.
- `src/blackorca/ml/train.py`: Training harness with walk-forward CV, hyperparameter sweeps, leakage detection.
- `src/blackorca/ml/inference.py`: Online inference inside Strategies. Strict latency budget.
- `src/blackorca/strategies/examples/ml_signal.py`: Strategy that wraps a trained model.
- `scripts/train_model.py`: CLI.

**Verify:** Train a LightGBM model on engineered features, predict 1-day forward returns, walk-forward CV produces stable IC, strategy wrapping the model backtests successfully.

**STOP. Report status. Wait for confirmation.**

---

### Phase 6 — Alt-data ingestion (v0.5 — scaffolds with real first source)

- `src/blackorca/data/sources/alt/base.py`: `AltDataSource` interface.
- `src/blackorca/data/sources/alt/taiwan_twse.py`: Real working scraper for monthly revenue announcements from TWSE. Includes TSMC, UMC, MediaTek, ASE. Handles the release schedule.
- `src/blackorca/data/sources/alt/korea_customs.py`: Real working ingestion for Korea customs 10-day export prelims (semiconductors line item).
- `src/blackorca/data/sources/alt/news.py`: Scaffold for news ingestion + Anthropic-powered NLP classification. Wire up to one free source (e.g., GDELT or a free RSS) as a working v0.
- `scripts/ingest_alt_data.py`: CLI for alt-data refresh.
- Integration with Phase 5 alt-data features.

**Verify:** Successfully ingest current Taiwan revenue data, current Korea export data. News NLP runs on sample text and produces classifications.

**STOP. Report status. Wait for confirmation.**

---

### Phase 7 — Live paper trading

- `src/blackorca/execution/adapters/alpaca.py`: Alpaca paper trading adapter compatible with Nautilus live engine.
- `src/blackorca/live/trading_node.py`: Nautilus TradingNode configuration.
- `src/blackorca/live/paper.py`: Paper trading entrypoint with full risk system active.
- `scripts/start_paper_trading.py`: CLI to launch paper trading.
- `docs/RUNBOOK.md`: Operational procedures — startup checks, monitoring, kill-switch usage, post-mortem template.
- `tests/integration/test_paper_trading_smoke.py`: Smoke test that paper trading starts, places a small test order, receives a fill, properly accounts position.

**Verify:** Paper trading runs end-to-end with the SMA cross strategy on a small universe, all risk checks active, metrics flowing to Prometheus, logs queryable.

**STOP. Report status. Wait for confirmation.**

---

### Phase 8 — Hardening

- Regression test suite: `tests/regression/test_strategy_baselines.py` locks in the expected Sharpe/return/MaxDD for each reference strategy. CI fails if a PR changes these unintentionally.
- Grafana dashboard JSON committed to `infra/grafana/` for: P&L, exposures, agent activity, data ingestion health, backtest run history.
- `docs/STRATEGY_GUIDE.md`: How to add a new strategy.
- `docs/AGENT_GUIDE.md`: How to design new agent prompts and tools.
- `docs/DATA_CONTRACTS.md`: Authoritative reference for all data schemas.

**Verify:** CI is fully green. Documentation is complete enough that someone else could onboard.

---

## Final Notes

- After each phase, run the full test suite, mypy, and ruff. Do not proceed if any are broken.
- If you discover the prompt is wrong or under-specified during a phase, flag it explicitly and propose the fix before implementing your interpretation.
- If a dependency choice in this prompt is meaningfully suboptimal given current state of the ecosystem, raise it before building. (Example: if there's a newer or better-maintained alternative to a library I listed, say so.)
- Prefer asking one good clarifying question over building the wrong thing.
- After Phase 8, produce a written assessment: what's solid, what's still v0.5 and should be hardened next, what surprised you during the build.

**Begin with Phase 0.**