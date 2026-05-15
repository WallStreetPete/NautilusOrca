"""Point-in-time integrity validation.

Two flavors of look-ahead bias we catch here:

1. ``observed_at < as_of`` — impossible to know the row before it happens.
2. ``observed_at > as_of + grace`` — row arrives implausibly late; in practice
   this catches a wired-wrong source emitting only ``as_of`` and copying it.

For *PIT joins* between two frames, the contract is: when evaluating a feature
at decision time ``t``, only rows with ``observed_at <= t`` may be used. The
``pit_asof_join`` helper enforces this.
"""

from __future__ import annotations

from datetime import timedelta

import polars as pl

from blackorca.metrics import PIT_VIOLATIONS


class PITViolation(ValueError):
    """Raised when a frame violates point-in-time integrity."""


def assert_no_lookahead(
    df: pl.DataFrame,
    *,
    source: str = "unknown",
    max_observation_lag: timedelta | None = None,
) -> None:
    """Validate a frame's PIT integrity.

    Required columns:
        - ``as_of``       (Datetime)
        - ``observed_at`` (Datetime)

    Raises :class:`PITViolation` on first violation found.
    """
    missing = {"as_of", "observed_at"} - set(df.columns)
    if missing:
        raise PITViolation(f"frame missing PIT columns: {missing}")

    if df.is_empty():
        return

    # 1) observed_at >= as_of (you cannot see something before it happened)
    bad = df.filter(pl.col("observed_at") < pl.col("as_of"))
    if not bad.is_empty():
        PIT_VIOLATIONS.labels(source=source, kind="observed_before_as_of").inc(len(bad))
        first = bad.row(0, named=True)
        raise PITViolation(
            f"PIT violation: {len(bad)} rows have observed_at < as_of "
            f"(first: as_of={first['as_of']} observed_at={first['observed_at']})"
        )

    # 2) plausible upper bound on the lag
    if max_observation_lag is not None:
        lag_secs = int(max_observation_lag.total_seconds())
        late = df.filter(
            (pl.col("observed_at") - pl.col("as_of")).dt.total_seconds() > lag_secs
        )
        if not late.is_empty():
            PIT_VIOLATIONS.labels(source=source, kind="observation_lag_exceeded").inc(len(late))
            raise PITViolation(
                f"PIT violation: {len(late)} rows have observed_at lagging by more than "
                f"{max_observation_lag}; expected near-real-time feed"
            )


def pit_asof_join(
    left: pl.DataFrame,
    right: pl.DataFrame,
    *,
    left_time: str = "as_of",
    right_time: str = "observed_at",
    by: str | list[str] | None = None,
    tolerance: timedelta | None = None,
) -> pl.DataFrame:
    """Backward as-of join that uses ``observed_at`` on the right frame.

    This is the canonical PIT join: for each row in ``left`` at time ``t``,
    pick the latest row in ``right`` with ``observed_at <= t``. Any code path
    that joins data should use this, not Polars' raw ``join_asof``, to avoid
    accidentally joining on ``as_of`` (which leaks future knowledge).
    """
    if right_time not in right.columns:
        raise ValueError(f"right frame must have column '{right_time}'")
    if left_time not in left.columns:
        raise ValueError(f"left frame must have column '{left_time}'")

    left_sorted = left.sort(left_time)
    right_sorted = right.sort(right_time)

    join_kwargs: dict[str, object] = {
        "left_on": left_time,
        "right_on": right_time,
        "strategy": "backward",
    }
    if by is not None:
        join_kwargs["by"] = by
    if tolerance is not None:
        join_kwargs["tolerance"] = tolerance

    return left_sorted.join_asof(right_sorted, **join_kwargs)  # type: ignore[arg-type]


__all__ = ["PITViolation", "assert_no_lookahead", "pit_asof_join"]
