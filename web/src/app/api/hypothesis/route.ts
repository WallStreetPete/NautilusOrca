import { anthropic } from "@ai-sdk/anthropic";
import { generateText, Output } from "ai";
import { NextResponse } from "next/server";
import { z } from "zod";

export const runtime = "nodejs";
export const maxDuration = 60;

const HypothesisSchema = z.object({
  statement: z.string().describe("One-sentence falsifiable claim."),
  mechanism: z.string().describe("Why we believe this works."),
  universe: z.string().describe("Symbols or filter expression."),
  horizon_days: z.number().int().min(1).max(252),
  expected_edge_bps: z.number().describe("Expected daily edge in basis points."),
  falsification_criterion: z
    .string()
    .describe("What pattern in the data would falsify this hypothesis?"),
  required_data: z
    .array(
      z.object({
        catalog_kind: z.string(),
        granularity: z.string(),
        rationale: z.string(),
      })
    )
    .min(1),
  estimated_decay_days: z.number().int().default(180),
  confidence: z.number().min(0).max(1),
});

const SYSTEM_PROMPT = `You are a senior quantitative research analyst at Black Orca Capital, an AI-native hedge fund. Your job is to generate falsifiable, testable trading hypotheses about a specific universe of securities.

## Operating principles

1. A hypothesis is not a directional view. It is a mechanism + empirically testable prediction + required data + expected edge.
2. Bias toward second-order effects (supplier drift, customer concentration, regulatory pass-through) over first-order momentum/value plays that are already priced.
3. Be honest about what would falsify the hypothesis. If it can't be falsified, it's not a hypothesis — it's marketing.
4. Prefer hypotheses where the data exists and the holding period is well-defined.
5. Estimate alpha decay: how fast does this edge die after publication?

## Output

Match the schema exactly. Be specific about data sources and the test design.

## Examples of good hypotheses

- "TSMC monthly revenue YoY > 15% predicts +30bps daily abnormal return on KLAC/AMAT over the 3 days following the print, conditional on prior 90-day correlation."
- "NVDA after-hours gap > 5% on earnings predicts +20bps abnormal return on Marvell over the next 5 trading days."

## Examples of bad hypotheses

- "Buy NVDA when it's oversold" (not falsifiable; no mechanism)
- "Sentiment predicts returns" (too vague; what sentiment, what horizon, what universe?)`;

export async function POST(req: Request) {
  try {
    if (!process.env.ANTHROPIC_API_KEY) {
      return NextResponse.json(
        { error: "ANTHROPIC_API_KEY not configured on the server" },
        { status: 500 }
      );
    }
    const { context, fast } = (await req.json()) as { context?: string; fast?: boolean };
    if (!context || context.trim().length < 20) {
      return NextResponse.json({ error: "context too short" }, { status: 400 });
    }

    const modelId = fast ? "claude-sonnet-4-6" : "claude-opus-4-7";

    const result = await generateText({
      model: anthropic(modelId),
      system: SYSTEM_PROMPT,
      prompt: context,
      output: Output.object({ schema: HypothesisSchema }),
      temperature: 0.3,
      maxOutputTokens: 2500,
    });

    // Cost estimate (USD per million tokens — keep in sync with Python ledger).
    const rates: Record<string, [number, number]> = {
      "claude-opus-4-7": [15, 75],
      "claude-sonnet-4-6": [3, 15],
    };
    const [inRate, outRate] = rates[modelId] ?? [5, 25];
    const usage = result.usage;
    const inTok = usage?.inputTokens ?? 0;
    const outTok = usage?.outputTokens ?? 0;
    const costUsd = (inTok * inRate + outTok * outRate) / 1_000_000;

    return NextResponse.json({
      model: modelId,
      hypothesis: result.output,
      tokens: { input: inTok, output: outTok },
      cost_usd: costUsd,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
