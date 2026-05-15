"""Data catalog page: ingest, browse, chart, PIT-check."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import plotly.graph_objects as go
import streamlit as st

from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.data.ingest import ingest_bars
from blackorca.data.pit import PITViolation, assert_no_lookahead
from blackorca.data.sources.databento import DatabentoSource
from blackorca.data.sources.yfinance import YFinanceSource
from blackorca.runs.registry import record
from frontend.components.common import PLOTLY_TEMPLATE, init_page

init_page("Data Catalog", icon="📊")
st.title("📊 Data Catalog")
st.caption("Ingest market data, browse the catalog, and run PIT integrity checks.")

cat = Catalog()
stats = cat.stats()

c1, c2, c3 = st.columns(3)
c1.metric("Backend", stats.get("backend", "?"))
c2.metric("Parquet files", stats.get("files", 0))
c3.metric("Size (MB)", round(stats.get("bytes", 0) / 1_000_000, 2))

tab_ingest, tab_browse, tab_pit = st.tabs(["🔽 Ingest", "🔎 Browse & chart", "🛡️ PIT check"])

# ---------------------------------------------------------------------------
# Ingest tab
# ---------------------------------------------------------------------------

with tab_ingest:
    with st.form("ingest_form"):
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        tickers = c1.text_input("Tickers (comma-sep)", value="NVDA,AMD")
        source_name = c2.selectbox("Source", ["yfinance", "databento"])
        years = c3.number_input("Years", min_value=1, max_value=20, value=2, step=1)
        aggregation = c4.selectbox("Bars", ["1d", "1h", "1m"], index=0)
        submitted = st.form_submit_button("Ingest")
    if submitted:
        syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        end = date.today()
        start = end - timedelta(days=int(years) * 365)
        src = YFinanceSource() if source_name == "yfinance" else DatabentoSource()
        if not src.is_available():
            st.error(f"{source_name} unavailable (missing key?).")
        else:
            started = datetime.now(timezone.utc)
            with st.status("Ingesting...", expanded=True) as status:
                try:
                    n = ingest_bars(src, cat, syms, start, end, BarAggregation(aggregation))
                    status.update(label=f"Ingested {n} rows from {source_name}", state="complete")
                    record(
                        kind="ingest",
                        name=f"{source_name} {','.join(syms)}",
                        started_at=started,
                        payload={"rows": n, "symbols": syms, "source": source_name},
                    )
                except Exception as e:
                    status.update(label=f"Failed: {e}", state="error")
                    record(
                        kind="ingest",
                        name=f"{source_name} {','.join(syms)}",
                        started_at=started,
                        payload={"symbols": syms, "source": source_name},
                        error=str(e),
                    )

# ---------------------------------------------------------------------------
# Browse + chart tab
# ---------------------------------------------------------------------------

with tab_browse:
    instruments = cat.list_instruments(BarAggregation.DAY)
    if not instruments:
        st.info("Catalog is empty for daily bars. Ingest something first.")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        sym = c1.selectbox("Symbol", instruments)
        chart_kind = c2.selectbox("Chart", ["candlestick", "close + volume"])
        bars_back = c3.number_input("Bars back", 30, 5000, 500, step=30)
        df = cat.read_bars(sym, date(2000, 1, 1), date.today())
        if df.is_empty():
            st.warning("No bars for that symbol.")
        else:
            df = df.tail(int(bars_back))
            ts = df["as_of"].to_list()
            o = df["open"].to_list()
            h = df["high"].to_list()
            lo = df["low"].to_list()
            c = df["close"].to_list()
            v = df["volume"].to_list()

            fig = go.Figure()
            if chart_kind == "candlestick":
                fig.add_trace(
                    go.Candlestick(x=ts, open=o, high=h, low=lo, close=c, name=sym)
                )
            else:
                fig.add_trace(go.Scatter(x=ts, y=c, name="close", mode="lines"))
                fig.add_trace(go.Bar(x=ts, y=v, name="volume", yaxis="y2", opacity=0.4))
                fig.update_layout(
                    yaxis2=dict(overlaying="y", side="right", showgrid=False, title="volume")
                )
            fig.update_layout(
                template=PLOTLY_TEMPLATE,
                margin=dict(l=10, r=10, t=20, b=10),
                height=460,
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander(f"Last 25 rows of {sym}"):
                st.dataframe(df.tail(25).to_pandas(), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# PIT check tab
# ---------------------------------------------------------------------------

with tab_pit:
    instruments = cat.list_instruments(BarAggregation.DAY)
    if not instruments:
        st.info("No instruments to check.")
    else:
        target = st.selectbox("Instrument", ["(all)", *instruments])
        if st.button("Run PIT integrity check"):
            errors = []
            ok = 0
            for sym in instruments if target == "(all)" else [target]:
                df = cat.read_bars(sym, date(2000, 1, 1), date.today())
                if df.is_empty():
                    continue
                try:
                    assert_no_lookahead(df, source=f"catalog:{sym}")
                    ok += 1
                except PITViolation as e:
                    errors.append((sym, str(e)))
            c1, c2 = st.columns(2)
            c1.metric("clean", ok)
            c2.metric("violations", len(errors))
            if errors:
                for sym, msg in errors:
                    st.error(f"{sym}: {msg}")
            else:
                st.success("All checked symbols are PIT-clean.")
