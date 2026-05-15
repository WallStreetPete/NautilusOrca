"""FastAPI app for internal services.

Endpoints:

- ``GET  /health``
- ``GET  /strategies``
- ``POST /backtests``        — run a backtest, return metrics
- ``POST /agents/hypothesis`` — generate a single hypothesis
- ``POST /agents/research``   — fire a bounded research loop
- ``POST /agents/review``     — code-review a strategy module
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from blackorca import __version__
from blackorca.agents.client import AnthropicClient
from blackorca.agents.graphs.research_loop import run_research_loop
from blackorca.agents.graphs.strategy_review import review_strategy
from blackorca.agents.schemas import Hypothesis
from blackorca.agents.tools import BacktestInput, tool_run_backtest
from blackorca.config import get_settings
from blackorca.logging import configure_logging, get_logger
from blackorca.strategies.registry import StrategyRegistry


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.logging.level, json=settings.logging.json_output)
    log = get_logger("server")

    app = FastAPI(title="Black Orca Capital", version=__version__)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "profile": settings.profile, "version": __version__}

    @app.get("/strategies")
    def strategies() -> dict[str, list[str]]:
        return {"strategies": StrategyRegistry.list_strategies()}

    @app.post("/backtests")
    def backtests(req: BacktestInput) -> dict[str, Any]:
        try:
            return tool_run_backtest(req).model_dump()
        except Exception as e:
            log.error("backtest.error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

    class HypothesisReq(BaseModel):
        universe_context: str

    @app.post("/agents/hypothesis")
    def hypothesis(req: HypothesisReq) -> dict[str, Any]:
        from pathlib import Path

        prompt = (
            Path(__file__).resolve().parent.parent / "agents/prompts/hypothesis_gen.md"
        ).read_text(encoding="utf-8")
        client = AnthropicClient()
        res = client.complete(system=prompt, prompt=req.universe_context, schema=Hypothesis)
        assert res.parsed is not None
        return {
            "hypothesis": res.parsed.model_dump(),
            "cost_usd": res.cost_usd,
            "tokens": {"in": res.input_tokens, "out": res.output_tokens},
        }

    class ResearchReq(BaseModel):
        universe_context: str
        max_iterations: int = 2
        fallback_strategy: str = "sma_cross"
        fallback_symbol: str = "NVDA"

    @app.post("/agents/research")
    def research(req: ResearchReq) -> dict[str, Any]:
        state = run_research_loop(
            universe_context=req.universe_context,
            max_iterations=req.max_iterations,
            fallback_strategy=req.fallback_strategy,
            fallback_symbol=req.fallback_symbol,
        )
        return {
            "iterations": state.iteration,
            "cost_usd": state.total_cost_usd,
            "hypothesis": state.hypothesis.model_dump() if state.hypothesis else None,
            "signal": state.signal.model_dump() if state.signal else None,
            "metrics": state.backtest["metrics"] if state.backtest else None,
            "analysis": state.analysis.model_dump() if state.analysis else None,
            "recommendation": state.final_recommendation,
        }

    class ReviewReq(BaseModel):
        module: str

    @app.post("/agents/review")
    def review(req: ReviewReq) -> dict[str, Any]:
        return review_strategy(req.module).model_dump()

    return app


app = create_app()
