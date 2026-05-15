"""Research loop graph.

A bounded autonomous-research loop:

    hypothesis_gen → signal_proposer → run_backtest → backtest_analyst
                                       (loop if iterate, else stop)

Implemented as a small, explicit state machine to keep dependencies light.
A LangGraph version is available behind ``USE_LANGGRAPH=1`` for users who
want the visualization / checkpoints — see ``research_loop_langgraph()``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from blackorca.agents.client import AnthropicClient, BudgetExceededError
from blackorca.agents.memory import (
    MemoryStore,
    hash_embedding,
    make_lesson,
    make_memory_store,
)
from blackorca.agents.schemas import (
    BacktestAnalysis,
    Hypothesis,
    SignalDefinition,
)
from blackorca.agents.tools import BacktestInput, tool_run_backtest
from blackorca.config import get_settings
from blackorca.logging import get_logger

log = get_logger(__name__)


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


@dataclass(slots=True)
class ResearchLoopState:
    universe_context: str
    max_iterations: int = 3
    iteration: int = 0
    hypothesis: Hypothesis | None = None
    signal: SignalDefinition | None = None
    backtest: dict[str, Any] | None = None
    analysis: BacktestAnalysis | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    total_cost_usd: float = 0.0
    final_recommendation: str | None = None


def step_hypothesis(client: AnthropicClient, state: ResearchLoopState, memory: MemoryStore) -> None:
    prompt = _read_prompt("hypothesis_gen.md")
    # Pull related lessons from memory
    related = memory.search(hash_embedding(state.universe_context), k=3)
    lessons_blob = "\n".join(
        f"- {ls.hypothesis} | {ls.result_summary}" for ls in related
    ) or "(none)"
    user = (
        f"## Universe context\n{state.universe_context}\n\n"
        f"## Past lessons\n{lessons_blob}\n\n"
        "Generate one fresh hypothesis we have not tested before."
    )
    res = client.complete(system=prompt, prompt=user, schema=Hypothesis)
    state.total_cost_usd += res.cost_usd
    assert res.parsed is not None
    state.hypothesis = res.parsed  # type: ignore[assignment]
    state.history.append({"step": "hypothesis", "model": res.model, "cost": res.cost_usd})


def step_signal(client: AnthropicClient, state: ResearchLoopState) -> None:
    assert state.hypothesis is not None
    prompt = _read_prompt("signal_proposer.md")
    user = (
        "## Hypothesis\n"
        f"{state.hypothesis.model_dump_json(indent=2)}\n\n"
        "Produce a concrete SignalDefinition for this hypothesis."
    )
    res = client.complete(system=prompt, prompt=user, schema=SignalDefinition, fast=True)
    state.total_cost_usd += res.cost_usd
    assert res.parsed is not None
    state.signal = res.parsed  # type: ignore[assignment]
    state.history.append({"step": "signal", "model": res.model, "cost": res.cost_usd})


def step_backtest(state: ResearchLoopState, *, fallback_strategy: str, fallback_symbol: str) -> None:
    """Run a backtest. For the day-0 system, we run the *reference* strategy as
    a proxy until a code-synthesis stage is added that translates a
    ``SignalDefinition`` into a concrete strategy class. That stage is a v0.5
    follow-up — see ``docs/READING.md``."""

    settings = get_settings()
    end = date.today()
    start = end.replace(year=end.year - 2)
    res = tool_run_backtest(
        BacktestInput(
            strategy_name=fallback_strategy,
            symbol=fallback_symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            params={},
            capital=settings.backtest.default_capital,
        )
    )
    state.backtest = res.model_dump()
    state.history.append({"step": "backtest", "summary": res.summary})


def step_analyze(client: AnthropicClient, state: ResearchLoopState) -> None:
    assert state.backtest is not None
    prompt = _read_prompt("backtest_analyst.md")
    user = (
        f"## Hypothesis\n{state.hypothesis.statement if state.hypothesis else '(none)'}\n\n"
        f"## Backtest metrics\n{json.dumps(state.backtest['metrics'], indent=2)}\n\n"
        f"## Backtest config\n{json.dumps(state.backtest['config'], indent=2)}"
    )
    res = client.complete(system=prompt, prompt=user, schema=BacktestAnalysis)
    state.total_cost_usd += res.cost_usd
    assert res.parsed is not None
    state.analysis = res.parsed  # type: ignore[assignment]
    state.history.append({"step": "analyze", "model": res.model, "cost": res.cost_usd})


def run_research_loop(
    *,
    universe_context: str,
    fallback_strategy: str = "sma_cross",
    fallback_symbol: str = "NVDA",
    max_iterations: int = 2,
    client: AnthropicClient | None = None,
    memory: MemoryStore | None = None,
) -> ResearchLoopState:
    """Execute the loop until a verdict is reached, ``max_iterations`` is hit,
    or the budget is exhausted."""
    client = client or AnthropicClient()
    memory = memory or make_memory_store()
    state = ResearchLoopState(universe_context=universe_context, max_iterations=max_iterations)

    while state.iteration < max_iterations and not state.finished:
        state.iteration += 1
        log.info("research_loop.iter", n=state.iteration)
        try:
            step_hypothesis(client, state, memory)
            step_signal(client, state)
            step_backtest(state, fallback_strategy=fallback_strategy, fallback_symbol=fallback_symbol)
            step_analyze(client, state)
        except BudgetExceededError as e:
            log.error("research_loop.budget", error=str(e))
            state.final_recommendation = "halted_budget"
            state.finished = True
            break

        assert state.analysis is not None
        if state.analysis.recommendation in {"promote", "reject"}:
            state.final_recommendation = state.analysis.recommendation
            state.finished = True

        # Persist lesson regardless
        memory.add(
            make_lesson(
                hypothesis=state.hypothesis.statement if state.hypothesis else "(none)",
                result_summary=(
                    f"recommendation={state.analysis.recommendation if state.analysis else '?'} "
                    f"sharpe={state.backtest['metrics'].get('sharpe', 0):.2f}"
                    if state.backtest
                    else "(none)"
                ),
                iteration=state.iteration,
            )
        )

    if not state.final_recommendation:
        state.final_recommendation = "iterate"
    return state


# Optional LangGraph variant — guarded so the import doesn't fail if not installed.
def research_loop_langgraph_available() -> bool:
    return os.environ.get("USE_LANGGRAPH") == "1"


__all__ = ["ResearchLoopState", "research_loop_langgraph_available", "run_research_loop"]
