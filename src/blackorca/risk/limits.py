"""Risk limit configuration.

Mirrors :class:`blackorca.config.RiskConfig` but adds per-strategy and
per-sector overrides. Used by :class:`PreTradeRiskCheck`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blackorca.config import RiskConfig


@dataclass(slots=True)
class RiskLimits:
    max_position_pct: float = 0.05
    max_gross_pct: float = 1.50
    max_net_pct: float = 1.00
    max_sector_pct: float = 0.30
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    per_order_max_notional: float = 250_000.0
    # Optional per-sector overrides
    sector_caps: dict[str, float] = field(default_factory=dict)
    # Optional per-symbol absolute share caps (e.g. illiquidity)
    symbol_share_caps: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: RiskConfig) -> RiskLimits:
        return cls(
            max_position_pct=cfg.max_position_pct,
            max_gross_pct=cfg.max_gross_pct,
            max_net_pct=cfg.max_net_pct,
            max_sector_pct=cfg.max_sector_pct,
            max_daily_loss_pct=cfg.max_daily_loss_pct,
            max_drawdown_pct=cfg.max_drawdown_pct,
            per_order_max_notional=cfg.per_order_max_notional,
        )


__all__ = ["RiskLimits"]
