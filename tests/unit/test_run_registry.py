"""Run registry round-trip test."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from blackorca.runs.registry import Run, RunRegistry, record


def test_write_and_list(tmp_path: Path) -> None:
    reg = RunRegistry(root=tmp_path / "runs")
    started = datetime.now(timezone.utc) - timedelta(seconds=2)
    r = Run(
        id="abc",
        kind="backtest",
        name="sma NVDA",
        status="ok",
        started_at=started.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        duration_seconds=2.0,
        payload={"metrics": {"sharpe": 1.2}},
    )
    reg.write(r)
    out = reg.list()
    assert len(out) == 1
    assert out[0].id == "abc"
    assert out[0].payload["metrics"]["sharpe"] == 1.2


def test_filter_by_kind(tmp_path: Path) -> None:
    reg = RunRegistry(root=tmp_path / "runs")
    started = datetime.now(timezone.utc)
    reg.write(Run(id="a", kind="backtest", name="x", status="ok", started_at=started.isoformat(), finished_at=started.isoformat(), duration_seconds=0.0))
    reg.write(Run(id="b", kind="training", name="y", status="ok", started_at=started.isoformat(), finished_at=started.isoformat(), duration_seconds=0.0))
    assert len(reg.list(kind="backtest")) == 1
    assert len(reg.list(kind="training")) == 1


def test_record_helper(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Point the singleton at tmp_path
    monkeypatch.setenv("BLACKORCA_QUIET", "1")
    from blackorca.runs import registry as reg_mod

    fresh = RunRegistry(root=tmp_path / "runs")
    monkeypatch.setattr(reg_mod, "_REGISTRY", fresh)
    started = datetime.now(timezone.utc)
    r = record(kind="ingest", name="yfinance NVDA", started_at=started, payload={"rows": 123})
    assert r.status == "ok"
    assert r.payload["rows"] == 123
    assert len(fresh.list()) == 1
