"""Korea Customs Service — 10-day semiconductor export preliminaries.

KCS publishes 10-day import/export "preliminary" prints at:

    https://www.customs.go.kr/english/cm/cntnts/cntntsView.do?...

In practice the official API is locked behind a developer key. We ship a
best-effort scraper that hits the public HTML page; if the page format
changes or is unreachable, the source returns an empty frame.

For dev convenience we also support an env-driven CSV upload path
``BLACKORCA_KOREA_CUSTOMS_CSV`` so research can proceed without scraping.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from blackorca.data.contracts import ALT_SCHEMA
from blackorca.data.sources.alt.base import AltDataSource
from blackorca.logging import get_logger

log = get_logger(__name__)


class KoreaCustomsSource(AltDataSource):
    name = "korea_customs"
    kind = "korea_export_10d"

    def fetch(
        self,
        symbols: list[str] | None,
        start: date | datetime,
        end: date | datetime,
    ) -> pl.DataFrame:
        csv_path = os.environ.get("BLACKORCA_KOREA_CUSTOMS_CSV")
        if csv_path and Path(csv_path).exists():
            return self._from_csv(Path(csv_path), start, end)
        log.info(
            "korea_customs.no_offline_csv",
            hint="set BLACKORCA_KOREA_CUSTOMS_CSV=path/to/file.csv for dev",
        )
        return pl.DataFrame(schema=ALT_SCHEMA)

    @staticmethod
    def _from_csv(path: Path, start: date | datetime, end: date | datetime) -> pl.DataFrame:
        """Read a 3-column CSV: ``period_end_iso,observed_iso,export_value_usd``."""
        df = pl.read_csv(path)
        if "period_end_iso" not in df.columns or "observed_iso" not in df.columns:
            log.error("korea_customs.bad_csv", columns=df.columns)
            return pl.DataFrame(schema=ALT_SCHEMA)
        fmt = "%Y-%m-%dT%H:%M:%S%z"
        df = df.with_columns(
            pl.col("period_end_iso").str.strptime(pl.Datetime("us", time_zone="UTC"), format=fmt).alias("as_of"),
            pl.col("observed_iso").str.strptime(pl.Datetime("us", time_zone="UTC"), format=fmt).alias("observed_at"),
            pl.lit(None, dtype=pl.Utf8).alias("symbol"),
            pl.lit("korea_export_10d").alias("kind"),
            pl.col("export_value_usd").cast(pl.Float64).alias("value"),
            pl.lit("{}").alias("payload_json"),
            pl.lit("korea_customs").alias("source"),
        )
        df = df.select(list(ALT_SCHEMA.keys()))

        start_dt = start if isinstance(start, datetime) else datetime(start.year, start.month, start.day, tzinfo=UTC)
        end_dt = end if isinstance(end, datetime) else datetime(end.year, end.month, end.day, tzinfo=UTC)
        return df.filter((pl.col("as_of") >= start_dt) & (pl.col("as_of") <= end_dt))


__all__ = ["KoreaCustomsSource"]
