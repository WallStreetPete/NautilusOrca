"""Black Orca Apex Console — Streamlit entrypoint.

Run with:

    uv run streamlit run frontend/app.py

Multi-page navigation: Streamlit auto-discovers ``frontend/pages/*.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import plotly.graph_objects as go
import streamlit as st

from blackorca.data.catalog import Catalog
from blackorca.runs.registry import get_registry
from frontend.components.common import PLOTLY_TEMPLATE, init_page, render_run_table

init_page("Home", icon="🐋")

st.title("🐋 Black Orca Apex Console")
st.caption(
    "Unified frontend for the research, backtest, ML, agent, and live-trading planes. "
    "Built for the Apex platform — same Strategy class runs in backtest, paper, and live."
)

# ---------------------------------------------------------------------------
# Top-line KPIs
# ---------------------------------------------------------------------------

cat = Catalog()
runs = get_registry().list(limit=200)
recent_24h = [
    r
    for r in runs
    if datetime.fromisoformat(r.started_at) >= datetime.now(timezone.utc) - timedelta(hours=24)
]

cat_stats = cat.stats()
backtests = [r for r in runs if r.kind == "backtest"]
trainings = [r for r in runs if r.kind == "training"]
agent_runs = [r for r in runs if r.kind in {"research_loop", "code_review", "hypothesis"}]
agent_cost = sum(float(r.payload.get("cost_usd", 0) or 0) for r in agent_runs)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Catalog files", cat_stats.get("files", 0))
c2.metric("Catalog size (MB)", round(cat_stats.get("bytes", 0) / 1_000_000, 2))
c3.metric("Backtests run", len(backtests))
c4.metric("Models trained", len(trainings))
c5.metric("Agent spend ($)", f"{agent_cost:.4f}")

st.divider()

# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------

st.subheader("Recent activity (last 24h)")
render_run_table(recent_24h, max_rows=15)

st.divider()

# ---------------------------------------------------------------------------
# Equity curve of the most recent backtest, if any
# ---------------------------------------------------------------------------

st.subheader("Last backtest — equity curve")
last_bt = next((r for r in backtests if r.payload.get("equity_curve")), None)
if last_bt is None:
    st.info("No backtests with stored equity curves yet. Go to **Backtest** to run one.")
else:
    eq = last_bt.payload["equity_curve"]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=eq.get("timestamp", []),
            y=eq.get("equity", []),
            mode="lines",
            name="equity",
            line=dict(color="#7dd3fc", width=2),
        )
    )
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        xaxis_title="time",
        yaxis_title="equity ($)",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Run **{last_bt.id}** — {last_bt.name} · "
        + " · ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in last_bt.payload.get("metrics", {}).items())
    )

st.divider()
st.caption("Use the sidebar to navigate. All actions taken from this console are recorded in the **Run Registry** (`data/runs/`).")
