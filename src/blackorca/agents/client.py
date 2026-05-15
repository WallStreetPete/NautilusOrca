"""Anthropic API client wrapper.

- Retries with exponential backoff on transient errors.
- Token + cost accounting (Prometheus + per-call return).
- Structured output via Pydantic schema (uses tool-use mode to coerce JSON).
- Configurable model: defaults to ``claude-opus-4-7``, with a ``fast`` flag
  that flips to ``claude-sonnet-4-6``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from anthropic import Anthropic, APIStatusError
from pydantic import BaseModel

from blackorca.config import get_settings
from blackorca.logging import get_logger
from blackorca.metrics import AGENT_COST_USD, AGENT_LATENCY, AGENT_TOKENS

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


# Approximate pricing per million tokens (USD). Update when Anthropic changes
# pricing; these are the only place that should know.
PRICING_PER_M_TOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-7":    (15.0, 75.0),    # (input, output)
    "claude-opus-4-7[1m]": (15.0, 75.0),
    "claude-sonnet-4-6":  (3.0,  15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


@dataclass(slots=True)
class CompletionResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    raw: Any = None
    parsed: BaseModel | None = None


@dataclass(slots=True)
class TokenLedger:
    """Cumulative cost tracker for budget enforcement."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        self.cost_usd += cost
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        m = self.by_model.setdefault(model, {"in": 0, "out": 0, "cost": 0.0})
        m["in"] += input_tokens
        m["out"] += output_tokens
        m["cost"] += cost


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING_PER_M_TOK.get(model, (5.0, 25.0))
    return (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        settings = get_settings()
        key = api_key or (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = Anthropic(api_key=key)
        self.default_model = default_model or settings.agents.default_model
        self.fast_model = settings.agents.fast_model
        self.max_tokens = max_tokens or settings.agents.max_tokens
        self.temperature = temperature if temperature is not None else settings.agents.temperature
        self.ledger = TokenLedger()

    # ------------------------------------------------------------------
    # primary entry
    # ------------------------------------------------------------------

    def complete(
        self,
        *,
        system: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        fast: bool = False,
        schema: type[T] | None = None,
        max_retries: int = 3,
    ) -> CompletionResult:
        """Call the Anthropic API.

        Either provide ``messages`` (list-of-dict) or a single ``prompt`` string.
        If ``schema`` is given, the model is asked to emit structured JSON
        matching the Pydantic schema, and the parsed instance is returned in
        :attr:`CompletionResult.parsed`.
        """
        msgs = messages or [{"role": "user", "content": prompt or ""}]
        chosen_model = model or (self.fast_model if fast else self.default_model)

        # Structured output: use tool-use to force JSON
        tools = None
        if schema is not None:
            tool_schema = schema.model_json_schema()
            tools = [
                {
                    "name": "emit_result",
                    "description": (
                        f"Emit a {schema.__name__} object matching the provided schema."
                    ),
                    "input_schema": tool_schema,
                }
            ]

        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": msgs,
        }
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "tool", "name": "emit_result"}

        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            try:
                resp = self._client.messages.create(**kwargs)
                AGENT_LATENCY.labels(model=chosen_model).observe(time.perf_counter() - t0)
                break
            except APIStatusError as e:
                last_err = e
                if e.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    log.warning("agent.retry", status=e.status_code, attempt=attempt)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        else:
            raise RuntimeError(f"all retries exhausted: {last_err}")

        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = estimate_cost(chosen_model, in_tok, out_tok)
        AGENT_TOKENS.labels(model=chosen_model, kind="input").inc(in_tok)
        AGENT_TOKENS.labels(model=chosen_model, kind="output").inc(out_tok)
        AGENT_COST_USD.labels(model=chosen_model).inc(cost)
        self.ledger.add(chosen_model, in_tok, out_tok, cost)

        # Extract text or tool input
        text_parts: list[str] = []
        parsed: BaseModel | None = None
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use" and block.name == "emit_result" and schema is not None:
                try:
                    parsed = schema.model_validate(block.input)
                    text_parts.append(json.dumps(block.input))
                except Exception as e:
                    log.warning("agent.schema_validation_failed", error=str(e))

        return CompletionResult(
            text="\n".join(text_parts),
            model=chosen_model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            raw=resp,
            parsed=parsed,
        )

    # ------------------------------------------------------------------
    # budget gating
    # ------------------------------------------------------------------

    def remaining_budget(self) -> float:
        settings = get_settings()
        return max(settings.agents.max_research_budget_usd - self.ledger.cost_usd, 0.0)

    def assert_within_budget(self) -> None:
        if self.remaining_budget() <= 0:
            raise BudgetExceededError(
                f"research budget exhausted (spent ${self.ledger.cost_usd:.2f})"
            )


class BudgetExceededError(RuntimeError):
    pass


__all__ = [
    "AnthropicClient",
    "BudgetExceededError",
    "CompletionResult",
    "TokenLedger",
    "estimate_cost",
]
