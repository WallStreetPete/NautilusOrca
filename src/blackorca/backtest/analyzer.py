"""Tearsheet metrics + HTML report.

Computes standard performance statistics on an equity curve. The numbers are
deliberately simple and well-defined — no proprietary risk adjustments here.

Bias note: ``sharpe`` is computed from daily returns assuming 252 trading
days. For sub-daily timeframes, callers should annualize separately.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl


def compute_metrics(
    equity_curve: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    initial_capital: float,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    if equity_curve.is_empty():
        return {}

    eq = equity_curve.get_column("equity").to_numpy()
    n = len(eq)
    rets = np.diff(eq) / eq[:-1] if n > 1 else np.array([0.0])

    total_return = float(eq[-1] / initial_capital - 1.0)
    ann_return = float((1.0 + total_return) ** (periods_per_year / max(n, 1)) - 1.0)
    daily_excess = rets - risk_free_rate / periods_per_year
    std = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    sharpe = (
        float(np.mean(daily_excess) / std * np.sqrt(periods_per_year))
        if std > 1e-12
        else 0.0
    )
    downside = rets[rets < 0]
    dstd = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (
        float(np.mean(daily_excess) / dstd * np.sqrt(periods_per_year))
        if dstd > 1e-12
        else 0.0
    )
    # Max drawdown
    peaks = np.maximum.accumulate(eq)
    dd = (eq - peaks) / peaks
    max_dd = float(dd.min())
    calmar = float(ann_return / abs(max_dd)) if max_dd < 0 else 0.0

    # Trades stats
    n_trades = trades.height
    hit_rate = 0.0
    profit_factor = 0.0
    avg_win = 0.0
    avg_loss = 0.0
    if n_trades > 0 and "side" in trades.columns:
        # Naive realized P&L per round trip is out of scope here;
        # we report trade-level cost statistics instead.
        commissions = float(trades.get_column("commission").sum())
        slippage = float(trades.get_column("slippage_bps").mean())
        return {
            "total_return": total_return,
            "annualized_return": ann_return,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "volatility_annualized": std * float(np.sqrt(periods_per_year)),
            "n_trades": float(n_trades),
            "total_commission_usd": commissions,
            "avg_slippage_bps": slippage,
            "hit_rate": hit_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "final_equity": float(eq[-1]),
        }
    return {
        "total_return": total_return,
        "annualized_return": ann_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "volatility_annualized": std * float(np.sqrt(periods_per_year)),
        "n_trades": float(n_trades),
        "final_equity": float(eq[-1]),
    }


def render_html_tearsheet(
    metrics: dict[str, float],
    equity_curve: pl.DataFrame,
    *,
    title: str,
    out_path: str | Path,
) -> Path:
    """Render a minimal stand-alone HTML tearsheet (no JS framework)."""
    rows = "\n".join(
        f"<tr><td>{k}</td><td>{v:,.4f}</td></tr>" for k, v in sorted(metrics.items())
    )
    pts = ",".join(
        f"[{int(t.timestamp() * 1000)},{v:.4f}]"
        for t, v in zip(
            equity_curve.get_column("timestamp").to_list(),
            equity_curve.get_column("equity").to_list(),
            strict=True,
        )
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 960px; margin: 2rem auto; }}
h1 {{ font-weight: 600; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ddd; padding: 0.4rem 0.8rem; }}
svg {{ width: 100%; height: 320px; background: #f8f8f8; }}
</style></head><body>
<h1>{title}</h1>
<h2>Metrics</h2>
<table><thead><tr><th>name</th><th>value</th></tr></thead><tbody>
{rows}
</tbody></table>
<h2>Equity curve</h2>
<svg id=c></svg>
<script>
const pts = [{pts}];
const svg = document.getElementById('c');
const w = svg.clientWidth, h = svg.clientHeight, pad = 20;
const xs = pts.map(p=>p[0]), ys = pts.map(p=>p[1]);
const minX = Math.min(...xs), maxX = Math.max(...xs);
const minY = Math.min(...ys), maxY = Math.max(...ys);
const sx = x => pad + (x-minX)/(maxX-minX)*(w-2*pad);
const sy = y => h-pad - (y-minY)/(maxY-minY)*(h-2*pad);
const d = pts.map((p,i)=>(i===0?'M':'L')+sx(p[0])+','+sy(p[1])).join(' ');
svg.innerHTML = '<path d="'+d+'" fill="none" stroke="#185abd" stroke-width="2"/>';
</script>
</body></html>
"""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


__all__ = ["compute_metrics", "render_html_tearsheet"]
