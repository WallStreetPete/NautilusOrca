"""Pydantic-based configuration.

Resolution order (lowest -> highest precedence):
    1. ``config/base.yaml``
    2. ``config/<profile>.yaml`` (profile from BLACKORCA_PROFILE env var, default ``dev``)
    3. Environment variables prefixed with ``BLACKORCA_`` (double underscore = nested key)
    4. ``.env`` file in the working directory (loaded automatically)

The resulting :class:`Settings` object is fully validated at startup. Mis-typed
values fail loudly rather than at trading time. Use :func:`get_settings` to
obtain a process-wide singleton.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Profile = Literal["dev", "paper", "live"]

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


# ---------------------------------------------------------------------------
# Nested config models
# ---------------------------------------------------------------------------


class CatalogConfig(BaseModel):
    path: str = "data/catalog"
    default_calendar: str = "NYSE"
    default_timezone: str = "America/New_York"

    @property
    def is_s3(self) -> bool:
        return self.path.startswith("s3://")


class LoggingConfig(BaseModel):
    model_config = {"protected_namespaces": ()}
    level: str = "INFO"
    json_output: bool = Field(True, alias="json")

    @field_validator("level")
    @classmethod
    def _upper(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {v}")
        return v


class MetricsConfig(BaseModel):
    enabled: bool = True
    port: int = 9100


class RiskConfig(BaseModel):
    max_position_pct: float = Field(0.05, gt=0, le=1)
    max_gross_pct: float = Field(1.50, gt=0)
    max_net_pct: float = Field(1.00, ge=0)
    max_sector_pct: float = Field(0.30, gt=0, le=1)
    max_daily_loss_pct: float = Field(0.02, gt=0, le=1)
    max_drawdown_pct: float = Field(0.10, gt=0, le=1)
    per_order_max_notional: float = Field(250_000, gt=0)


class BacktestConfig(BaseModel):
    default_capital: float = 1_000_000.0
    slippage_bps: float = 2.0
    commission_per_share: float = 0.005
    min_commission: float = 1.00
    borrow_bps_annual: float = 50.0


class AgentsConfig(BaseModel):
    default_model: str = "claude-opus-4-7"
    fast_model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float = 0.2
    max_research_budget_usd: float = 5.00


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BLACKORCA_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    profile: Profile = "dev"

    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)

    # ---- secrets / external services (read from plain env, no prefix) ----
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    exa_api_key: SecretStr | None = Field(default=None, alias="EXA_API_KEY")
    firecrawl_api_key: SecretStr | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    alpha_vantage_api_key: SecretStr | None = Field(default=None, alias="ALPHA_VANTAGE_API_KEY")
    databento_api_key: SecretStr | None = Field(default=None, alias="DATABENTO_API_KEY")
    alpaca_api_key: SecretStr | None = Field(default=None, alias="ALPACA_API_KEY")
    alpaca_api_secret: SecretStr | None = Field(default=None, alias="ALPACA_API_SECRET")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets", alias="ALPACA_BASE_URL"
    )

    database_url: str = Field(
        default="postgresql://blackorca:blackorca@localhost:5432/blackorca",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # ---- repo paths ----
    repo_root: Path = Field(default=REPO_ROOT)

    @property
    def catalog_path(self) -> Path | str:
        """Return absolute path if local, raw URI if S3."""
        if self.catalog.is_s3:
            return self.catalog.path
        p = Path(self.catalog.path)
        return p if p.is_absolute() else (self.repo_root / p).resolve()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, Mapping):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must be a mapping at the top level")
    return data


def _load_yaml_layer(profile: str) -> dict[str, Any]:
    base = _read_yaml(CONFIG_DIR / "base.yaml")
    overlay = _read_yaml(CONFIG_DIR / f"{profile}.yaml")
    return _deep_merge(base, overlay)


def load_settings(profile: str | None = None, env_file: str | Path | None = ".env") -> Settings:
    """Build a fresh Settings instance.

    The optional ``env_file`` is loaded via python-dotenv before construction so
    pydantic-settings can pick it up. Use :func:`get_settings` instead in normal
    code paths — this function is mainly for tests.
    """
    if env_file is not None and Path(env_file).exists():
        load_dotenv(env_file, override=False)

    profile = profile or os.getenv("BLACKORCA_PROFILE", "dev")
    yaml_data = _load_yaml_layer(profile)
    yaml_data.setdefault("profile", profile)
    return Settings(**yaml_data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return load_settings()


def reset_settings_cache() -> None:
    """For tests: clear the singleton."""
    get_settings.cache_clear()


__all__ = [
    "AgentsConfig",
    "BacktestConfig",
    "CatalogConfig",
    "LoggingConfig",
    "MetricsConfig",
    "Profile",
    "RiskConfig",
    "Settings",
    "get_settings",
    "load_settings",
    "reset_settings_cache",
]
