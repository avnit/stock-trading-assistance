# argo — Stock Research & Trading Assistant (Phase 0)

Phase 0 of the stock research and trading assistant described in [`PRD.md`](PRD.md).

> **Not investment advice.** Personal-use research tool. Paper trading only by default.
> Read the PRD before changing anything.

## What Phase 0 does

A CLI that, for one US-listed ticker, runs the full loop:

1. `argo research <TICKER>` — pulls the latest 10-K sections (Item 1, 1A, 7) via
   `edgartools`, the last 8 quarters of fundamentals via SEC companyfacts,
   and 6 months of price + 50/200 SMA via yfinance. Claude Opus 4.7 synthesises
   a one-page thesis.
2. `argo propose <TICKER> --thesis bullish|bearish|neutral` — produces a single
   trade ticket (long stock; future phases add options).
3. `argo execute <TICKET_ID> --confirm` — places the paper order via Alpaca after
   a typed-confirmation prompt.

Everything is logged to a local SQLite DB.

## Quick start

```bash
# Install (uv is recommended; pip works too)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Configure
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, and SEC_USER_AGENT.
# Get free Alpaca paper-trading keys at https://alpaca.markets/.

# Run
argo research NVDA
argo propose NVDA --thesis bullish --capital 500
argo tickets list
argo execute TKT-001 --confirm
argo positions
```

## Configuration

Settings come from environment variables (loaded from `.env` if present):

| Var | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Used for the thesis LLM call. |
| `ALPACA_API_KEY` | — | Required. Alpaca paper-trading key. |
| `ALPACA_SECRET_KEY` | — | Required. Alpaca paper-trading secret. |
| `ALPACA_PAPER` | `true` | If `false`, hits the live trading endpoint. **Do not flip until Phase 2.** |
| `SEC_USER_AGENT` | — | Required by SEC EDGAR — `Name email@example.com`. |
| `ARGO_MAX_NOTIONAL_USD` | `500` | Hard cap on a single trade's notional value. |
| `ARGO_DATA_DIR` | `~/.argo` | Where the SQLite DB and saved research live. |

## Guardrails

- **Paper trading only by default** (`ALPACA_PAPER=true`).
- **$500 notional cap per trade** (`ARGO_MAX_NOTIONAL_USD`).
- **Typed-confirmation execute** — must type `APPROVE <TICKER> <TICKET_ID>` exactly.
- **`argo halt`** — cancels every open order and marks all pending tickets blocked.

## Tests

```bash
pytest
```

Tests use mocks for Alpaca, edgartools, and Anthropic — no live API calls.

## What's deliberately not in Phase 0

- Multi-leg options strategies → Phase 1
- IBKR adapter → Phase 2
- Smart-money signals (13F, insider, Congress) → Phase 3
- Backtesting → Phase 4
- Web UI → Phase 5

See [`PRD.md`](PRD.md) for the full plan.
