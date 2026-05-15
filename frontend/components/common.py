"""Shared Streamlit helpers.

Centralizes the few things we use on every page: a header, a settings sidebar,
a small Plotly theme, and helpers for rendering Run records.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from blackorca import __version__
from blackorca.config import get_settings
from blackorca.runs.registry import Run


PLOTLY_TEMPLATE = "plotly_dark"


def init_page(title: str, icon: str = "🐋") -> None:
    """Set the page config + sidebar header. Call once per page."""
    st.set_page_config(
        page_title=f"Black Orca · {title}",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        .stApp header {visibility: hidden;}
        section[data-testid="stSidebar"] {min-width: 240px;}
        .small-meta {color: #888; font-size: 12px;}
        .metric-good {color: #2dba4e;}
        .metric-bad  {color: #d73a49;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown(f"### Black Orca Capital\n*v{__version__}*")
        settings = get_settings()
        st.caption(f"profile: **{settings.profile}**")
        st.caption(f"catalog: `{settings.catalog_path}`")
        if settings.anthropic_api_key:
            st.success("anthropic: set", icon="✓")
        else:
            st.error("anthropic: missing", icon="✕")
        st.divider()


def status_chip(ok: bool, label_ok: str = "ok", label_bad: str = "fail") -> str:
    color = "#2dba4e" if ok else "#d73a49"
    text = label_ok if ok else label_bad
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:8px;font-size:12px;">{text}</span>'
    )


def render_run_table(runs: list[Run], max_rows: int = 50) -> None:
    if not runs:
        st.info("No runs recorded yet.")
        return
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "id": r.id,
                "kind": r.kind,
                "name": r.name,
                "status": r.status,
                "started": r.started_at[:19].replace("T", " "),
                "duration_s": round(r.duration_seconds, 2),
                "summary": _summarize_payload(r.payload),
            }
            for r in runs[:max_rows]
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def _summarize_payload(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    if "metrics" in payload and isinstance(payload["metrics"], dict):
        m = payload["metrics"]
        bits = []
        if "total_return" in m:
            bits.append(f"ret={m['total_return']:.2%}")
        if "sharpe" in m:
            bits.append(f"sharpe={m['sharpe']:.2f}")
        if "max_drawdown" in m:
            bits.append(f"mdd={m['max_drawdown']:.2%}")
        return " · ".join(bits)
    if "rows" in payload:
        return f"rows={payload['rows']}"
    if "cost_usd" in payload:
        return f"cost=${payload['cost_usd']:.4f}"
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:3])


__all__ = ["PLOTLY_TEMPLATE", "init_page", "render_run_table", "status_chip"]
