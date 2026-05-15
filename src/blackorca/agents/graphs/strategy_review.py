"""Strategy code review graph.

Pulls strategy source via ``read_strategy_source`` and runs the code-review
agent. Returns a :class:`CodeReview` instance.
"""

from __future__ import annotations

from pathlib import Path

from blackorca.agents.client import AnthropicClient
from blackorca.agents.schemas import CodeReview
from blackorca.agents.tools import ReadSourceInput, tool_read_strategy_source
from blackorca.logging import get_logger

log = get_logger(__name__)


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def review_strategy(module: str, *, client: AnthropicClient | None = None) -> CodeReview:
    client = client or AnthropicClient()
    src = tool_read_strategy_source(ReadSourceInput(module=module)).source
    system = (PROMPTS_DIR / "code_review.md").read_text(encoding="utf-8")
    user = f"## Module\n`{module}`\n\n## Source\n```python\n{src}\n```"
    res = client.complete(system=system, prompt=user, schema=CodeReview)
    assert res.parsed is not None
    return res.parsed  # type: ignore[return-value]


__all__ = ["review_strategy"]
