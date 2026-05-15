"""Tests page: run pytest from the UI with live output."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from blackorca.runs.registry import record
from frontend.components.common import init_page

init_page("Tests", icon="✅")
st.title("✅ Test Suite Runner")

st.caption(
    "Runs pytest in a subprocess. Captures stdout/stderr to a log file so the UI can stream it. "
    "Test markers (unit / integration / regression / live) are configurable in `pyproject.toml`."
)

# Test discovery
TESTS_ROOT = Path("tests")
suites = {
    "unit": "tests/unit",
    "integration": "tests/integration",
    "regression (tagged)": "-m regression",
    "all (no live)": "-m 'not live'",
}

c1, c2 = st.columns(2)
chosen = c1.selectbox("Suite", list(suites.keys()))
verbose = c2.checkbox("Verbose (-v)", value=True)

cli_extra = st.text_input("Extra pytest args", value="")

if st.button("Run pytest", use_container_width=True):
    cmd = ["uv", "run", "pytest"]
    target = suites[chosen]
    if target.startswith("-m"):
        cmd += target.split()
    else:
        cmd += [target]
    if verbose:
        cmd += ["-v"]
    if cli_extra.strip():
        cmd += cli_extra.split()
    st.write("Running:", " ".join(cmd))
    started = datetime.now(timezone.utc)
    placeholder = st.empty()
    log_lines: list[str] = []
    try:
        with subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        ) as proc:
            for line in proc.stdout or []:
                log_lines.append(line.rstrip())
                placeholder.code("\n".join(log_lines[-200:]), language="bash")
            ret = proc.wait()
        ok = ret == 0
        st.success("✓ tests passed") if ok else st.error(f"✕ tests failed (exit {ret})")
        record(
            kind="pytest",
            name=chosen,
            started_at=started,
            payload={"exit_code": ret, "n_lines": len(log_lines)},
            error=None if ok else f"exit code {ret}",
        )
    except Exception as e:
        st.error(f"Couldn't run pytest: {e}")
        record(kind="pytest", name=chosen, started_at=started, error=str(e))

st.divider()
with st.expander("Discover tests"):
    tests = list(TESTS_ROOT.rglob("test_*.py"))
    st.write(f"Found {len(tests)} test files:")
    for t in tests:
        st.write(f"- `{t.relative_to(TESTS_ROOT.parent).as_posix()}`")
