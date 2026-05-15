"""Universe + dependency graph visualization."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from blackorca.universe.dependency_graph import DEPENDENCY_GRAPH
from blackorca.universe.semis import SEMI_UNIVERSE, Tier
from frontend.components.common import PLOTLY_TEMPLATE, init_page

init_page("Universe", icon="🧬")
st.title("🧬 Universe & Dependency Graph")

tab_univ, tab_graph = st.tabs(["Universe", "Supplier graph"])

with tab_univ:
    rows = [
        {
            "symbol": s.symbol,
            "name": s.name,
            "tier": int(s.tier),
            "segment": s.segment,
            "country": s.country,
            "avg_adv": s.avg_adv,
            "mcap": s.mcap_bucket,
        }
        for s in SEMI_UNIVERSE
    ]
    df = pd.DataFrame(rows)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Names", len(df))
        st.metric("Tier-1", int((df["tier"] == 1).sum()))
        st.metric("Tier-2", int((df["tier"] == 2).sum()))
        st.metric("Tier-3", int((df["tier"] == 3).sum()))
    with c2:
        st.write("**Distribution by segment**")
        seg = df.groupby("segment").size().reset_index(name="count").sort_values("count", ascending=True)
        fig = go.Figure(go.Bar(y=seg["segment"], x=seg["count"], orientation="h"))
        fig.update_layout(template=PLOTLY_TEMPLATE, margin=dict(l=10, r=10, t=10, b=10), height=320)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_graph:
    min_conf = st.slider("Min confidence", 0.0, 1.0, 0.4, 0.05)
    edges = [(e.upstream, e.downstream, e.confidence, e.expected_lag_days, e.relationship)
             for e in DEPENDENCY_GRAPH if e.confidence >= min_conf]
    if not edges:
        st.info("No edges above the threshold.")
    else:
        G = nx.DiGraph()
        for u, d, c, lag, rel in edges:
            G.add_edge(u, d, weight=c, lag=lag, relationship=rel)
        pos = nx.spring_layout(G, seed=7, k=1.5)

        edge_traces = []
        for u, d in G.edges():
            x0, y0 = pos[u]
            x1, y1 = pos[d]
            edge_traces.append(
                go.Scatter(
                    x=[x0, x1, None], y=[y0, y1, None],
                    mode="lines",
                    line=dict(width=1 + 3 * G[u][d]["weight"], color="rgba(125,211,252,0.5)"),
                    hoverinfo="none", showlegend=False,
                )
            )
        # Tier-colored nodes
        node_color = []
        for n in G.nodes():
            tier = next((s.tier for s in SEMI_UNIVERSE if s.symbol == n), Tier.T3)
            node_color.append({Tier.T1: "#f97316", Tier.T2: "#7dd3fc", Tier.T3: "#a3a3a3"}[tier])
        node_trace = go.Scatter(
            x=[pos[n][0] for n in G.nodes()],
            y=[pos[n][1] for n in G.nodes()],
            mode="markers+text",
            text=list(G.nodes()),
            textposition="top center",
            marker=dict(size=24, color=node_color, line=dict(width=1, color="black")),
            hoverinfo="text",
        )
        fig = go.Figure(data=[*edge_traces, node_trace])
        fig.update_layout(
            template=PLOTLY_TEMPLATE,
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=560,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander(f"{len(edges)} edges"):
            edf = pd.DataFrame([
                {"upstream": u, "downstream": d, "confidence": c, "lag_days": lag, "relationship": rel}
                for u, d, c, lag, rel in edges
            ])
            st.dataframe(edf, use_container_width=True, hide_index=True)
