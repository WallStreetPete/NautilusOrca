export default function ConsolePage() {
  const consoleUrl = process.env.NEXT_PUBLIC_CONSOLE_URL ?? "";
  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <h1 className="text-3xl font-semibold mb-3">Apex Console</h1>
      <p className="text-zinc-400 text-sm max-w-3xl mb-8">
        The full interactive console (Streamlit) — 11 pages: data ingest, charts,
        backtests, ML training, agent research loop, risk simulator, paper trading,
        test runner, logs & metrics. Persistent state, long-running compute, and
        subprocess-based test runner all require a real container — Railway is the
        right home for that.
      </p>

      {consoleUrl ? (
        <>
          <a
            href={consoleUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-cyan-500 text-zinc-900 font-medium hover:bg-cyan-400 transition-colors mb-6"
          >
            Open the Console →
          </a>
          <div className="rounded-xl border border-zinc-800/80 overflow-hidden">
            <iframe src={consoleUrl} className="w-full h-[760px] bg-zinc-950" />
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-yellow-700/40 bg-yellow-950/20 p-6 text-sm text-yellow-200">
          The Console URL is not configured yet. Set the{" "}
          <code className="font-mono text-xs bg-zinc-800 px-1.5 py-0.5 rounded">
            NEXT_PUBLIC_CONSOLE_URL
          </code>{" "}
          environment variable in Vercel to your Railway deployment URL
          (e.g. <span className="font-mono text-xs">https://nautilus-orca.up.railway.app</span>).
          Until then this page is a placeholder.
        </div>
      )}

      <h2 className="text-xl font-semibold mt-12 mb-3">Pages in the Console</h2>
      <div className="grid sm:grid-cols-2 gap-3 text-sm">
        {[
          ["🏠 Home", "System health, recent runs, agent spend ledger, last backtest equity"],
          ["📊 Data Catalog", "Ingest from yfinance/Databento, browse, candlestick charts, PIT check"],
          ["🧬 Universe", "Tier filter + interactive dependency graph"],
          ["🧪 Research", "Event study, IC decay, factor study"],
          ["⚡ Backtest", "Run any registered strategy, view tearsheet, browse history"],
          ["🤖 ML Pipeline", "Feature explorer, training, model registry"],
          ["🧠 Agents", "Hypothesis, full research loop, code review, memory"],
          ["🛡️ Risk", "Limits, pre-trade simulator, kill-switch tester"],
          ["📈 Paper Trading", "Start/stop the live node, view positions"],
          ["✅ Tests", "Run pytest with live output streaming"],
          ["📋 Logs & Metrics", "Prometheus snapshot, run registry, Grafana"],
        ].map(([t, b]) => (
          <div key={t} className="rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3">
            <div className="font-medium">{t}</div>
            <div className="text-zinc-400 text-xs mt-0.5">{b}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
