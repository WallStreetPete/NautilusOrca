export default function ArchitecturePage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <h1 className="text-3xl font-semibold mb-3">Architecture</h1>
      <p className="text-zinc-400 text-sm max-w-3xl mb-10">
        Five interfaces, three runtimes (sim / paper / live), one Strategy class.
      </p>

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-6 font-mono text-xs leading-6 overflow-x-auto">
        <pre>{`                       ┌──────────────────┐
                       │  Agent Loop      │
                       │ (LangGraph +     │
                       │  Anthropic API)  │
                       └────────┬─────────┘
                                │ proposes hypotheses, reviews code
                                ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────────┐
│  Data    │→ │  Features  │→ │  Strategy    │→ │  Execution   │
│  (PIT)   │  │  (PIT)     │  │  (one class) │  │ (sim|paper|  │
│ Polars   │  │ sklearn    │  │ + Risk gate  │  │  live)       │
│ Parquet  │  │ pipelines  │  │              │  │              │
└──────────┘  └────────────┘  └──────────────┘  └──────────────┘
       ▲              ▲              ▲                 ▲
       │              │              │                 │
       └──── structlog + prometheus + opentelemetry ───┘`}</pre>
      </div>

      <h2 className="text-xl font-semibold mt-10 mb-4">Layers</h2>
      <div className="space-y-4 text-sm">
        {[
          ["Data plane", "Pydantic contracts with the two-timestamp invariant (as_of + observed_at). Polars + DuckDB + Parquet. Sources: yfinance, Databento, Alpha Vantage, TWSE scraper, Korea Customs, GDELT news. The PIT validator runs at ingest and inside every test."],
          ["Universe & dependency graph", "26 hand-curated names + 19 hand-curated supplier edges with confidence and expected lag. Used by the tier-1 → tier-2 drift strategy."],
          ["Strategy + risk + backtest", "Event-driven engine. T+1 fills against the next bar. Realistic slippage + square-root impact + partial fills. Pre-trade risk with 7 explicit rejection codes. Kill switch for drawdown + daily loss."],
          ["Research toolkit", "Market-adjusted event study with t-stats. IC + IC decay. Quintile factor research. Walk-forward CV with embargo."],
          ["ML pipeline", "PIT-aware features (returns / vol / momentum-z / microstructure). sklearn-style pipeline that refuses inputs failing PIT checks. Versioned model registry. Walk-forward training (LightGBM / Ridge)."],
          ["Agent layer", "Anthropic API wrapper with structured Pydantic output, retries, token + cost ledger. Markdown prompts. 6 typed tools (run_backtest, run_event_study, query_dependency_graph, …). pgvector + in-memory dual memory store."],
          ["Live trading node", "Same BlackOrcaStrategy class, same risk gate, real broker adapter (Alpaca). The simulated venue and live venue implement the same ExecutionAdapter protocol."],
        ].map(([t, b]) => (
          <div key={t} className="rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-4">
            <div className="font-medium text-cyan-300 mb-1">{t}</div>
            <p className="text-zinc-300 leading-relaxed">{b}</p>
          </div>
        ))}
      </div>

      <h2 className="text-xl font-semibold mt-10 mb-4">Nautilus Trader</h2>
      <p className="text-sm text-zinc-300 leading-relaxed">
        Designed to host Nautilus Trader as the execution engine. The internal engine
        uses Nautilus-compatible interfaces (Bar / Trade / Quote events, OrderRequest,
        ExecutionAdapter) so a NautilusBacktestAdapter and NautilusTradingNode can drop in
        without strategy changes.
      </p>
    </div>
  );
}
