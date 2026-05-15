"use client";

import { useMemo, useState } from "react";
import { DEPENDENCY_GRAPH, SEMI_UNIVERSE, type SemiName, type Tier } from "@/lib/universe";

const TIER_COLOR: Record<Tier, string> = {
  1: "#f97316",
  2: "#7dd3fc",
  3: "#a3a3a3",
};

function tierBadge(t: Tier) {
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full mr-1.5"
      style={{ backgroundColor: TIER_COLOR[t] }}
    />
  );
}

type Pos = { x: number; y: number };

function springLayout(nodes: string[], edges: { a: string; b: string }[]): Record<string, Pos> {
  // Deterministic, lightweight spring layout. We don't need d3 for ~25 nodes.
  const n = nodes.length;
  const positions: Record<string, Pos> = {};
  // initial: evenly on a circle
  nodes.forEach((node, i) => {
    const angle = (i / n) * Math.PI * 2;
    positions[node] = { x: Math.cos(angle), y: Math.sin(angle) };
  });
  const adjacency: Record<string, Set<string>> = {};
  nodes.forEach((n2) => (adjacency[n2] = new Set()));
  edges.forEach((e) => {
    adjacency[e.a]?.add(e.b);
    adjacency[e.b]?.add(e.a);
  });
  // Fruchterman-Reingold-ish
  const area = 1;
  const k = Math.sqrt(area / Math.max(n, 1));
  let t = 0.1;
  for (let iter = 0; iter < 200; iter++) {
    const disp: Record<string, Pos> = {};
    nodes.forEach((v) => (disp[v] = { x: 0, y: 0 }));
    for (const v of nodes) {
      for (const u of nodes) {
        if (u === v) continue;
        const dx = positions[v].x - positions[u].x;
        const dy = positions[v].y - positions[u].y;
        const dist = Math.max(Math.hypot(dx, dy), 0.01);
        const force = (k * k) / dist;
        disp[v].x += (dx / dist) * force;
        disp[v].y += (dy / dist) * force;
      }
    }
    for (const v of nodes) {
      for (const u of adjacency[v] ?? []) {
        const dx = positions[v].x - positions[u].x;
        const dy = positions[v].y - positions[u].y;
        const dist = Math.max(Math.hypot(dx, dy), 0.01);
        const force = (dist * dist) / k;
        disp[v].x -= (dx / dist) * force;
        disp[v].y -= (dy / dist) * force;
      }
    }
    for (const v of nodes) {
      const d = disp[v];
      const dlen = Math.max(Math.hypot(d.x, d.y), 0.001);
      positions[v].x += (d.x / dlen) * Math.min(dlen, t);
      positions[v].y += (d.y / dlen) * Math.min(dlen, t);
    }
    t *= 0.97;
  }
  // normalize
  const xs = nodes.map((n2) => positions[n2].x);
  const ys = nodes.map((n2) => positions[n2].y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  for (const v of nodes) {
    positions[v].x = (positions[v].x - minX) / (maxX - minX || 1);
    positions[v].y = (positions[v].y - minY) / (maxY - minY || 1);
  }
  return positions;
}

export default function UniversePage() {
  const [minConfidence, setMinConfidence] = useState(0.4);
  const [filter, setFilter] = useState<"all" | 1 | 2 | 3>("all");
  const [selected, setSelected] = useState<string | null>(null);

  const filteredUniverse = useMemo(() => {
    if (filter === "all") return SEMI_UNIVERSE;
    return SEMI_UNIVERSE.filter((s) => s.tier === filter);
  }, [filter]);

  const visibleEdges = useMemo(
    () => DEPENDENCY_GRAPH.filter((e) => e.confidence >= minConfidence),
    [minConfidence]
  );

  const layout = useMemo(() => {
    const nodes = Array.from(new Set(visibleEdges.flatMap((e) => [e.upstream, e.downstream])));
    return { nodes, positions: springLayout(nodes, visibleEdges.map((e) => ({ a: e.upstream, b: e.downstream }))) };
  }, [visibleEdges]);

  const nodeTier = (sym: string): Tier => (SEMI_UNIVERSE.find((s) => s.symbol === sym)?.tier ?? 3) as Tier;

  return (
    <div className="mx-auto max-w-7xl px-6 py-12">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold mb-2">Universe & Dependency Graph</h1>
        <p className="text-zinc-400 text-sm max-w-3xl">
          The Black Orca semi basket — 26 names across tier-1 (megacap catalysts), tier-2
          (direct suppliers), and tier-3 (deeper supply chain). The dependency graph is
          hand-curated, with a confidence + expected-lag annotation per edge, used by the
          tier-1 → tier-2 drift strategy.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* graph */}
        <div className="lg:col-span-2 rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-4">
          <div className="flex items-center justify-between mb-3 gap-4 flex-wrap">
            <h2 className="font-semibold">Supplier dependency graph</h2>
            <div className="flex items-center gap-3 text-xs">
              <label className="flex items-center gap-2">
                min conf
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={minConfidence}
                  onChange={(e) => setMinConfidence(Number(e.target.value))}
                  className="w-28"
                />
                <span className="font-mono text-cyan-300">{minConfidence.toFixed(2)}</span>
              </label>
            </div>
          </div>
          <Graph layout={layout} edges={visibleEdges} nodeTier={nodeTier} selected={selected} onSelect={setSelected} />
          <div className="mt-3 flex gap-4 text-xs text-zinc-400">
            <span><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: TIER_COLOR[1] }} />Tier 1</span>
            <span><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: TIER_COLOR[2] }} />Tier 2</span>
            <span><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: TIER_COLOR[3] }} />Tier 3</span>
            <span className="ml-auto">{visibleEdges.length} edges shown</span>
          </div>
        </div>

        {/* universe table */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Names</h2>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value === "all" ? "all" : (Number(e.target.value) as Tier))}
              className="text-xs bg-zinc-800/60 border border-zinc-700/60 rounded px-2 py-1"
            >
              <option value="all">All</option>
              <option value={1}>Tier 1</option>
              <option value={2}>Tier 2</option>
              <option value={3}>Tier 3</option>
            </select>
          </div>
          <div className="max-h-[460px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-zinc-500 sticky top-0 bg-[#0a0d14]">
                <tr>
                  <th className="text-left font-medium py-1">Symbol</th>
                  <th className="text-left font-medium py-1">Segment</th>
                  <th className="text-left font-medium py-1">Country</th>
                </tr>
              </thead>
              <tbody>
                {filteredUniverse.map((s: SemiName) => (
                  <tr
                    key={s.symbol}
                    onClick={() => setSelected(s.symbol)}
                    className={`cursor-pointer border-t border-zinc-800/40 ${
                      selected === s.symbol ? "bg-cyan-900/20" : "hover:bg-zinc-800/30"
                    }`}
                  >
                    <td className="py-1.5 font-mono">{tierBadge(s.tier)}{s.symbol}</td>
                    <td className="py-1.5 text-zinc-400">{s.segment}</td>
                    <td className="py-1.5 text-zinc-500">{s.country}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* selected detail */}
      {selected && <SelectedDetail symbol={selected} />}
    </div>
  );
}

