"""Online inference for strategies.

Lightweight: loads a model + meta, exposes a ``predict(features) -> array``
shim. Strategies hold a long-lived inference handle so we don't pay the
load cost on every bar.

Latency budget for online inference is 2ms / bar — at this scale, just
running scikit-learn directly is comfortably inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from blackorca.ml.models import ModelMeta, ModelRegistry


@dataclass(slots=True)
class InferenceHandle:
    model: Any
    meta: ModelMeta

    def predict(self, features: pl.DataFrame) -> np.ndarray:
        X = features.select(self.meta.features).to_numpy()
        return np.asarray(self.model.predict(X), dtype=np.float64)


def load_inference(name: str, version: str, registry: ModelRegistry | None = None) -> InferenceHandle:
    reg = registry or ModelRegistry()
    model, meta = reg.load(name, version)
    return InferenceHandle(model=model, meta=meta)


__all__ = ["InferenceHandle", "load_inference"]
