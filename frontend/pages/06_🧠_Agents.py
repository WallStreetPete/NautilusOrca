"""Agents page: hypothesis, research loop, code review, memory browser."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from blackorca.agents.client import AnthropicClient
from blackorca.agents.graphs.research_loop import run_research_loop
from blackorca.agents.graphs.strategy_review import review_strategy
from blackorca.agents.memory import make_memory_store
from blackorca.agents.schemas import Hypothesis
from blackorca.config import get_settings
from blackorca.runs.registry import record
from blackorca.strategies.registry import StrategyRegistry
from frontend.components.common import init_page

init_page("Agents", icon="🧠")
st.title("🧠 Agent Console")

settings = get_settings()
if not settings.anthropic_api_key:
    st.error("ANTHROPIC_API_KEY not set. Add it to `.env`.")
    st.stop()

PROMPT_DIR = Path("src/blackorca/agents/prompts")

tab_hyp, tab_loop, tab_review, tab_mem = st.tabs(
    ["💡 Hypothesis", "🔁 Research loop", "🔍 Code review", "🧾 Memory"]
)

# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------

with tab_hyp:
    ctx = st.text_area(
        "Universe context",
        height=140,
        value=(
            "Universe: NVDA, TSM, AMAT, KLAC, AMD, MU. Recent: TSMC monthly revenue +60% YoY. "
            "We have daily bars in the catalog and a curated supplier dependency graph."
        ),
    )
    fast = st.toggle("Use fast model (Sonnet 4.6)", value=True)
    if st.button("Generate hypothesis"):
        started = datetime.now(timezone.utc)
        try:
            client = AnthropicClient()
            system = (PROMPT_DIR / "hypothesis_gen.md").read_text(encoding="utf-8")
            res = client.complete(system=system, prompt=ctx, schema=Hypothesis, fast=fast, max_tokens=2000)
            if res.parsed:
                h = res.parsed
                st.success(f"Cost: ${res.cost_usd:.4f}  ·  tokens: {res.input_tokens}/{res.output_tokens}")
                st.markdown(f"**Statement:** {h.statement}")
                st.markdown(f"**Mechanism:** {h.mechanism}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Horizon (days)", h.horizon_days)
                c2.metric("Expected edge (bps)", h.expected_edge_bps)
                c3.metric("Confidence", f"{h.confidence:.2f}")
                st.markdown(f"**Universe:** {h.universe}")
                st.markdown(f"**Falsification:** {h.falsification_criterion}")
                with st.expander("Required data"):
                    for d in h.required_data:
                        st.write(f"- **{d.catalog_kind}** ({d.granularity}): {d.rationale}")
                record(
                    kind="hypothesis",
                    name=h.statement[:80],
                    started_at=started,
                    payload={"cost_usd": res.cost_usd, "hypothesis": h.model_dump()},
                )
            else:
                st.warning("Model returned no structured output.")
        except Exception as e:
            st.error(f"Failed: {e}")
            record(kind="hypothesis", name="hypothesis_gen", started_at=started, error=str(e))

# ---------------------------------------------------------------------------
# Research loop
# ---------------------------------------------------------------------------

with tab_loop:
    c1, c2 = st.columns([2, 1])
    ctx = c1.text_area("Universe context", height=120, value="Universe: US semis (~25 names). Recent: TSMC monthly revenue print.")
    iters = c2.number_input("Max iterations", 1, 5, 1)
    fb_strategy = c2.selectbox("Fallback strategy", StrategyRegistry.list_strategies(), index=0)
    fb_symbol = c2.text_input("Fallback symbol", "NVDA")
    if st.button("Run research loop"):
        started = datetime.now(timezone.utc)
        with st.spinner("Running agent loop... (may take 30-60s)"):
            try:
                state = run_research_loop(
                    universe_context=ctx,
                    max_iterations=int(iters),
                    fallback_strategy=fb_strategy,
                    fallback_symbol=fb_symbol,
                )
                st.metric("Total cost (USD)", f"${state.total_cost_usd:.4f}")
                st.metric("Recommendation", state.final_recommendation or "?")
                if state.hypothesis:
                    st.markdown("**Hypothesis**")
                    st.markdown(f"> {state.hypothesis.statement}")
                if state.analysis:
                    st.markdown("**Analysis**")
                    st.write({"red_flags": state.analysis.red_flags, "green_flags": state.analysis.green_flags})
                    st.markdown(f"_{state.analysis.summary}_")
                record(
                    kind="research_loop",
                    name=(state.hypothesis.statement[:80] if state.hypothesis else "research loop"),
                    started_at=started,
                    payload={
                        "cost_usd": state.total_cost_usd,
                        "recommendation": state.final_recommendation,
                        "hypothesis": state.hypothesis.model_dump() if state.hypothesis else None,
                        "metrics": state.backtest.get("metrics") if state.backtest else None,
                    },
                )
            except Exception as e:
                st.error(f"Loop failed: {e}")
                record(kind="research_loop", name="research_loop", started_at=started, error=str(e))

# ---------------------------------------------------------------------------
# Code review
# ---------------------------------------------------------------------------

with tab_review:
    module = st.text_input(
        "Module dotted path",
        value="blackorca.strategies.examples.sma_cross",
    )
    if st.button("Review code"):
        started = datetime.now(timezone.utc)
        try:
            review = review_strategy(module)
            verdict_color = {"approve": "green", "iterate": "orange", "block": "red"}[review.verdict]
            st.markdown(f"**Verdict:** :{verdict_color}[{review.verdict.upper()}]")
            st.markdown(f"*{review.summary}*")
            for issue in review.issues:
                with st.expander(f"[{issue.severity}] {issue.category}: {issue.message}"):
                    if issue.suggested_fix:
                        st.code(issue.suggested_fix)
                    if issue.file:
                        st.caption(f"{issue.file}:{issue.line or '?'}")
            record(
                kind="code_review",
                name=module,
                started_at=started,
                payload={"verdict": review.verdict, "issues": [i.model_dump() for i in review.issues]},
            )
        except Exception as e:
            st.error(f"Review failed: {e}")
            record(kind="code_review", name=module, started_at=started, error=str(e))

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

with tab_mem:
    mem = make_memory_store()
    lessons = mem.all() if hasattr(mem, "all") else []
    st.metric("Stored lessons", len(lessons))
    if lessons:
        import pandas as pd

        df = pd.DataFrame(
            [
                {"id": l.id[:12], "hypothesis": l.hypothesis[:120], "result": l.result_summary[:120]}
                for l in lessons
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No lessons stored yet — run the research loop a few times.")