function Graph({
  layout,
  edges,
  nodeTier,
  selected,
  onSelect,
}: {
  layout: { nodes: string[]; positions: Record<string, Pos> };
  edges: readonly { upstream: string; downstream: string; confidence: number; expected_lag_days: number }[];
  nodeTier: (sym: string) => Tier;
  selected: string | null;
  onSelect: (s: string) => void;
}) {
  const W = 700, H = 460, pad = 30;
  const sx = (x: number) => pad + x * (W - 2 * pad);
  const sy = (y: number) => pad + y * (H - 2 * pad);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="rgba(125,211,252,0.5)" />
        </marker>
      </defs>
      {edges.map((e, i) => {
        const a = layout.positions[e.upstream];
        const b = layout.positions[e.downstream];
        if (!a || !b) return null;
        const isHighlight = selected && (selected === e.upstream || selected === e.downstream);
        return (
          <line
            key={i}
            x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)}
            stroke={isHighlight ? "#7dd3fc" : "rgba(125,211,252,0.25)"}
            strokeWidth={1 + 3 * e.confidence}
            markerEnd="url(#arrow)"
          />
        );
      })}
      {layout.nodes.map((node) => {
        const p = layout.positions[node];
        const t = nodeTier(node);
        const isSel = selected === node;
        return (
          <g key={node} transform={`translate(${sx(p.x)},${sy(p.y)})`} onClick={() => onSelect(node)} className="cursor-pointer">
            <circle r={isSel ? 16 : 12} fill={TIER_COLOR[t]} stroke={isSel ? "#fff" : "#000"} strokeWidth={isSel ? 2 : 1} />
            <text textAnchor="middle" y={-18} fontSize={11} fill="#e6edf3" fontFamily="monospace">{node}</text>
          </g>
        );
      })}
    </svg>
  );
}

function SelectedDetail({ symbol }: { symbol: string }) {
  const node = SEMI_UNIVERSE.find((s) => s.symbol === symbol);
  const downstream = DEPENDENCY_GRAPH.filter((e) => e.upstream === symbol);
  const upstream = DEPENDENCY_GRAPH.filter((e) => e.downstream === symbol);
  return (
    <div className="mt-6 rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-5">
      <div className="flex items-center gap-3 mb-2">
        <h2 className="text-xl font-semibold font-mono">{symbol}</h2>
        {node && (
          <span className="text-xs text-zinc-400">
            {node.name} · tier {node.tier} · {node.segment}
          </span>
        )}
      </div>
      <div className="grid md:grid-cols-2 gap-4 mt-3 text-sm">
        <div>
          <div className="text-zinc-400 text-xs uppercase mb-1">Downstream of {symbol}</div>
          {downstream.length === 0 ? (
            <div className="text-zinc-500 text-xs">None.</div>
          ) : downstream.map((e) => (
            <div key={e.downstream} className="py-1 border-t border-zinc-800/40">
              <span className="font-mono">{e.downstream}</span>{" "}
              <span className="text-cyan-300 text-xs">conf {e.confidence.toFixed(2)} · lag {e.expected_lag_days}d</span>
              <div className="text-xs text-zinc-400">{e.relationship}</div>
            </div>
          ))}
        </div>
        <div>
          <div className="text-zinc-400 text-xs uppercase mb-1">Catalysts for {symbol}</div>
          {upstream.length === 0 ? (
            <div className="text-zinc-500 text-xs">None.</div>
          ) : upstream.map((e) => (
            <div key={e.upstream} className="py-1 border-t border-zinc-800/40">
              <span className="font-mono">{e.upstream}</span>{" "}
              <span className="text-cyan-300 text-xs">conf {e.confidence.toFixed(2)} · lag {e.expected_lag_days}d</span>
              <div className="text-xs text-zinc-400">{e.relationship}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
