"""Pydantic schemas for agent structured output.

Used to coerce LLM responses into typed Python objects. Each schema is paired
with a prompt in :mod:`blackorca.agents.prompts`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HypothesisRequiredData(BaseModel):
    catalog_kind: str = Field(description="bars_1d / twse_monthly_rev / etc.")
    granularity: str = Field(description="daily / monthly / event / ...")
    rationale: str


class Hypothesis(BaseModel):
    statement: str = Field(description="One-sentence falsifiable claim.")
    mechanism: str = Field(description="Why we believe this works.")
    universe: str = Field(description="Symbols or filter expression.")
    horizon_days: int = Field(ge=1, le=252)
    expected_edge_bps: float = Field(description="Expected daily edge in basis points.")
    falsification_criterion: str = Field(
        description="What pattern in the data would falsify this hypothesis?"
    )
    required_data: list[HypothesisRequiredData]
    estimated_decay_days: int = Field(
        default=180, description="How fast does the edge decay post-publication?"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class CodeReviewIssue(BaseModel):
    severity: Literal["critical", "major", "minor"]
    category: Literal["lookahead", "off_by_one", "risk", "state", "numerical", "style"]
    file: str | None = None
    line: int | None = None
    message: str
    suggested_fix: str | None = None


class CodeReview(BaseModel):
    verdict: Literal["approve", "iterate", "block"]
    issues: list[CodeReviewIssue]
    summary: str


class BacktestAnalysis(BaseModel):
    red_flags: list[str]
    green_flags: list[str]
    followup_tests: list[str]
    recommendation: Literal["promote", "iterate", "reject"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str


class FeatureDef(BaseModel):
    name: str
    formula: str
    lookback_days: int
    source: str


class SignalDefinition(BaseModel):
    name: str = Field(description="kebab-case slug")
    mechanism: str
    features: list[FeatureDef]
    entry_rule: str
    exit_rule: str
    holding_period_days: int = Field(ge=1)
    universe_filter: str
    required_data: list[str]


__all__ = [
    "BacktestAnalysis",
    "CodeReview",
    "CodeReviewIssue",
    "FeatureDef",
    "Hypothesis",
    "HypothesisRequiredData",
    "SignalDefinition",
]
