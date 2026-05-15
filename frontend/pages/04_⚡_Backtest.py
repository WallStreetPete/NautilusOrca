"""Backtest page: run any registered strategy and view tearsheet."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import plotly.graph_objects as go
import streamlit as st

from blackorca.backtest.runner import run_backtest
from blackorca.data.catalog import Catalog
from blackorca.risk.limits import RiskLimits
from blackorca.runs.registry import get_registry, record
from blackorca.strategies.registry import StrategyRegistry
from frontend.components.common import PLOTLY_TEMPLATE, init_page, render_run_table

init_page("Backtest", icon="⚡")
st.title("⚡ Backtest Runner")

cat = Catalog()
instruments = cat.list_instruments()
strategies = StrategyRegistry.list_strategies()

tab_run, tab_hist = st.tabs(["Run", "History"])

with tab_run:
    with st.form("bt_form"):
        c1, c2, c3 = st.columns(3)
        strategy_name = c1.selectbox("Strategy", strategies)
        symbol = c2.selectbox("Symbol", instruments) if instruments else c2.text_input("Symbol", "NVDA")
        capital = c3.number_input("Capital (USD)", 10_000, 100_000_000, 1_000_000, step=100_000)

        c4, c5, c6 = st.columns(3)
        end_d = c4.date_input("End date", value=date.today())
        years_back = c5.number_input("Years back", 1, 20, 4)
        target_weight = c6.number_input("Target weight (per name)", 0.01, 1.0, 0.2, step=0.01)

        c7, c8, c9 = st.columns(3)
        slippage_bps = c7.number_input("Slippage (bps)", 0.0, 50.0, 2.0)
        per_order_cap = c8.number_input("Per-order notional cap ($)", 1_000.0, 1e9, 1e9, step=10_000.0)
        params_json = c9.text_input("Extra params (JSON)", "{}")

        submitted = st.form_submit_button("Run backtest", use_container_width=True)

    if submitted:
        try:
            params = json.loads(params_json) if params_json.strip() else {}
        except Exception as e:
            st.error(f"Bad params JSON: {e}")
            st.stop()
        start_d = end_d - timedelta(days=int(years_back) * 365)
        params.setdefault("target_weight", float(target_weight))
        strat_cls = StrategyRegistry.get(strategy_name)
        strat = strat_cls(symbol=symbol, **params)
        relaxed = RiskLimits(
            max_position_pct=0.50,
            max_gross_pct=2.0,
            max_net_pct=2.0,
            per_order_max_notional=float(per_order_cap),
        )
        started = datetime.now(timezone.utc)
        with st.spinner("Running..."):
            try:
                result = run_backtest(
                    strat,
                    symbols=[symbol],
                    start=start_d,
                    end=end_d,
                    capital=float(capital),
                    catalog=cat,
                    risk_limits=relaxed,
                )
                # KPIs
                m = result.metrics
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Total return", f"{m.get('total_return', 0):.2%}")
                c2.metric("Sharpe", f"{m.get('sharpe', 0):.2f}")
                c3.metric("Max DD", f"{m.get('max_drawdown', 0):.2%}")
                c4.metric("Trades", int(m.get("n_trades", 0)))
                c5.metric("Final equity", f"${m.get('final_equity', 0):,.0f}")

                # Equity curve
                ec = result.equity_curve
                fig = go.Figure(
                    go.Scatter(
                        x=ec["timestamp"].to_list(),
                        y=ec["equity"].to_list(),
                        line=dict(color="#7dd3fc", width=2),
                    )
                )
                fig.update_layout(
                    template=PLOTLY_TEMPLATE, height=380, margin=dict(l=10, r=10, t=20, b=10),
                    title="Equity curve",
                )
                st.plotly_chart(fig, use_container_width=True)

                # Drawdown
                eq = ec["equity"].to_numpy()
                if len(eq) > 1:
                    import numpy as np

                    peaks = np.maximum.accumulate(eq)
                    dd = (eq - peaks) / peaks
                    fig_dd = go.Figure(go.Scatter(x=ec["timestamp"].to_list(), y=dd, fill="tozeroy", line=dict(color="#d73a49")))
                    fig_dd.update_layout(template=PLOTLY_TEMPLATE, height=200, margin=dict(l=10, r=10, t=10, b=10), title="Drawdown")
                    st.plotly_chart(fig_dd, use_container_width=True)

                # Trade log
                if not result.trades.is_empty():
                    with st.expander(f"{result.trades.height} trades"):
                        st.dataframe(result.trades.to_pandas(), use_container_width=True, hide_index=True)

                with st.expander("All metrics"):
                    st.json(m)

                record(
                    kind="backtest",
                    name=f"{strategy_name} {symbol}",
                    started_at=started,
                    payload={
                        "config": result.config,
                        "metrics": m,
                        "equity_curve": {
                            "timestamp": [t.isoformat() for t in ec["timestamp"].to_list()],
                            "equity": ec["equity"].to_list(),
                        },
                    },
                )
                st.success(f"Recorded run.")
            except Exception as e:
                st.error(f"Backtest failed: {e}")
                record(
                    kind="backtest",
                    name=f"{strategy_name} {symbol}",
                    started_at=started,
                    payload={"params": params, "symbol": symbol},
                    error=str(e),
                )

with tab_hist:
    runs = get_registry().list(kind="backtest", limit=200)
    render_run_table(runs, max_rows=100)
    if runs:
        sel = st.selectbox("Drill into run", [r.id for r in runs])
        run = next((r for r in runs if r.id == sel), None)
        if run is not None and run.payload.get("equity_curve"):
            eq = run.payload["equity_curve"]
            fig = go.Figure(go.Scatter(x=eq["timestamp"], y=eq["equity"], line=dict(color="#7dd3fc")))
            fig.update_layout(template=PLOTLY_TEMPLATE, height=320, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.json(run.payload.get("metrics", {}))
