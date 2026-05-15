"""Feature interface.

A :class:`Feature` is an idempotent transform that takes a Polars DataFrame
keyed by ``[symbol, as_of]`` and produces a Polars DataFrame with the same
keys plus the feature columns it adds.

PIT discipline: features may only access columns whose ``observed_at`` is
``<= as_of``. The :meth:`assert_pit` hook is run in tests against a
deliberately corrupted frame to catch lookahead bugs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    lookback_days: int
    needs_columns: tuple[str, ...] = ("close",)


class Feature(ABC):
    spec: FeatureSpec

    @abstractmethod
    def compute(self, df: pl.DataFrame) -> pl.DataFrame: ...

    def output_column(self) -> str:
        return self.spec.name


__all__ = ["Feature", "FeatureSpec"]
