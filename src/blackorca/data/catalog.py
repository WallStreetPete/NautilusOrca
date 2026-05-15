"""Parquet-backed data catalog.

A thin wrapper around partitioned Parquet on local disk or S3. Schema-compatible
with Nautilus Trader's ``ParquetDataCatalog`` so a swap-in later is mechanical.

Layout::

    {root}/bars/{aggregation}/{symbol}/year={YYYY}/part-*.parquet
    {root}/fundamentals/{symbol}/part-*.parquet
    {root}/alt/{kind}/part-*.parquet
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from blackorca.config import get_settings
from blackorca.data.contracts import ALT_SCHEMA, BAR_SCHEMA, FUNDAMENTAL_SCHEMA, BarAggregation
from blackorca.data.pit import assert_no_lookahead
from blackorca.logging import get_logger

log = get_logger(__name__)


class Catalog:
    """Read/write market & alt data partitioned by symbol and year."""

    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            root = get_settings().catalog_path
        self.root = root  # may be a Path or str (S3 URI)

    # ------------------------------------------------------------------
    # path helpers
    # ------------------------------------------------------------------

    @property
    def is_s3(self) -> bool:
        return isinstance(self.root, str) and self.root.startswith("s3://")

    def _join(self, *parts: str) -> str:
        if self.is_s3:
            return "/".join([str(self.root).rstrip("/"), *parts])
        p = Path(self.root)
        for part in parts:
            p = p / part
        return str(p)

    def _ensure_local(self, path: str) -> None:
        if not self.is_s3:
            Path(path).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # bars
    # ------------------------------------------------------------------

    def write_bars(self, df: pl.DataFrame, *, validate_pit: bool = True) -> int:
        """Append a Polars frame of bars to the catalog.

        Partitions by (aggregation, symbol, year). Returns rows written.
        """
        if df.is_empty():
            return 0
        if validate_pit:
            assert_no_lookahead(df, source="catalog.write_bars")

        # Validate columns
        missing = set(BAR_SCHEMA.keys()) - set(df.columns)
        if missing:
            raise ValueError(f"missing bar columns: {missing}")

        # Add a year column for partitioning, then write per-(agg, sym, year)
        df = df.with_columns(year=pl.col("as_of").dt.year())
        n = 0
        for (agg, sym, year), group in df.group_by(["aggregation", "symbol", "year"]):
            path = self._join("bars", str(agg), str(sym), f"year={int(year)}")
            self._ensure_local(path)
            file_path = path + "/part.parquet"
            group_to_write = group.drop("year").sort("as_of")
            # Merge with existing if present
            if not self.is_s3 and Path(file_path).exists():
                existing = pl.read_parquet(file_path)
                group_to_write = (
                    pl.concat([existing, group_to_write], how="vertical_relaxed")
                    .unique(subset=["symbol", "as_of"], keep="last")
                    .sort("as_of")
                )
            group_to_write.write_parquet(file_path)
            n += group_to_write.height
        log.info("catalog.write_bars", rows=n, root=str(self.root))
        return n

    def read_bars(
        self,
        symbols: list[str] | str,
        start: date | datetime,
        end: date | datetime,
        aggregation: BarAggregation = BarAggregation.DAY,
    ) -> pl.DataFrame:
        if isinstance(symbols, str):
            symbols = [symbols]

        frames: list[pl.DataFrame] = []
        for sym in symbols:
            base = self._join("bars", aggregation.value, sym)
            if self.is_s3:
                pattern = base + "/year=*/part.parquet"
                try:
                    frames.append(pl.read_parquet(pattern))
                except Exception:
                    continue
            else:
                base_path = Path(base)
                if not base_path.exists():
                    continue
                files = list(base_path.glob("year=*/part.parquet"))
                if not files:
                    continue
                frames.append(pl.concat([pl.read_parquet(f) for f in files], how="vertical_relaxed"))

        if not frames:
            return pl.DataFrame(schema=BAR_SCHEMA)

        out = pl.concat(frames, how="vertical_relaxed").sort(["symbol", "as_of"])
        start_dt = self._to_utc(start)
        end_dt = self._to_utc(end)
        return out.filter((pl.col("as_of") >= start_dt) & (pl.col("as_of") <= end_dt))

    def list_instruments(self, aggregation: BarAggregation = BarAggregation.DAY) -> list[str]:
        base = self._join("bars", aggregation.value)
        if self.is_s3:
            return []  # listing S3 needs s3fs; out of scope for v0
        p = Path(base)
        if not p.exists():
            return []
        return sorted([d.name for d in p.iterdir() if d.is_dir()])

    # ------------------------------------------------------------------
    # fundamentals
    # ------------------------------------------------------------------

    def write_fundamentals(self, df: pl.DataFrame) -> int:
        if df.is_empty():
            return 0
        assert_no_lookahead(df, source="catalog.write_fundamentals")
        missing = set(FUNDAMENTAL_SCHEMA.keys()) - set(df.columns)
        if missing:
            raise ValueError(f"missing fundamentals columns: {missing}")
        n = 0
        for (sym,), group in df.group_by(["symbol"]):
            path = self._join("fundamentals", str(sym))
            self._ensure_local(path)
            file_path = path + "/part.parquet"
            if not self.is_s3 and Path(file_path).exists():
                existing = pl.read_parquet(file_path)
                group = (
                    pl.concat([existing, group], how="vertical_relaxed")
                    .unique(subset=["symbol", "field", "period"], keep="last")
                    .sort(["field", "as_of"])
                )
            group.write_parquet(file_path)
            n += group.height
        return n

    def read_fundamentals(self, symbol: str) -> pl.DataFrame:
        path = Path(self._join("fundamentals", symbol, "part.parquet"))
        if self.is_s3 or not path.exists():
            return pl.DataFrame(schema=FUNDAMENTAL_SCHEMA)
        return pl.read_parquet(path)

    # ------------------------------------------------------------------
    # alt
    # ------------------------------------------------------------------

    def write_alt(self, df: pl.DataFrame) -> int:
        if df.is_empty():
            return 0
        assert_no_lookahead(df, source="catalog.write_alt")
        n = 0
        for (kind,), group in df.group_by(["kind"]):
            path = self._join("alt", str(kind))
            self._ensure_local(path)
            file_path = path + "/part.parquet"
            if not self.is_s3 and Path(file_path).exists():
                existing = pl.read_parquet(file_path)
                group = pl.concat([existing, group], how="vertical_relaxed").sort("as_of")
            group.write_parquet(file_path)
            n += group.height
        return n

    def read_alt(self, kind: str) -> pl.DataFrame:
        path = Path(self._join("alt", kind, "part.parquet"))
        if self.is_s3 or not path.exists():
            return pl.DataFrame(schema=ALT_SCHEMA)
        return pl.read_parquet(path)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _to_utc(d: date | datetime) -> datetime:
        if isinstance(d, datetime):
            if d.tzinfo is None:

                return d.replace(tzinfo=UTC)
            return d
        from datetime import datetime as _dt

        return _dt(d.year, d.month, d.day, tzinfo=UTC)

    def stats(self) -> dict[str, Any]:
        if self.is_s3:
            return {"backend": "s3", "root": self.root}
        root = Path(self.root)
        if not root.exists():
            return {"backend": "local", "root": str(root), "files": 0, "bytes": 0}
        files = list(root.rglob("*.parquet"))
        return {
            "backend": "local",
            "root": str(root),
            "files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
        }


__all__ = ["Catalog"]
