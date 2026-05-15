"""Ingestion orchestration.

Composes a :class:`MarketDataSource` and a :class:`Catalog` into a single
``ingest_bars`` function that handles batching, retries, and the PIT gate.
"""

from __future__ import annotations

from datetime import date, datetime

from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.data.pit import assert_no_lookahead
from blackorca.data.sources.base import MarketDataSource
from blackorca.logging import get_logger

log = get_logger(__name__)


def ingest_bars(
    source: MarketDataSource,
    catalog: Catalog,
    symbols: list[str],
    start: date | datetime,
    end: date | datetime,
    aggregation: BarAggregation = BarAggregation.DAY,
    batch_size: int = 25,
) -> int:
    """Fetch bars from ``source`` in batches and write to the ``catalog``.

    Returns the total number of rows written.
    """
    total = 0
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        log.info("ingest.batch.start", batch=batch, start=str(start), end=str(end))
        df = source.fetch_bars(batch, start, end, aggregation)
        if df.is_empty():
            log.warning("ingest.batch.empty", batch=batch)
            continue
        assert_no_lookahead(df, source=source.name)
        total += catalog.write_bars(df)
    log.info("ingest.done", total_rows=total)
    return total


__all__ = ["ingest_bars"]
