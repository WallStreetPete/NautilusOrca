"""Walk-forward validation.

Splits the timeline into rolling (train, embargo, test) windows. Runs a
provided callable on each window. Returns per-window metrics so we can
inspect stability: a strategy that works only in 2021 isn't worth carrying.

The harness is parameter-agnostic — the callable is responsible for fitting on
train and evaluating on test (sklearn-style).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl


@dataclass(slots=True)
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WalkForwardResult:
    windows: list[WalkForwardWindow]
    summary: dict[str, float]

    def to_polars(self) -> pl.DataFrame:
        rows = [
            {
                "train_start": w.train_start,
                "train_end": w.train_end,
                "test_start": w.test_start,
                "test_end": w.test_end,
                **w.metrics,
            }
            for w in self.windows
        ]
        return pl.from_dicts(rows) if rows else pl.DataFrame()


def run_walk_forward(
    timestamps: list[datetime],
    *,
    train_days: int = 252,
    test_days: int = 63,
    embargo_days: int = 5,
    step_days: int | None = None,
    evaluator: Callable[[WalkForwardWindow], dict[str, float]],
) -> WalkForwardResult:
    """Run a walk-forward validation.

    The ``evaluator`` callable receives a :class:`WalkForwardWindow` with the
    date ranges populated and returns metrics it computed for that window.
    """
    if not timestamps:
        return WalkForwardResult([], {})
    timestamps = sorted(timestamps)
    start = timestamps[0]
    end = timestamps[-1]
    step = timedelta(days=step_days if step_days is not None else test_days)

    windows: list[WalkForwardWindow] = []
    cursor = start
    while cursor + timedelta(days=train_days + embargo_days + test_days) <= end:
        train_start = cursor
        train_end = cursor + timedelta(days=train_days)
        test_start = train_end + timedelta(days=embargo_days)
        test_end = test_start + timedelta(days=test_days)
        w = WalkForwardWindow(train_start, train_end, test_start, test_end)
        w.metrics = evaluator(w)
        windows.append(w)
        cursor = cursor + step

    summary: dict[str, float] = {}
    if windows:
        keys = {k for w in windows for k in w.metrics}
        for k in keys:
            xs = [w.metrics.get(k, np.nan) for w in windows]
            xs = [x for x in xs if x is not None and not np.isnan(x)]
            if xs:
                summary[f"{k}_mean"] = float(np.mean(xs))
                summary[f"{k}_std"] = float(np.std(xs, ddof=1)) if len(xs) > 1 else 0.0
                summary[f"{k}_min"] = float(np.min(xs))
                summary[f"{k}_max"] = float(np.max(xs))
        summary["n_windows"] = float(len(windows))
    return WalkForwardResult(windows=windows, summary=summary)


__all__ = ["WalkForwardResult", "WalkForwardWindow", "run_walk_forward"]
