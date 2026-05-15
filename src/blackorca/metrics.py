"""Prometheus metrics.

All metrics live in :data:`REGISTRY` (a private :class:`CollectorRegistry`) so
tests get a clean slate and we don't accidentally export Python process
internals. Call :func:`start_metrics_server` once at app startup to expose
``/metrics`` on the configured port.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

REGISTRY = CollectorRegistry(auto_describe=True)

# ---------------------------------------------------------------------------
# Trading-side metrics
# ---------------------------------------------------------------------------

ORDERS_SUBMITTED = Counter(
    "blackorca_orders_submitted_total",
    "Orders submitted by strategy and side",
    labelnames=("strategy", "symbol", "side"),
    registry=REGISTRY,
)

ORDERS_REJECTED = Counter(
    "blackorca_orders_rejected_total",
    "Orders rejected by pre-trade risk",
    labelnames=("strategy", "reason"),
    registry=REGISTRY,
)

FILLS = Counter(
    "blackorca_fills_total",
    "Order fills",
    labelnames=("strategy", "symbol", "side"),
    registry=REGISTRY,
)

PNL_GAUGE = Gauge(
    "blackorca_pnl_usd",
    "Net P&L in USD (mark-to-market)",
    labelnames=("strategy",),
    registry=REGISTRY,
)

NAV_GAUGE = Gauge(
    "blackorca_nav_usd",
    "Net asset value in USD",
    labelnames=("account",),
    registry=REGISTRY,
)

GROSS_EXPOSURE_GAUGE = Gauge(
    "blackorca_gross_exposure_usd",
    "Gross exposure in USD",
    labelnames=("strategy",),
    registry=REGISTRY,
)

NET_EXPOSURE_GAUGE = Gauge(
    "blackorca_net_exposure_usd",
    "Net exposure in USD",
    labelnames=("strategy",),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Data ingestion / catalog
# ---------------------------------------------------------------------------

BARS_INGESTED = Counter(
    "blackorca_bars_ingested_total",
    "Bars written to catalog",
    labelnames=("source", "instrument"),
    registry=REGISTRY,
)

DATA_FETCH_LATENCY = Histogram(
    "blackorca_data_fetch_latency_seconds",
    "Latency of external data source fetches",
    labelnames=("source",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

PIT_VIOLATIONS = Counter(
    "blackorca_pit_violations_total",
    "Point-in-time integrity violations detected",
    labelnames=("source", "kind"),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Agent / LLM
# ---------------------------------------------------------------------------

AGENT_TOKENS = Counter(
    "blackorca_agent_tokens_total",
    "LLM tokens consumed",
    labelnames=("model", "kind"),
    registry=REGISTRY,
)

AGENT_COST_USD = Counter(
    "blackorca_agent_cost_usd_total",
    "Cumulative LLM spend in USD",
    labelnames=("model",),
    registry=REGISTRY,
)

AGENT_LATENCY = Histogram(
    "blackorca_agent_latency_seconds",
    "End-to-end agent call latency",
    labelnames=("model",),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
    registry=REGISTRY,
)


_SERVER_STARTED = False


def start_metrics_server(port: int = 9100) -> None:
    """Start the Prometheus HTTP server. Idempotent."""
    global _SERVER_STARTED
    if _SERVER_STARTED:
        return
    start_http_server(port, registry=REGISTRY)
    _SERVER_STARTED = True


def snapshot() -> dict[str, Any]:
    """Return a dict snapshot of all metrics; primarily for tests."""
    out: dict[str, Any] = {}
    for metric in REGISTRY.collect():
        out[metric.name] = [
            {"labels": dict(s.labels), "value": s.value} for s in metric.samples
        ]
    return out


__all__ = [
    "AGENT_COST_USD",
    "AGENT_LATENCY",
    "AGENT_TOKENS",
    "BARS_INGESTED",
    "DATA_FETCH_LATENCY",
    "FILLS",
    "GROSS_EXPOSURE_GAUGE",
    "NAV_GAUGE",
    "NET_EXPOSURE_GAUGE",
    "ORDERS_REJECTED",
    "ORDERS_SUBMITTED",
    "PIT_VIOLATIONS",
    "PNL_GAUGE",
    "REGISTRY",
    "snapshot",
    "start_metrics_server",
]
