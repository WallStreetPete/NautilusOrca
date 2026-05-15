"""Logs & Metrics page: snapshot Prometheus metrics, embed Grafana, tail runs."""

from __future__ import annotations

import streamlit as st

from blackorca.metrics import snapshot
from blackorca.runs.registry import get_registry
from frontend.components.common import init_page, render_run_table

init_page("Logs & Metrics", icon="📋")
st.title("📋 Logs & Metrics")

tab_metrics, tab_runs, tab_grafana = st.tabs(["Prometheus snapshot", "Run registry", "Grafana"])

with tab_metrics:
    snap = snapshot()
    if not snap:
        st.info("No metrics emitted yet.")
    else:
        # Flatten into one table per metric
        for metric_name, samples in snap.items():
            if not samples:
                continue
            with st.expander(f"**{metric_name}** — {len(samples)} samples"):
                import pandas as pd

                df = pd.DataFrame(
                    [{**s["labels"], "value": s["value"]} for s in samples]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)

with tab_runs:
    runs = get_registry().list(limit=500)
    kinds = sorted({r.kind for r in runs})
    chosen = st.multiselect("Filter by kind", kinds, default=kinds)
    filtered = [r for r in runs if r.kind in chosen]
    render_run_table(filtered, max_rows=200)

with tab_grafana:
    st.caption("If you started `docker compose up -d`, Grafana is at http://localhost:3000 (admin/admin).")
    st.markdown(
        '<iframe src="http://localhost:3000" width="100%" height="800" '
        'style="border: 1px solid #444; border-radius: 6px;"></iframe>',
        unsafe_allow_html=True,
    )
