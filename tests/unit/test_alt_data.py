"""Alt-data source tests.

These tests don't hit the network — they exercise the parsing and PIT
correctness with fixture inputs. Live network tests live under the
``live`` marker.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from blackorca.data.contracts import ALT_SCHEMA
from blackorca.data.pit import assert_no_lookahead
from blackorca.data.sources.alt.korea_customs import KoreaCustomsSource


def test_korea_customs_csv_loads(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    csv_path = tmp_path / "korea.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["period_end_iso", "observed_iso", "export_value_usd"])
        w.writerow(["2024-01-10T00:00:00+00:00", "2024-01-13T00:00:00+00:00", "1000000"])
        w.writerow(["2024-01-20T00:00:00+00:00", "2024-01-23T00:00:00+00:00", "1100000"])

    monkeypatch.setenv("BLACKORCA_KOREA_CUSTOMS_CSV", str(csv_path))
    src = KoreaCustomsSource()
    df = src.fetch(None, datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC))
    assert df.height == 2
    # PIT clean
    assert_no_lookahead(df, source="korea_test")
    # Schema match
    assert set(df.columns) == set(ALT_SCHEMA.keys())


def test_korea_customs_no_csv_returns_empty(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("BLACKORCA_KOREA_CUSTOMS_CSV", raising=False)
    src = KoreaCustomsSource()
    df = src.fetch(None, datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC))
    assert df.is_empty()
