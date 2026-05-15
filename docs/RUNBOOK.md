# Runbook — paper / live trading operations

This is the on-call procedure. Read it cold before you touch live capital.

## 1. Pre-startup checklist

- [ ] `git status` clean on the deploy branch
- [ ] `uv run pytest -m "not live"` green locally
- [ ] `uv run ruff check src tests` clean
- [ ] `uv run mypy src` clean
- [ ] `docker compose ps` shows postgres/redis/prometheus/grafana healthy
- [ ] `uv run blackorca health` reports `anthropic=set`, `alpaca=set`
- [ ] Latest market data ingested today (`uv run python scripts/ingest_market_data.py --universe semis`)
- [ ] Risk limits in `config/paper.yaml` (or `live.yaml`) reviewed since last incident
- [ ] Kill switch test fired this week: `uv run pytest tests/unit/test_risk_limits.py::test_kill_switch_drawdown`

## 2. Startup

```bash
# Paper
BLACKORCA_PROFILE=paper uv run python scripts/start_paper_trading.py --strategy=sma_cross --symbol=NVDA

# Live (you must explicitly set profile)
BLACKORCA_PROFILE=live uv run python scripts/start_paper_trading.py --strategy=sma_cross --symbol=NVDA
```

Confirm in Grafana that:
- `blackorca_nav_usd` is reporting
- `blackorca_orders_submitted_total` increments after the first signal
- `blackorca_fills_total` matches orders submitted within a minute

## 3. Monitoring (during the session)

| Signal                                 | Threshold       | Action                            |
|----------------------------------------|-----------------|-----------------------------------|
| `blackorca_pnl_usd` < -1% of NAV       | within session  | Check kill-switch state; review last 10 fills |
| `blackorca_orders_rejected_total` rate | > 1/min         | Look up rejection reasons in logs |
| `blackorca_data_fetch_latency` p95     | > 5s            | Check Databento/yfinance status   |
| Logs: `kill_switch.tripped`            | any             | **All hands**; see §4              |

## 4. Kill switch trip — what to do

1. The trading node has already requested a flatten. **Verify all positions are flat** in Alpaca's UI.
2. Capture:
   - The last 200 log lines
   - The `kill_switch.tripped` event payload (reason field)
   - The Grafana snapshot for the session
3. **Do not reset** the kill switch the same day. Post-mortem first.

## 5. Post-mortem template

```
# Post-mortem — YYYY-MM-DD — <one-line summary>

## What happened
…

## Why
- Root cause(s):
- Contributing factors:

## What we caught
- Detection time:
- Mitigation time:

## What we missed
- Gaps in tests:
- Gaps in monitoring:

## Action items
- [ ] (owner) (deadline)
```

## 6. Shutdown

```bash
# Send SIGINT to the trading node process.
# It will flush pending orders, drain fills, and emit a final tearsheet.
```

Confirm:
- All positions flat (or intentionally held — log the rationale).
- Final NAV reconciles with Alpaca account view.
- Tearsheet saved under `data/reports/`.
