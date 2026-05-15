"""Taiwan Stock Exchange monthly revenue scraper.

TWSE publishes monthly revenue (營業收入) on a per-company basis around the
10th of the following month at:

    https://mops.twse.com.tw/nas/t21/sii/t21sc03_<roc_year>_<month>_0.html

We support a fixed set of semis: TSMC (2330), UMC (2303), MediaTek (2454),
ASE (3711). Output rows carry ``as_of`` = month-end and ``observed_at`` =
the 10th of the following month (the release window).

Defensive: if the page format changes or the request fails, we log and
return an empty frame instead of crashing. Calling code should treat alt
sources as best-effort.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime

import httpx
import polars as pl

from blackorca.data.contracts import ALT_SCHEMA
from blackorca.data.sources.alt.base import AltDataSource
from blackorca.logging import get_logger
from blackorca.metrics import DATA_FETCH_LATENCY

log = get_logger(__name__)


_TICKER_TO_TWSE = {
    "TSM": "2330",     # TSMC
    "UMC": "2303",
    "MTK": "2454",     # MediaTek (no US ADR; included for completeness)
    "ASE": "3711",     # ASE Tech (US ticker is ASX, but we use ASE for the parent)
}


class TaiwanTwseSource(AltDataSource):
    name = "twse"
    kind = "twse_monthly_rev"

    def __init__(self, sleep_between: float = 0.5) -> None:
        self.sleep_between = sleep_between

    def fetch(
        self,
        symbols: list[str] | None,
        start: date | datetime,
        end: date | datetime,
    ) -> pl.DataFrame:
        targets = sorted(set(symbols or list(_TICKER_TO_TWSE)))
        targets = [s for s in targets if s in _TICKER_TO_TWSE]
        if not targets:
            return pl.DataFrame(schema=ALT_SCHEMA)

        start_d = start if isinstance(start, date) else start.date()
        end_d = end if isinstance(end, date) else end.date()

        # Iterate months
        rows: list[dict[str, object]] = []
        cursor = date(start_d.year, start_d.month, 1)
        end_month = date(end_d.year, end_d.month, 1)
        while cursor <= end_month:
            roc_year = cursor.year - 1911
            month = cursor.month
            url = (
                f"https://mops.twse.com.tw/nas/t21/sii/t21sc03_"
                f"{roc_year}_{month}_0.html"
            )
            t0 = time.perf_counter()
            try:
                resp = httpx.get(url, timeout=15.0, headers={"User-Agent": "blackorca/0.1"})
                DATA_FETCH_LATENCY.labels(source="twse").observe(time.perf_counter() - t0)
                resp.raise_for_status()
                rows.extend(self._parse_page(resp.text, cursor, targets))
            except Exception as e:
                log.warning("twse.fetch_failed", url=url, error=str(e))

            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
            time.sleep(self.sleep_between)

        if not rows:
            return pl.DataFrame(schema=ALT_SCHEMA)
        return pl.from_dicts(rows).cast(ALT_SCHEMA)  # type: ignore[arg-type]

    @staticmethod
    def _parse_page(html: str, month: date, targets: list[str]) -> list[dict[str, object]]:
        """Heuristic parser: TWSE pages are simple tables with company code
        in the first column and revenue in the third. We accept any layout
        that contains a row whose first cell matches one of our codes."""
        from bs4 import BeautifulSoup

        out: list[dict[str, object]] = []
        soup = BeautifulSoup(html, "html.parser")
        code_to_ticker = {v: k for k, v in _TICKER_TO_TWSE.items()}
        codes = {_TICKER_TO_TWSE[t] for t in targets}

        # Last day of the month (as_of) and 10th of the next month (observed_at)
        if month.month == 12:
            as_of = datetime(month.year, 12, 31, 15, 0, tzinfo=UTC)
            observed_at = datetime(month.year + 1, 1, 10, 7, 0, tzinfo=UTC)
        else:
            from calendar import monthrange

            last_day = monthrange(month.year, month.month)[1]
            as_of = datetime(month.year, month.month, last_day, 15, 0, tzinfo=UTC)
            observed_at = datetime(month.year, month.month + 1, 10, 7, 0, tzinfo=UTC)

        for row in soup.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            code = cells[0]
            if code not in codes:
                continue
            # Find the first numeric cell after the code
            for cell in cells[1:]:
                m = re.search(r"-?[\d,]+\.?\d*", cell)
                if m:
                    try:
                        value = float(m.group(0).replace(",", ""))
                        out.append(
                            {
                                "symbol": code_to_ticker[code],
                                "kind": "twse_monthly_rev",
                                "value": value,
                                "payload_json": "{}",
                                "as_of": as_of,
                                "observed_at": observed_at,
                                "source": "twse",
                            }
                        )
                        break
                    except ValueError:
                        continue
        return out


__all__ = ["TaiwanTwseSource"]
