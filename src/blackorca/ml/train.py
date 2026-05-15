"""Training harness with walk-forward CV.

Trains a regression model (LightGBM or sklearn ridge) on PIT-clean features
against forward returns, with walk-forward validation. Persists the model
to the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge

from blackorca.logging import get_logger
from blackorca.ml.models import ModelMeta, ModelRegistry
from blackorca.ml.pipelines import PITPipeline

log = get_logger(__name__)


@dataclass(slots=True)
class TrainResult:
    model_name: str
    version: str
    train_metrics: dict[str, float]
    cv_metrics: dict[str, float]
    feature_columns: list[str]
    n_train_rows: int


def _make_lightgbm() -> Any:
    try:
        import lightgbm as lgb

        return lgb.LGBMRegressor(
            n_estimators=300,
            learning_rate=0.03,
            num_leaves=31,
            max_depth=-1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=7,
            verbose=-1,
        )
    except ImportError:
        return None


def train_model(
    bars: pl.DataFrame,
    pipeline: PITPipeline,
    *,
    name: str,
    version: str | None = None,
    framework: str = "lightgbm",
    target_horizon: int = 1,
    n_splits: int = 5,
    embargo_days: int = 5,
    registry: ModelRegistry | None = None,
) -> TrainResult:
    version = version or datetime.now().strftime("%Y%m%d_%H%M%S")
    registry = registry or ModelRegistry()

    supervised, fit_meta = pipeline.build_supervised(bars, target_horizon=target_horizon)
    if supervised.is_empty():
        raise RuntimeError("no rows after feature construction; check inputs")

    X = supervised.select(fit_meta.feature_columns).to_numpy()
    y = supervised[fit_meta.target_column].to_numpy()
    timestamps = supervised["as_of"].to_list()

    # Time-ordered walk-forward
    order = np.argsort([t.timestamp() for t in timestamps])
    X = X[order]
    y = y[order]

    cv_scores: list[float] = []
    n = len(y)
    fold_size = n // (n_splits + 1)
    for i in range(n_splits):
        train_end = fold_size * (i + 1)
        test_start = train_end + embargo_days
        test_end = test_start + fold_size
        if test_end > n:
            break
        m = _make_lightgbm() if framework == "lightgbm" else None
        if m is None:
            m = Ridge(alpha=1.0)
        m.fit(X[:train_end], y[:train_end])
        pred = m.predict(X[test_start:test_end])
        truth = y[test_start:test_end]
        if np.std(pred) > 0 and np.std(truth) > 0:
            ic = float(np.corrcoef(pred, truth)[0, 1])
        else:
            ic = 0.0
        cv_scores.append(ic)

    final = _make_lightgbm() if framework == "lightgbm" else None
    if final is None:
        final = Ridge(alpha=1.0)
        framework = "ridge"
    final.fit(X, y)

    in_sample_pred = final.predict(X)
    in_sample_ic = (
        float(np.corrcoef(in_sample_pred, y)[0, 1])
        if np.std(in_sample_pred) > 0 and np.std(y) > 0
        else 0.0
    )

    cv_mean = float(np.mean(cv_scores)) if cv_scores else 0.0
    cv_std = float(np.std(cv_scores, ddof=1)) if len(cv_scores) > 1 else 0.0

    meta = ModelMeta(
        name=name,
        version=version,
        framework=framework,
        features=fit_meta.feature_columns,
        target=fit_meta.target_column,
        train_start=str(min(timestamps)),
        train_end=str(max(timestamps)),
        metrics={
            "in_sample_ic": in_sample_ic,
            "cv_ic_mean": cv_mean,
            "cv_ic_std": cv_std,
            "n_cv_folds": float(len(cv_scores)),
        },
        notes=f"horizon={target_horizon}d, embargo={embargo_days}d",
    )
    registry.save(name, version, final, meta)

    return TrainResult(
        model_name=name,
        version=version,
        train_metrics={"in_sample_ic": in_sample_ic},
        cv_metrics={"cv_ic_mean": cv_mean, "cv_ic_std": cv_std, "n_folds": float(len(cv_scores))},
        feature_columns=fit_meta.feature_columns,
        n_train_rows=fit_meta.n_rows,
    )


__all__ = ["TrainResult", "train_model"]
