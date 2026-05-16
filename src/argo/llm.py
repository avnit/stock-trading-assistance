from __future__ import annotations

from dataclasses import dataclass

import anthropic

SYSTEM_PROMPT = """You are a careful, skeptical equity research analyst writing a one-page thesis for a personal investor.

The investor will read your thesis and decide whether to act. You are NOT giving investment advice; you are summarizing evidence and naming risks so the investor can decide.

Rules:
- Be specific. Cite numbers from the financials and quotes from the 10-K when they materially support a claim.
- Lead with the bear case. If the bear case is weak, the bull case is stronger.
- Distinguish facts (from the 10-K / financials / price action) from your interpretation.
- Never invent figures. If a number is not in the inputs, say "not in inputs".
- If the evidence is mixed or thin, the recommendation should be HOLD or AVOID, not BUY.
- End with one line: `RECOMMENDATION: BUY | HOLD | AVOID` and `DIRECTION: bullish | bearish | neutral`.

Output format (Markdown):
# <TICKER> — Thesis (as of <today>)

## Snapshot
- one-line description of the business
- current price, 50/200 SMA position, 6-mo return

## Bull case (2–4 bullets)
## Bear case (2–4 bullets)
## What would change my mind
## Recommendation
RECOMMENDATION: ...
DIRECTION: ...
"""


@dataclass
class ThesisResult:
    markdown: str
    recommendation: str
    direction: str
    usage: dict[str, int]


def _parse_tail(markdown: str) -> tuple[str, str]:
    rec, direction = "HOLD", "neutral"
    for line in markdown.splitlines():
        upper = line.strip().upper()
        if upper.startswith("RECOMMENDATION:"):
            value = upper.split(":", 1)[1].strip().split()[0]
            if value in {"BUY", "HOLD", "AVOID"}:
                rec = value
        elif upper.startswith("DIRECTION:"):
            value = upper.split(":", 1)[1].strip().split()[0].lower()
            if value in {"bullish", "bearish", "neutral"}:
                direction = value
    return rec, direction


def generate_thesis(
    *,
    api_key: str,
    model: str,
    ticker: str,
    research_context: str,
    today_iso: str,
    client: anthropic.Anthropic | None = None,
) -> ThesisResult:
    """Generate the thesis. Caches the large research_context across runs on the same ticker."""
    client = client or anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=[
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": research_context,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Today is {today_iso}. Write the one-page thesis for {ticker} "
                            f"using only the inputs above. Follow the output format exactly."
                        ),
                    },
                ],
            }
        ],
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    rec, direction = _parse_tail(text)
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
    }
    return ThesisResult(markdown=text, recommendation=rec, direction=direction, usage=usage)
