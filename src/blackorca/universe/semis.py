"""Semiconductor universe.

A ~25-ticker basket annotated with:

- ``tier``       — 1 (megacap catalysts), 2 (direct suppliers), 3 (deep tier)
- ``segment``    — logic / memory / equipment / IP / optical / SiC / photomask
- ``avg_adv``    — average daily dollar volume bucket (low / med / high)
- ``mcap_bucket`` — small / mid / large / mega

These metadata fields are used by the supply-chain-lag strategy and by
universe filters. Numbers are approximate and intended for screening, not
trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Tier(int, Enum):
    T1 = 1
    T2 = 2
    T3 = 3


Segment = Literal[
    "logic",
    "memory",
    "equipment",
    "ip_design",
    "optical",
    "sic",
    "photomask",
    "foundry",
    "fabless",
    "analog",
    "test_packaging",
]

AdvBucket = Literal["low", "mid", "high", "mega"]
McapBucket = Literal["small", "mid", "large", "mega"]


@dataclass(frozen=True, slots=True)
class SemiName:
    symbol: str
    name: str
    tier: Tier
    segment: Segment
    avg_adv: AdvBucket
    mcap_bucket: McapBucket
    country: str = "US"


SEMI_UNIVERSE: tuple[SemiName, ...] = (
    # ---- Tier 1: catalysts / megacaps ----
    SemiName("NVDA", "NVIDIA",                 Tier.T1, "fabless",        "mega", "mega"),
    SemiName("AMD",  "Advanced Micro Devices", Tier.T1, "fabless",        "high", "mega"),
    SemiName("TSM",  "Taiwan Semi",            Tier.T1, "foundry",        "high", "mega", "TW"),
    SemiName("AVGO", "Broadcom",               Tier.T1, "fabless",        "high", "mega"),
    SemiName("ASML", "ASML",                   Tier.T1, "equipment",      "high", "mega", "NL"),
    SemiName("INTC", "Intel",                  Tier.T1, "logic",          "high", "large"),
    SemiName("QCOM", "Qualcomm",               Tier.T1, "fabless",        "high", "large"),
    SemiName("MU",   "Micron",                 Tier.T1, "memory",         "high", "large"),
    SemiName("TXN",  "Texas Instruments",      Tier.T1, "analog",         "high", "large"),
    # ---- Tier 2: direct suppliers & equipment ----
    SemiName("AMAT", "Applied Materials",      Tier.T2, "equipment",      "high", "large"),
    SemiName("LRCX", "Lam Research",           Tier.T2, "equipment",      "high", "large"),
    SemiName("KLAC", "KLA",                    Tier.T2, "equipment",      "high", "large"),
    SemiName("MRVL", "Marvell",                Tier.T2, "fabless",        "mid",  "large"),
    SemiName("NXPI", "NXP",                    Tier.T2, "analog",         "mid",  "large"),
    SemiName("ON",   "ON Semi",                Tier.T2, "sic",            "mid",  "mid"),
    SemiName("ADI",  "Analog Devices",         Tier.T2, "analog",         "mid",  "large"),
    SemiName("STM",  "STMicroelectronics",     Tier.T2, "analog",         "mid",  "mid",  "IT"),
    SemiName("WOLF", "Wolfspeed",              Tier.T2, "sic",            "low",  "small"),
    # ---- Tier 3: deeper supply chain / niche ----
    SemiName("ARM",  "Arm Holdings",           Tier.T3, "ip_design",      "mid",  "large", "GB"),
    SemiName("MCHP", "Microchip",              Tier.T3, "analog",         "mid",  "mid"),
    SemiName("LSCC", "Lattice",                Tier.T3, "fabless",        "low",  "small"),
    SemiName("AEHR", "Aehr Test",              Tier.T3, "test_packaging", "low",  "small"),
    SemiName("UCTT", "Ultra Clean Holdings",   Tier.T3, "equipment",      "low",  "small"),
    SemiName("IVAC", "Intevac",                Tier.T3, "equipment",      "low",  "small"),
    SemiName("ENTG", "Entegris",               Tier.T3, "equipment",      "mid",  "mid"),
    SemiName("ACMR", "ACM Research",           Tier.T3, "equipment",      "low",  "small"),
)


def get_universe(
    *,
    tier: Tier | None = None,
    segment: Segment | None = None,
    min_adv: AdvBucket | None = None,
) -> list[SemiName]:
    """Filter the universe."""
    order = {"low": 0, "mid": 1, "high": 2, "mega": 3}
    out = list(SEMI_UNIVERSE)
    if tier is not None:
        out = [n for n in out if n.tier == tier]
    if segment is not None:
        out = [n for n in out if n.segment == segment]
    if min_adv is not None:
        threshold = order[min_adv]
        out = [n for n in out if order[n.avg_adv] >= threshold]
    return out


def symbols(*, tier: Tier | None = None, segment: Segment | None = None) -> list[str]:
    return [n.symbol for n in get_universe(tier=tier, segment=segment)]


__all__ = ["SEMI_UNIVERSE", "AdvBucket", "McapBucket", "Segment", "SemiName", "Tier", "get_universe", "symbols"]
