"""Paper trading page: start/stop the node, view positions + NAV."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

from blackorca.config import get_settings
from blackorca.strategies.registry import StrategyRegistry
from frontend.components.common import init_page

init_page("Paper Trading", icon="📈")
st.title("📈 Paper Trading")

settings = get_settings()
if not settings.alpaca_api_key or not settings.alpaca_api_secret:
    st.warning(
        "Alpaca keys not configured — the paper trading node will run in **dry mode** "
        "(no orders actually reach a broker). Set `ALPACA_API_KEY` + `ALPACA_API_SECRET` in `.env`."
    )

# ---------------------------------------------------------------------------
# Process control via subprocess + a pid lock file
# ---------------------------------------------------------------------------

LOCK_FILE = Path("data/paper_trading.lock")
LOG_FILE = Path("data/paper_trading.log")

c1, c2, c3 = st.columns(3)
running = LOCK_FILE.exists()
c1.metric("Status", "RUNNING 🟢" if running else "STOPPED 🔴")
c2.metric("Profile", settings.profile)
c3.metric("Broker", "Alpaca paper" if settings.alpaca_api_key else "dry mode")

with st.form("paper_form"):
    strategy = st.selectbox("Strategy", StrategyRegistry.list_strategies())
    symbol = st.text_input("Symbol", "NVDA")
    params = st.text_input("Params (JSON)", "{}")
    c1, c2 = st.columns(2)
    start_btn = c1.form_submit_button("▶ Start", disabled=running)
    stop_btn = c2.form_submit_button("⏹ Stop", disabled=not running)

if start_btn and not running:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "ab")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "-m", "blackorca.live.paper",
         f"--strategy={strategy}", f"--symbol={symbol}", f"--params={params}"],
        stdout=log,
        stderr=log,
        cwd=str(settings.repo_root),
    )
    LOCK_FILE.write_text(str(proc.pid))
    st.success(f"Started paper trading (pid {proc.pid}).")
    time.sleep(1)
    st.rerun()

if stop_btn and running:
    import os
    import signal

    try:
        pid = int(LOCK_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        st.warning(f"Couldn't kill pid: {e}")
    LOCK_FILE.unlink(missing_ok=True)
    st.success("Stopped paper trading.")
    time.sleep(1)
    st.rerun()

st.divider()
st.subheader("Tail of paper trading log")
if LOG_FILE.exists():
    text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-80:])
    st.code(tail or "(empty)", language="json")
else:
    st.info("No log yet — start the node to see output.")
