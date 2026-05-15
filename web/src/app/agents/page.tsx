"use client";

import { useState } from "react";

type Hypothesis = {
  statement: string;
  mechanism: string;
  universe: string;
  horizon_days: number;
  expected_edge_bps: number;
  falsification_criterion: string;
  required_data: { catalog_kind: string; granularity: string; rationale: string }[];
  estimated_decay_days: number;
  confidence: number;
};

const DEFAULT_CTX = `Universe: NVDA, TSM, AMD, AMAT, KLAC, LRCX, MU, ASML, AVGO.
Recent: TSMC reported monthly revenue +60% YoY for the latest print.
We have daily bars in the catalog and a curated supplier dependency graph
(NVDA -> TSM -> AMAT/KLAC/LRCX, etc).`;

export default function AgentsPage() {
  const [ctx, setCtx] = useState(DEFAULT_CTX);
  const [fast, setFast] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Hypothesis | null>(null);
  const [meta, setMeta] = useState<{ cost: number; model: string } | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    setResult(null);
    setMeta(null);
    try {
      const res = await fetch("/api/hypothesis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context: ctx, fast }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`${res.status}: ${txt}`);
      }
      const data = await res.json();
      setResult(data.hypothesis as Hypothesis);
      setMeta({ cost: data.cost_usd ?? 0, model: data.model });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold mb-2">Agent · hypothesis generator</h1>
        <p className="text-zinc-400 text-sm max-w-3xl">
          Real Anthropic Claude call with structured Pydantic-equivalent (Zod) output.
          The same prompt that runs in the Python agent loop. Typical cost: ~$0.02 per
          call on Sonnet 4.6, ~$0.08 on Opus 4.7.
        </p>
      </div>

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-5">
        <label className="block text-xs uppercase tracking-wider text-zinc-400 mb-2">Universe context</label>
        <textarea
          value={ctx}
          onChange={(e) => setCtx(e.target.value)}
          rows={6}
          className="w-full bg-[#0a0d14] border border-zinc-800 rounded-md p-3 text-sm font-mono text-zinc-200 focus:outline-none focus:border-cyan-700"
        />
        <div className="flex items-center justify-between mt-3">
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={fast}
              onChange={(e) => setFast(e.target.checked)}
              className="accent-cyan-500"
            />
            Use fast model (Sonnet 4.6) — cheaper, ~3x faster
          </label>
          <button
            onClick={generate}
            disabled={loading || !ctx.trim()}
            className="px-4 py-2 rounded-md bg-cyan-500 text-zinc-900 font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-cyan-400 transition-colors text-sm"
          >
            {loading ? "Generating…" : "Generate hypothesis"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-5 rounded-md border border-red-800/60 bg-red-950/30 text-red-300 text-sm p-4">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 rounded-xl border border-cyan-700/30 bg-cyan-950/10 p-6 space-y-5">
          <div>
            <div className="text-xs uppercase tracking-wider text-cyan-300 mb-1">Statement</div>
            <p className="text-zinc-100 leading-relaxed">{result.statement}</p>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-cyan-300 mb-1">Mechanism</div>
            <p className="text-zinc-300 text-sm leading-relaxed">{result.mechanism}</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <Stat label="Universe" value={result.universe} mono />
            <Stat label="Horizon" value={`${result.horizon_days}d`} />
            <Stat label="Expected edge" value={`${result.expected_edge_bps.toFixed(0)} bps`} />
            <Stat label="Confidence" value={`${(result.confidence * 100).toFixed(0)}%`} />
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-cyan-300 mb-1">Falsification criterion</div>
            <p className="text-zinc-300 text-sm leading-relaxed">{result.falsification_criterion}</p>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-cyan-300 mb-2">Required data</div>
            <div className="space-y-2">
              {result.required_data.map((d, i) => (
                <div key={i} className="text-xs border-l-2 border-cyan-700/40 pl-3">
                  <div>
                    <span className="font-mono text-cyan-300">{d.catalog_kind}</span>{" "}
                    <span className="text-zinc-500">({d.granularity})</span>
                  </div>
                  <div className="text-zinc-400 mt-0.5">{d.rationale}</div>
                </div>
              ))}
            </div>
          </div>
          {meta && (
            <div className="text-xs text-zinc-500 border-t border-zinc-800/60 pt-3">
              <span className="font-mono">{meta.model}</span> · cost ${meta.cost.toFixed(4)} · decay ~{result.estimated_decay_days}d
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs text-zinc-500 uppercase tracking-wider">{label}</div>
      <div className={`text-sm mt-0.5 text-zinc-100 ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}
