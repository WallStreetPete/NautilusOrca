"""CLI: kick off a bounded autonomous research run."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from blackorca.agents.graphs.research_loop import run_research_loop
from blackorca.logging import configure_logging

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def main(
    context: Annotated[
        str,
        typer.Option(
            help="Universe context blob to seed the agent.",
        ),
    ] = (
        "Universe: US semiconductors. ~25 names spanning tier-1 (NVDA, TSM, AMD), "
        "equipment (AMAT, LRCX, KLAC, ASML), memory (MU), and a long tail of "
        "tier-2/3 suppliers. We have daily bars in the catalog and a curated "
        "supplier dependency graph available via the query_dependency_graph tool."
    ),
    max_iterations: Annotated[int, typer.Option()] = 1,
    fallback_strategy: Annotated[str, typer.Option()] = "sma_cross",
    fallback_symbol: Annotated[str, typer.Option()] = "NVDA",
) -> None:
    configure_logging(level="INFO", json=False)
    state = run_research_loop(
        universe_context=context,
        max_iterations=max_iterations,
        fallback_strategy=fallback_strategy,
        fallback_symbol=fallback_symbol,
    )
    payload = {
        "iterations": state.iteration,
        "cost_usd": round(state.total_cost_usd, 4),
        "recommendation": state.final_recommendation,
        "hypothesis": state.hypothesis.model_dump() if state.hypothesis else None,
        "analysis": state.analysis.model_dump() if state.analysis else None,
    }
    console.print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    app()
