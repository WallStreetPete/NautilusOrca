"""Supplier dependency graph.

Static, hand-curated mapping from tier-1 catalysts to the tier-2/3 names that
*should* move on the same news. Each edge has a rationale comment that
captures *why* we believe the linkage exists. When the linkage breaks
empirically, drop the edge — do not silently let it rot.

This is intentionally a tiny graph (not GraphML, not networkx). If we need
real graph algorithms later, lift this into a typed adjacency dict and wrap
with networkx without changing the shape of the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class SupplierEdge:
    upstream: str           # catalyst ticker (the one that moves first)
    downstream: str         # ticker expected to drift behind
    relationship: str       # short description
    expected_lag_days: int  # empirical-ish lag horizon
    confidence: float       # 0..1 — how strong we think the linkage is


# ---------------------------------------------------------------------------
# Curated edges. Add an edge only with a rationale.
# ---------------------------------------------------------------------------

DEPENDENCY_GRAPH: Final[tuple[SupplierEdge, ...]] = (
    # NVDA's earnings or product launch is the canonical AI-cycle catalyst.
    # CoWoS-style advanced packaging suppliers and HBM names drift behind.
    SupplierEdge("NVDA", "TSM",  "TSMC is NVDA's sole high-end foundry",                 3,  0.85),
    SupplierEdge("NVDA", "AMAT", "Advanced packaging tools — NVDA AI capex pull-through", 5,  0.55),
    SupplierEdge("NVDA", "LRCX", "Etch tools for HBM stacks",                            5,  0.55),
    SupplierEdge("NVDA", "ENTG", "Materials & purity in HBM / CoWoS",                    7,  0.45),
    SupplierEdge("NVDA", "MU",   "HBM3/HBM3e shipped into NVDA accelerators",            3,  0.60),
    SupplierEdge("NVDA", "AVGO", "AI networking ASICs adjacent to NVDA platforms",        5,  0.40),

    # TSM's monthly revenue print is THE leading number for advanced-node demand.
    # Photomask, etch, deposition, and metrology vendors drift behind by days.
    SupplierEdge("TSM",  "ASML", "Lithography — TSM is ASML's biggest customer",         5,  0.70),
    SupplierEdge("TSM",  "KLAC", "Process control / yield — ramps with TSM",             5,  0.55),
    SupplierEdge("TSM",  "AMAT", "Deposition / packaging tools",                         5,  0.50),
    SupplierEdge("TSM",  "ENTG", "Specialty materials & filtration",                     7,  0.40),
    SupplierEdge("TSM",  "ACMR", "Cleaning equipment — leveraged to TSM capex",           7,  0.35),

    # AMD/QCOM cycles often drag in fabless / analog suppliers.
    SupplierEdge("AMD",  "MRVL", "Both leveraged to AI datacenter capex",                3,  0.45),
    SupplierEdge("AMD",  "AVGO", "Co-shipped in datacenter / networking stacks",          5,  0.40),
    SupplierEdge("QCOM", "ARM",  "Royalty exposure to QCOM volumes",                     3,  0.50),

    # SiC / EV exposure cluster — share the same end-demand factor.
    SupplierEdge("ON",   "WOLF", "Both SiC EV plays; correlated on auto-cycle news",     2,  0.55),
    SupplierEdge("STM",  "WOLF", "STM signed long-term SiC supply with WOLF",            3,  0.40),

    # Equipment ripple within itself
    SupplierEdge("AMAT", "UCTT", "UCTT supplies subsystems to AMAT",                     7,  0.60),
    SupplierEdge("LRCX", "UCTT", "UCTT supplies subsystems to LRCX",                     7,  0.60),
    SupplierEdge("AMAT", "IVAC", "Niche capex pull-through",                             10, 0.30),
)


def downstream_of(symbol: str, *, min_confidence: float = 0.0) -> list[SupplierEdge]:
    """All edges where ``symbol`` is the catalyst."""
    return [e for e in DEPENDENCY_GRAPH if e.upstream == symbol and e.confidence >= min_confidence]


def upstream_of(symbol: str) -> list[SupplierEdge]:
    """All edges where ``symbol`` is the downstream."""
    return [e for e in DEPENDENCY_GRAPH if e.downstream == symbol]


__all__ = ["DEPENDENCY_GRAPH", "SupplierEdge", "downstream_of", "upstream_of"]
