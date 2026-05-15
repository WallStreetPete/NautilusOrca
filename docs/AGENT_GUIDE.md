# Agent Guide

How to design new agent prompts and tools.

## Mental model

The agent layer is a small set of structured callers around the Anthropic API. Three building blocks:

1. **Prompt** — Markdown file in `src/blackorca/agents/prompts/`. Markdown is human-friendly, scannable, and version-controlled. The first lines are YAML frontmatter for metadata; the rest is the system prompt.
2. **Schema** — Pydantic model in `src/blackorca/agents/schemas.py`. Defines the structured response the model emits via Anthropic's tool-use mode.
3. **Tool** — Pydantic-typed callable in `src/blackorca/agents/tools.py` registered in `TOOLS`. Tools let the model take actions: query the catalog, run a backtest, look up a dependency edge.

## Adding a new prompt

```markdown
---
name: my_agent
role: <role>
model: claude-sonnet-4-6
description: <one line>
---

# Operating principles
1. ...
2. ...

# Output
Use the ``emit_result`` tool. Match the schema exactly.
```

Reference the matching Pydantic schema in your call:

```python
from blackorca.agents.client import AnthropicClient
from blackorca.agents.schemas import Hypothesis

client = AnthropicClient()
res = client.complete(system=open("…/my_agent.md").read(), prompt=user_msg, schema=Hypothesis)
result: Hypothesis = res.parsed
```

## Adding a new tool

In `agents/tools.py`:

```python
class MyToolInput(BaseModel):
    foo: str

class MyToolOutput(BaseModel):
    bar: int

def tool_my(arg: MyToolInput) -> MyToolOutput:
    return MyToolOutput(bar=len(arg.foo))

TOOLS["my_tool"] = (MyToolInput, MyToolOutput, tool_my)
```

If the agent uses tool-use, register the JSON schema with `Anthropic.tools=[...]`. For LangGraph-style local orchestration, wire `tool_my` into the graph node.

## Budget

Every `AnthropicClient` instance has a `TokenLedger`. Check `client.remaining_budget()` before the next call; call `client.assert_within_budget()` to raise. The session-level cap is `agents.max_research_budget_usd` in config.

## Memory

```python
from blackorca.agents.memory import make_memory_store, make_lesson

mem = make_memory_store()
mem.add(make_lesson(hypothesis="…", result_summary="sharpe 1.2"))
related = mem.search(query_embedding=[...], k=3)
```

By default this is `pgvector` when Postgres is reachable, in-memory otherwise. The agent code never branches on the backend.

## Cost notes

- Default model is `claude-opus-4-7` (~$15/$75 per million tokens in/out).
- Fast model is `claude-sonnet-4-6` (~$3/$15). Use for high-throughput classification (news, code review for tiny PRs).
- Structured-output (tool-use) costs the same per-token but compresses retries-on-malformed-JSON.
