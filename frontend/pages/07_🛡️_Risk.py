"""Risk page: limits viewer, pre-trade simulator, kill-switch tester."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from blackorca.backtest.runner import BacktestState
from blackorca.config import get_settings
from blackorca.data.contracts import Side
from blackorca.risk.kill_switch import KillSwitch
from blackorca.risk.limits import RiskLimits
from blackorca.risk.pretrade import PreTradeRiskCheck
from blackorca.strategies.base import OrderRequest
from frontend.components.common import init_page

init_page("Risk", icon="🛡️")
st.title("🛡️ Risk System")

settings = get_settings()
risk_cfg = settings.risk

tab_view, tab_pretrade, tab_kill = st.tabs(["Limits", "Pre-trade simulator", "Kill switch"])

# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

with tab_view:
    st.write(f"Active profile: **{settings.profile}**")
    st.json(risk_cfg.model_dump())

# ---------------------------------------------------------------------------
# Pre-trade simulator
# ---------------------------------------------------------------------------

with tab_pretrade:
    st.caption("Build a hypothetical book + an order; see if pre-trade risk approves it.")
    c1, c2, c3, c4 = st.columns(4)
    symbol = c1.text_input("Symbol", "NVDA")
    side = c2.selectbox("Side", ["BUY", "SELL"])
    quantity = c3.number_input("Quantity", 1, 1_000_000, 100)
    last_price = c4.number_input("Last price ($)", 0.01, 100_000.0, 500.0)

    st.write("**Existing positions** (symbol → qty)")
    positions_raw = st.text_input("e.g. NVDA:50, AMD:-20", value="")
    positions: dict[str, float] = {}
    for chunk in positions_raw.split(","):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            try:
                positions[k.strip().upper()] = float(v)
            except ValueError:
                pass

    c5, c6, c7 = st.columns(3)
    cash = c5.number_input("Cash ($)", -1e9, 1e9, 1_000_000.0)
    pos_cap = c6.number_input("Override max_position_pct", 0.0, 1.0, risk_cfg.max_position_pct)
    notional_cap = c7.number_input("Per-order notional cap", 100.0, 1e9, risk_cfg.per_order_max_notional)

    if st.button("Check order"):
        state = BacktestState(cash=cash)
        state.positions = dict(positions)
        state.last_price = {symbol.upper(): float(last_price)}
        for sym in positions:
            state.last_price.setdefault(sym, float(last_price))
        limits = RiskLimits(
            max_position_pct=float(pos_cap),
            max_gross_pct=risk_cfg.max_gross_pct,
            max_net_pct=risk_cfg.max_net_pct,
            max_sector_pct=risk_cfg.max_sector_pct,
            max_daily_loss_pct=risk_cfg.max_daily_loss_pct,
            max_drawdown_pct=risk_cfg.max_drawdown_pct,
            per_order_max_notional=float(notional_cap),
        )
        chk = PreTradeRiskCheck(limits)
        order = OrderRequest(
            strategy_id="sim",
            symbol=symbol.upper(),
            side=Side.BUY if side == "BUY" else Side.SELL,
            quantity=float(quantity),
        )
        decision = chk.check(order, state)
        if decision.approved:
            st.success("✓ APPROVED")
        else:
            st.error(f"✕ REJECTED — code: `{decision.code}` — {decision.reason}")
        st.caption(f"Equity: ${state.equity():,.2f}")

# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

with tab_kill:
    c1, c2 = st.columns(2)
    dd_pct = c1.slider("Simulated drawdown from HWM", 0.0, 0.3, 0.06, 0.01)
    daily_loss = c2.slider("Simulated daily loss", 0.0, 0.10, 0.01, 0.005)
    hwm = 1_000_000
    equity = hwm * (1 - dd_pct)
    day_open = hwm
    day_now = equity
    ks = KillSwitch(
        max_drawdown_pct=risk_cfg.max_drawdown_pct,
        max_daily_loss_pct=risk_cfg.max_daily_loss_pct,
    )
    tripped = ks.evaluate(equity, hwm, day_open, datetime.now(timezone.utc))
    daily_pct = (day_now - day_open) / day_open
    if tripped:
        st.error(f"🛑 KILL SWITCH TRIPPED — {ks.state.reason}")
    else:
        st.success(f"✓ Switch armed (no trip). DD={dd_pct:.2%}, daily={daily_pct:.2%}")
    st.caption(f"Limits: DD ≤ {risk_cfg.max_drawdown_pct:.2%}, daily ≤ {risk_cfg.max_daily_loss_pct:.2%}")
