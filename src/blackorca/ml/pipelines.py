"""PIT-aware feature pipeline.

A thin wrapper that:

1. Runs a sequence of :class:`Feature` transforms.
2. Refuses to fit/transform if the inputs aren't PIT-clean.
3. Aligns features to forward returns at a target horizon.

We deliberately avoid sklearn ``Pipeline`` here because Polars frames flow
better as the primary container, and we want explicit PIT gates between
steps.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from blackorca.data.pit import assert_no_lookahead
from blackorca.ml.features.base import Feature


@dataclass(slots=True)
class FitResult:
    feature_columns: list[str]
    target_column: str
    n_rows: int


class PITPipeline:
    def __init__(self, features: list[Feature]) -> None:
        self.features = features
        self.feature_columns = [f.output_column() for f in features]

    def transform(self, bars: pl.DataFrame) -> pl.DataFrame:
        if not bars.is_empty():
            assert_no_lookahead(bars, source="pipeline.input")
        out = bars
        for f in self.features:
            out = f.compute(out)
        return out

    def build_supervised(
        self,
        bars: pl.DataFrame,
        *,
        target_horizon: int = 1,
        target_col: str = "fwd_ret",
    ) -> tuple[pl.DataFrame, FitResult]:
        feats = self.transform(bars)
        feats = feats.sort(["symbol", "as_of"]).with_columns(
            (
                pl.col("close").shift(-target_horizon).over("symbol") / pl.col("close") - 1
            ).alias(target_col)
        )
        # Drop rows missing any feature or the target (avoids leakage at edges)
        keep = ["symbol", "as_of", target_col, *self.feature_columns]
        feats = feats.select([c for c in keep if c in feats.columns]).drop_nulls()
        return feats, FitResult(
            feature_columns=self.feature_columns,
            target_column=target_col,
            n_rows=feats.height,
        )


__all__ = ["FitResult", "PITPipeline"]
