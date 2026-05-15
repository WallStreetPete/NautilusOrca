"""Research page: event study, IC analysis, factor study, walk-forward."""

from __future__ import annotations

from datetime import date, datetime, timezone

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from blackorca.data.catalog import Catalog
from blackorca.research.event_study import run_event_study
from blackorca.research.factor_research import run_factor_study
from blackorca.research.ic_analysis import compute_ic_decay
from blackorca.runs.registry import record
from frontend.components.common import PLOTLY_TEMPLATE, init_page

init_page("Research", icon="🧪")
st.title("🧪 Research Toolkit")

cat = Catalog()
instruments = cat.list_instruments()

tab_event, tab_ic, tab_factor = st.tabs(["📅 Event study", "📈 IC decay", "🧮 Factor study"])

# ---------------------------------------------------------------------------
# Event study
# ---------------------------------------------------------------------------

with tab_event:
    if not instruments:
        st.info("Ingest data first.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        sym = c1.selectbox("Symbol", instruments, key="es_sym")
        pre = c2.number_input("Pre-window (days)", 1, 60, 5, key="es_pre")
        post = c3.number_input("Post-window (days)", 1, 120, 20, key="es_post")
        dates_str = c4.text_input(
            "Event dates (comma ISO)",
            value="2023-02-22,2023-05-24,2023-08-23,2023-11-21",
            key="es_dates",
        )
        if st.button("Run event study"):
            started = datetime.now(timezone.utc)
            prices = cat.read_bars([sym], date(2000, 1, 1), date.today())
            try:
                event_dates = [
                    datetime.fromisoformat(d.strip()).replace(tzinfo=timezone.utc)
                    for d in dates_str.split(",")
                    if d.strip()
                ]
                events = pl.DataFrame({"symbol": [sym] * len(event_dates), "event_date": event_dates})
                res = run_event_study(prices, events, pre_window=int(pre), post_window=int(post))
                st.metric("Events used", res.n_events)
                # AAR chart
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=res.aar["day"].to_list(),
                        y=res.aar["aar"].to_list(),
                        name="AAR",
                        marker_color="#7dd3fc",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=res.caar["day"].to_list(),
                        y=res.caar["caar"].to_list(),
                        name="CAAR",
                        yaxis="y2",
                        line=dict(color="#f97316", width=2),
                    )
                )
                fig.update_layout(
                    template=PLOTLY_TEMPLATE,
                    yaxis=dict(title="AAR"),
                    yaxis2=dict(title="CAAR", overlaying="y", side="right"),
                    height=400, margin=dict(l=10, r=10, t=10, b=10),
                )
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("Per-day AAR table"):
                    st.dataframe(res.aar.to_pandas(), use_container_width=True, hide_index=True)
                record(
                    kind="event_study",
                    name=f"{sym} ({res.n_events} events)",
                    started_at=started,
                    payload={"n_events": res.n_events, "sym": sym},
                )
            except Exception as e:
                st.error(f"Event study failed: {e}")
                record(kind="event_study", name=sym, started_at=started, error=str(e))

# ---------------------------------------------------------------------------
# IC decay
# ---------------------------------------------------------------------------

with tab_ic:
    if not instruments:
        st.info("Ingest data first.")
    else:
        st.write("Computes cross-sectional IC decay over horizons {1,3,5,10,20} for a mean-reversion signal across the chosen basket.")
        syms = st.multiselect("Symbols", instruments, default=instruments[: min(8, len(instruments))])
        if st.button("Compute IC decay", disabled=not syms):
            started = datetime.now(timezone.utc)
            prices = cat.read_bars(syms, date(2000, 1, 1), date.today())
            factor = (
                prices.sort(["symbol", "as_of"])
                .with_columns(value=-pl.col("close").pct_change().shift(1).over("symbol"))
                .drop_nulls("value")
                .select(["symbol", "as_of", "value"])
            )
            decay = compute_ic_decay(factor, prices)
            d = decay.to_pandas()
            st.dataframe(d, use_container_width=True, hide_index=True)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=d["horizon"], y=d["mean_ic"], name="IC", marker_color="#7dd3fc"))
            fig.add_trace(go.Scatter(x=d["horizon"], y=d["rank_mean_ic"], name="rank IC", line=dict(color="#f97316")))
            fig.update_layout(template=PLOTLY_TEMPLATE, height=380, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            record(kind="ic_decay", name="mr-1d", started_at=started, payload={"horizons": list(d["horizon"])})

# ---------------------------------------------------------------------------
# Factor study
# ---------------------------------------------------------------------------

with tab_factor:
    if not instruments:
        st.info("Ingest data first.")
    else:
        c1, c2, c3 = st.columns(3)
        syms = c1.multiselect("Symbols", instruments, default=instruments[: min(10, len(instruments))], key="fs_syms")
        horizon = c2.number_input("Horizon (days)", 1, 30, 1, key="fs_h")
        n_buckets = c3.number_input("Buckets", 2, 10, 5, key="fs_b")
        if st.button("Run factor study", disabled=not syms):
            started = datetime.now(timezone.utc)
            prices = cat.read_bars(syms, date(2000, 1, 1), date.today())
            factor = (
                prices.sort(["symbol", "as_of"])
                .with_columns(value=-pl.col("close").pct_change().shift(1).over("symbol"))
                .drop_nulls("value")
                .select(["symbol", "as_of", "value"])
            )
            res = run_factor_study(factor, prices, horizon=int(horizon), n_buckets=int(n_buckets))
            st.write("**Long-short metrics**")
            st.json(res.metrics)
            if not res.long_short.is_empty():
                eq = (1 + res.long_short["ls_ret"]).cum_prod()
                fig = go.Figure(go.Scatter(x=res.long_short["as_of"].to_list(), y=eq.to_list(), line=dict(color="#7dd3fc")))
                fig.update_layout(
                    template=PLOTLY_TEMPLATE, height=380, margin=dict(l=10, r=10, t=10, b=10),
                    title="Long-short cumulative return",
                )
                st.plotly_chart(fig, use_container_width=True)
            record(kind="factor_study", name="mr-1d", started_at=started, payload={"metrics": res.metrics})
