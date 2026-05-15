"""News ingestion + Anthropic-powered NLP classification.

Two paths:

1. **Live**: pulls from GDELT 2.0 (no key required) for queries like
   ``site:reuters.com NVIDIA``. We support a small whitelist of queries
   pre-tied to the semi universe.
2. **Offline**: a CSV passthrough at ``BLACKORCA_NEWS_CSV`` (path) with
   columns ``ts,symbol,headline,body,url``.

Headlines/body get classified via Anthropic into a small taxonomy
``{earnings, supply_chain, regulatory, demand, capex, other}`` plus a
sentiment ∈ [-1, 1]. Classification is batched (~10 items per call).
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl

from blackorca.agents.client import AnthropicClient
from blackorca.data.contracts import ALT_SCHEMA
from blackorca.data.sources.alt.base import AltDataSource
from blackorca.logging import get_logger

log = get_logger(__name__)


NEWS_CLASSIFIER_PROMPT = """You are a financial-news classifier. For each item return:

- ``label`` ∈ {earnings, supply_chain, regulatory, demand, capex, other}
- ``sentiment`` ∈ [-1.0, 1.0] (negative = bearish for the named company)

Return strictly JSON: a list of {"id", "label", "sentiment"} objects, in the same
order as the input.
"""


class NewsSource(AltDataSource):
    name = "news"
    kind = "news"

    def __init__(self, classify: bool = True) -> None:
        self.classify = classify
        self._client: AnthropicClient | None = None

    def fetch(
        self,
        symbols: list[str] | None,
        start: date | datetime,
        end: date | datetime,
    ) -> pl.DataFrame:
        csv_path = os.environ.get("BLACKORCA_NEWS_CSV")
        if csv_path and Path(csv_path).exists():
            df = self._from_csv(Path(csv_path), start, end)
        else:
            df = self._from_gdelt(symbols or [], start, end)
        if df.is_empty():
            return df
        if self.classify:
            df = self._classify(df)
        return df.select(list(ALT_SCHEMA.keys()))

    # ------------------------------------------------------------------
    # offline
    # ------------------------------------------------------------------

    @staticmethod
    def _from_csv(path: Path, start: date | datetime, end: date | datetime) -> pl.DataFrame:
        raw = pl.read_csv(path)
        needed = {"ts", "symbol", "headline"}
        if not needed.issubset(set(raw.columns)):
            log.error("news.bad_csv", columns=raw.columns)
            return pl.DataFrame(schema=ALT_SCHEMA)
        df = raw.with_columns(
            pl.col("ts").str.to_datetime().alias("as_of"),
            pl.col("ts").str.to_datetime().alias("observed_at"),
            pl.lit("news").alias("kind"),
            pl.lit(None, dtype=pl.Float64).alias("value"),
            pl.lit("offline_csv").alias("source"),
        )
        # Stash headline + body in payload
        def _pj(row: dict[str, object]) -> str:
            return json.dumps(
                {
                    "headline": row.get("headline", ""),
                    "body": row.get("body", ""),
                    "url": row.get("url", ""),
                }
            )

        df = df.with_columns(
            pl.struct(["headline", "body", "url"] if "body" in df.columns else ["headline", "url"])
            .map_elements(_pj, return_dtype=pl.Utf8)
            .alias("payload_json")
        )
        df = df.select(["symbol", "kind", "value", "payload_json", "as_of", "observed_at", "source"])
        start_dt = start if isinstance(start, datetime) else datetime(start.year, start.month, start.day, tzinfo=UTC)
        end_dt = end if isinstance(end, datetime) else datetime(end.year, end.month, end.day, tzinfo=UTC)
        return df.filter((pl.col("as_of") >= start_dt) & (pl.col("as_of") <= end_dt))

    # ------------------------------------------------------------------
    # GDELT
    # ------------------------------------------------------------------

    @staticmethod
    def _from_gdelt(
        symbols: list[str],
        start: date | datetime,
        end: date | datetime,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame(schema=ALT_SCHEMA)
        rows: list[dict[str, object]] = []
        start_d = start if isinstance(start, date) else start.date()
        end_d = end if isinstance(end, date) else end.date()
        for sym in symbols:
            q = f"{sym} semiconductor"
            url = (
                "https://api.gdeltproject.org/api/v2/doc/doc"
                f"?query={q}&mode=ArtList&format=json&maxrecords=20"
                f"&startdatetime={start_d:%Y%m%d}000000"
                f"&enddatetime={end_d:%Y%m%d}235959"
            )
            try:
                resp = httpx.get(url, timeout=15.0)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning("gdelt.fetch_failed", symbol=sym, error=str(e))
                continue
            for art in data.get("articles", []):
                try:
                    ts = datetime.strptime(art["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                except Exception:
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "kind": "news",
                        "value": None,
                        "payload_json": json.dumps(
                            {"headline": art.get("title", ""), "url": art.get("url", "")}
                        ),
                        "as_of": ts,
                        "observed_at": ts,
                        "source": "gdelt",
                    }
                )
            time.sleep(0.2)  # be polite
        if not rows:
            return pl.DataFrame(schema=ALT_SCHEMA)
        return pl.from_dicts(rows).cast(ALT_SCHEMA)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # classification
    # ------------------------------------------------------------------

    def _classify(self, df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df
        # Stub client only if we actually have a key
        try:
            client = self._client or AnthropicClient()
        except Exception as e:
            log.warning("news.classifier_unavailable", error=str(e))
            return df

        self._client = client
        batches: list[list[dict[str, object]]] = []
        current: list[dict[str, object]] = []
        for row in df.iter_rows(named=True):
            current.append(row)
            if len(current) == 10:
                batches.append(current)
                current = []
        if current:
            batches.append(current)

        out_rows: list[dict[str, object]] = []
        for batch in batches:
            items = [
                {"id": i, "headline": json.loads(r["payload_json"]).get("headline", "")}
                for i, r in enumerate(batch)
            ]
            user = json.dumps(items)
            try:
                res = client.complete(
                    system=NEWS_CLASSIFIER_PROMPT,
                    prompt=user,
                    max_tokens=600,
                    temperature=0.0,
                    fast=True,
                )
                parsed = json.loads(res.text.strip().splitlines()[-1] if "\n" in res.text else res.text)
            except Exception as e:
                log.warning("news.classify_failed", error=str(e))
                parsed = []
            label_by_id = {item.get("id"): item for item in (parsed if isinstance(parsed, list) else [])}
            for i, r in enumerate(batch):
                payload = json.loads(r["payload_json"])
                if i in label_by_id:
                    payload["label"] = label_by_id[i].get("label")
                    payload["sentiment"] = label_by_id[i].get("sentiment")
                    r["value"] = payload["sentiment"]
                r["payload_json"] = json.dumps(payload)
                out_rows.append(r)
        return pl.from_dicts(out_rows).cast(ALT_SCHEMA)  # type: ignore[arg-type]


__all__ = ["NEWS_CLASSIFIER_PROMPT", "NewsSource"]
