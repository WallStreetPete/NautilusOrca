"""Append-only JSON registry of platform runs.

Each run is a single JSON file under ``data/runs/``. The schema is loose on
purpose — backtest runs, training runs, and agent runs all share the same
envelope but stash kind-specific payloads in ``payload``.

This is a frontend convenience: pages need to *list past runs* without
re-running them. Keep the dependency surface tiny (stdlib only).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from blackorca.config import get_settings


@dataclass(slots=True)
class Run:
    id: str
    kind: str                 # "backtest" | "training" | "research_loop" | "code_review" | "ingest"
    name: str                 # human-friendly label
    status: str               # "ok" | "error"
    started_at: str
    finished_at: str
    duration_seconds: float
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class RunRegistry:
    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            root = Path(get_settings().repo_root) / "data" / "runs"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, run: Run) -> Path:
        path = self.root / f"{run.id}.json"
        path.write_text(json.dumps(asdict(run), indent=2, default=str), encoding="utf-8")
        return path

    def list(self, kind: str | None = None, limit: int = 200) -> list[Run]:
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: list[Run] = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if kind is not None and data.get("kind") != kind:
                    continue
                out.append(Run(**data))
            except Exception:
                continue
        return out

    def get(self, run_id: str) -> Run | None:
        p = self.root / f"{run_id}.json"
        if not p.exists():
            return None
        return Run(**json.loads(p.read_text(encoding="utf-8")))

    def delete(self, run_id: str) -> bool:
        p = self.root / f"{run_id}.json"
        if p.exists():
            p.unlink()
            return True
        return False


_REGISTRY: RunRegistry | None = None


def get_registry() -> RunRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RunRegistry()
    return _REGISTRY


def record(
    *,
    kind: str,
    name: str,
    started_at: datetime,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> Run:
    """Build a :class:`Run` and persist it."""
    now = datetime.now(timezone.utc)
    run = Run(
        id=str(uuid4())[:8] + "-" + now.strftime("%Y%m%d%H%M%S"),
        kind=kind,
        name=name,
        status="error" if error else "ok",
        started_at=started_at.isoformat(),
        finished_at=now.isoformat(),
        duration_seconds=(now - started_at).total_seconds(),
        payload=payload or {},
        error=error,
    )
    get_registry().write(run)
    # Honor an optional log-suppression in test environments
    if os.environ.get("BLACKORCA_QUIET") != "1":
        from blackorca.logging import get_logger

        get_logger(__name__).info("run.recorded", id=run.id, kind=kind, name=name, status=run.status)
    return run


__all__ = ["Run", "RunRegistry", "get_registry", "record"]
