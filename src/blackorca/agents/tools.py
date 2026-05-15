"""Tools the agent can call.

Each tool has a strict Pydantic input + output schema. Tools are *typed
function objects*, not just functions — this matters because the agent's
prompts reference them by name and the schemas are sent to the LLM verbatim.

In production, register the JSON schemas with the Anthropic ``tools=`` API.
For local LangGraph orchestration we wire them as Python callables.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

from blackorca.backtest.runner import run_backtest
from blackorca.config import get_settings
from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.logging import get_logger
from blackorca.research.event_study import run_event_study
from blackorca.research.ic_analysis import compute_ic
from blackorca.risk.limits import RiskLimits
from blackorca.strategies.registry import StrategyRegistry
from blackorca.universe.dependency_graph import DEPENDENCY_GRAPH, SupplierEdge
from blackorca.universe.semis import SEMI_UNIVERSE

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FetchDataInput(BaseModel):
    symbols: list[str]
    start: str
    end: str
    aggregation: str = "1d"


class FetchDataOutput(BaseModel):
    rows: int
    symbols: list[str]
    head_csv: str = Field(description="First 5 rows as CSV.")


class EventStudyInput(BaseModel):
    symbol: str
    event_dates: list[str]
    pre_window: int = 5
    post_window: int = 20


class EventStudyOutput(BaseModel):
    n_events: int
    aar_summary: str
    caar_summary: str


class BacktestInput(BaseModel):
    strategy_name: str
    symbol: str
    start: str
    end: str
    params: dict[str, Any] = Field(default_factory=dict)
    capital: float = 1_000_000


class BacktestOutput(BaseModel):
    metrics: dict[str, float]
    config: dict[str, Any]
    summary: str


class ICInput(BaseModel):
    horizon: int = 1


class ICOutput(BaseModel):
    horizon: int
    mean_ic: float
    rank_mean_ic: float
    ic_ir: float
    note: str


class DependencyQueryInput(BaseModel):
    upstream: str | None = None
    downstream: str | None = None
    min_confidence: float = 0.0


class DependencyQueryOutput(BaseModel):
    edges: list[str]   # serialized "upstream -> downstream (conf, lag)"


class ReadSourceInput(BaseModel):
    module: str = Field(description="dotted path e.g. blackorca.strategies.examples.sma_cross")


class ReadSourceOutput(BaseModel):
    module: str
    source: str


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def tool_fetch_data(arg: FetchDataInput) -> FetchDataOutput:
    cat = Catalog()
    df = cat.read_bars(
        arg.symbols,
        datetime.fromisoformat(arg.start),
        datetime.fromisoformat(arg.end),
        BarAggregation(arg.aggregation),
    )
    head_csv = df.head(5).write_csv() if not df.is_empty() else ""
    return FetchDataOutput(rows=df.height, symbols=arg.symbols, head_csv=head_csv)


def tool_run_event_study(arg: EventStudyInput) -> EventStudyOutput:
    cat = Catalog()
    df = cat.read_bars(
        [arg.symbol], datetime(1900, 1, 1), datetime(2099, 12, 31), BarAggregation.DAY
    )
    events = pl.DataFrame(
        {"symbol": [arg.symbol] * len(arg.event_dates), "event_date": [datetime.fromisoformat(d) for d in arg.event_dates]}
    )
    res = run_event_study(df, events, pre_window=arg.pre_window, post_window=arg.post_window)
    return EventStudyOutput(
        n_events=res.n_events,
        aar_summary=res.aar.write_csv() if not res.aar.is_empty() else "(empty)",
        caar_summary=res.caar.write_csv() if not res.caar.is_empty() else "(empty)",
    )


def tool_run_backtest(arg: BacktestInput) -> BacktestOutput:
    strat_cls = StrategyRegistry.get(arg.strategy_name)
    strat = strat_cls(symbol=arg.symbol, **arg.params)
    relaxed = RiskLimits(
        per_order_max_notional=arg.capital * 10,
        max_position_pct=0.50,
        max_gross_pct=2.0,
        max_net_pct=2.0,
    )
    cat = Catalog()
    result = run_backtest(
        strat,
        symbols=[arg.symbol],
        start=datetime.fromisoformat(arg.start),
        end=datetime.fromisoformat(arg.end),
        capital=arg.capital,
        catalog=cat,
        risk_limits=relaxed,
    )
    return BacktestOutput(
        metrics=result.metrics,
        config=result.config,
        summary=(
            f"Strategy {arg.strategy_name} on {arg.symbol}: "
            f"total_return={result.metrics.get('total_return',0):.2%} "
            f"sharpe={result.metrics.get('sharpe',0):.2f} "
            f"mdd={result.metrics.get('max_drawdown',0):.2%}"
        ),
    )


def tool_compute_ic(arg: ICInput) -> ICOutput:
    # This stub computes IC over a sentinel factor vs all catalog instruments.
    cat = Catalog()
    symbols = cat.list_instruments()
    if not symbols:
        return ICOutput(horizon=arg.horizon, mean_ic=0.0, rank_mean_ic=0.0, ic_ir=0.0, note="catalog empty")
    df = cat.read_bars(symbols, datetime(2000, 1, 1), datetime.now())
    factor = (
        df.sort(["symbol", "as_of"])
        .with_columns(value=-pl.col("close").pct_change().shift(1).over("symbol"))
        .drop_nulls("value")
        .select(["symbol", "as_of", "value"])
    )
    r = compute_ic(factor, df, horizon=arg.horizon)
    return ICOutput(
        horizon=r.horizon,
        mean_ic=r.mean_ic,
        rank_mean_ic=r.rank_mean_ic,
        ic_ir=r.ic_ir,
        note=f"computed over {len(symbols)} symbols",
    )


def tool_query_dependency_graph(arg: DependencyQueryInput) -> DependencyQueryOutput:
    edges: list[SupplierEdge] = [
        e
        for e in DEPENDENCY_GRAPH
        if (arg.upstream is None or e.upstream == arg.upstream)
        and (arg.downstream is None or e.downstream == arg.downstream)
        and e.confidence >= arg.min_confidence
    ]
    return DependencyQueryOutput(
        edges=[
            f"{e.upstream} -> {e.downstream} (conf={e.confidence:.2f}, lag={e.expected_lag_days}d, {e.relationship})"
            for e in edges
        ]
    )


def tool_read_strategy_source(arg: ReadSourceInput) -> ReadSourceOutput:
    settings = get_settings()
    parts = arg.module.split(".")
    p = settings.repo_root / "src" / Path(*parts).with_suffix(".py")
    if not p.exists():
        return ReadSourceOutput(module=arg.module, source=f"# not found: {p}")
    return ReadSourceOutput(module=arg.module, source=p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS = {
    "fetch_data": (FetchDataInput, FetchDataOutput, tool_fetch_data),
    "run_event_study": (EventStudyInput, EventStudyOutput, tool_run_event_study),
    "run_backtest": (BacktestInput, BacktestOutput, tool_run_backtest),
    "compute_ic": (ICInput, ICOutput, tool_compute_ic),
    "query_dependency_graph": (DependencyQueryInput, DependencyQueryOutput, tool_query_dependency_graph),
    "read_strategy_source": (ReadSourceInput, ReadSourceOutput, tool_read_strategy_source),
}


def list_universe() -> list[dict[str, str | int]]:
    return [
        {
            "symbol": s.symbol,
            "name": s.name,
            "tier": int(s.tier),
            "segment": s.segment,
            "country": s.country,
        }
        for s in SEMI_UNIVERSE
    ]


__all__ = [
    "TOOLS",
    "BacktestInput",
    "BacktestOutput",
    "DependencyQueryInput",
    "DependencyQueryOutput",
    "EventStudyInput",
    "EventStudyOutput",
    "FetchDataInput",
    "FetchDataOutput",
    "ICInput",
    "ICOutput",
    "ReadSourceInput",
    "ReadSourceOutput",
    "list_universe",
    "tool_compute_ic",
    "tool_fetch_data",
    "tool_query_dependency_graph",
    "tool_read_strategy_source",
    "tool_run_backtest",
    "tool_run_event_study",
]
