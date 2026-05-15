# Data Contracts

Authoritative reference for every data schema that flows through the
catalog and the strategy layer. Schemas are defined in
`src/blackorca/data/contracts.py`.

## Universal PIT timestamps

Every row carries two timestamps. **They are not interchangeable.**

| Field         | Meaning                                                                |
|---------------|------------------------------------------------------------------------|
| `as_of`       | The moment of the world this row describes. Period end / event time. |
| `observed_at` | When *we* learned the row. Disclosure / filing / ingestion time.       |

Invariant: `observed_at >= as_of`. Enforced by `data.pit.assert_no_lookahead`.

## Bars

```python
BarData(
    symbol: str,
    aggregation: BarAggregation,   # 1s, 1m, 5m, 15m, 1h, 1d, 1w
    open, high, low, close, volume: float,
    vwap: float | None,
    trade_count: int | None,
    as_of, observed_at: datetime
)
```

OHLC invariants:
- `low <= open <= high`
- `low <= close <= high`
- `volume >= 0`

For daily bars: `observed_at == as_of` (the close *is* the disclosure).
For tick / minute bars from delayed feeds: `observed_at = as_of + delay`.

## Trades / Quotes

```python
TradeData(symbol, price, size, aggressor_side?, as_of, observed_at)
QuoteData(symbol, bid_price, ask_price, bid_size, ask_size, as_of, observed_at)
```

Quote invariant: `ask_price >= bid_price`.

## Fundamentals

```python
FundamentalData(
    symbol, field,      # e.g. "eps_reported"
    value: float,
    period: str,        # "2024Q1"
    source: str,
    as_of: datetime,         # = period end
    observed_at: datetime,   # = filing timestamp
)
```

The split between `as_of` (period end) and `observed_at` (filing date) is the single biggest source of lookahead bugs in equity research. Always join on `observed_at`.

## Alt-data

```python
AltDataPoint(
    symbol: str | None,         # None for macro / index alt-data
    kind: str,                  # "twse_monthly_rev", "korea_export_10d", "news"
    value: float | None,
    payload: dict[str, ...],
    source: str,
    as_of, observed_at: datetime,
)
```

`kind` namespaces alt-data tables in the catalog: `data/catalog/alt/{kind}/part.parquet`. Use a consistent kebab-case convention.

## News

```python
NewsItem(
    symbol: str | None,
    headline: str,
    body: str | None,
    url: str | None,
    sentiment: float | None,         # [-1, 1]
    classification: str | None,
    source: str,
    as_of, observed_at: datetime,
)
```

## Catalog layout

```
data/catalog/
├── bars/{aggregation}/{symbol}/year={YYYY}/part.parquet
├── fundamentals/{symbol}/part.parquet
└── alt/{kind}/part.parquet
```

This layout works for both local disk and `s3://` URIs (set `BLACKORCA_CATALOG_PATH=s3://…`).
