"""Fundamental data source (PIT-aware).

We use Alpha Vantage as a free dev source for *current* fundamentals and
expose a generic ``FundamentalsSource`` interface that a Sharadar / FactSet /
S&P Compustat adapter can drop into later. The critical point is that
``observed_at`` is the *filing date*, not the period end.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import httpx
import polars as pl

from blackorca.config import get_settings
from blackorca.data.contracts import FUNDAMENTAL_SCHEMA
from blackorca.data.sources.base import AltDataSource
from blackorca.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


class AlphaVantageFundamentals(AltDataSource):
    """Pulls overview + earnings via Alpha Vantage.

    Notes:
        - The free tier allows 5 calls/min and 500/day. Stay within it.
        - ``observed_at`` is the reported filing date; ``as_of`` is the
          fiscal period end.
    """

    name = "alpha_vantage"
    kind = "fundamentals"

    def __init__(self, base_url: str = "https://www.alphavantage.co/query"):
        self.base_url = base_url

    def is_available(self) -> bool:
        return get_settings().alpha_vantage_api_key is not None

    def fetch(
        self,
        symbols: list[str] | None,
        start: date | datetime,
        end: date | datetime,
    ) -> pl.DataFrame:
        if not self.is_available() or not symbols:
            return pl.DataFrame(schema=FUNDAMENTAL_SCHEMA)
        key = get_settings().alpha_vantage_api_key
        assert key is not None  # checked above
        api_key = key.get_secret_value()

        rows: list[dict[str, Any]] = []
        with httpx.Client(timeout=15.0) as client:
            for sym in symbols:
                try:
                    r = client.get(
                        self.base_url,
                        params={"function": "EARNINGS", "symbol": sym, "apikey": api_key},
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    log.warning("alpha_vantage.fetch_failed", symbol=sym, error=str(e))
                    continue

                for q in data.get("quarterlyEarnings", []):
                    try:
                        period_end = datetime.fromisoformat(q["fiscalDateEnding"]).replace(
                            tzinfo=UTC
                        )
                        reported = datetime.fromisoformat(q["reportedDate"]).replace(
                            tzinfo=UTC
                        )
                    except Exception:
                        continue
                    if period_end < datetime.fromisoformat(str(start)).replace(tzinfo=UTC):
                        continue
                    if period_end > datetime.fromisoformat(str(end)).replace(tzinfo=UTC):
                        continue
                    try:
                        eps = float(q["reportedEPS"])
                    except Exception:
                        continue
                    rows.append(
                        {
                            "symbol": sym.upper(),
                            "field": "eps_reported",
                            "value": eps,
                            "period": q["fiscalDateEnding"],
                            "as_of": period_end,
                            "observed_at": reported,
                            "source": "alpha_vantage",
                        }
                    )

        if not rows:
            return pl.DataFrame(schema=FUNDAMENTAL_SCHEMA)
        return pl.from_dicts(rows).cast(FUNDAMENTAL_SCHEMA)  # type: ignore[arg-type]


__all__ = ["AlphaVantageFundamentals"]
