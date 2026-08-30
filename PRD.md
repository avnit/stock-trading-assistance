# Stock Research & Trading Assistant — PRD (v0.1, for review)

**Status:** Draft for review
**Date:** 2026-05-16
**Author:** research compiled by Claude
**Audience:** product owner (you)

> Note: this PRD lives on the `claude/stock-trading-app-research-aIPdI` branch only.
> The Argonaut Claims repo is unrelated; this is a deliverable parked here for review,
> not code intended to merge to `main`.

---

## 1. TL;DR

Build a personal AI research-and-trading assistant for US equities and options.
The assistant ingests company filings, market data, and "smart-money" signals,
proposes trades (including options strategies), and — with explicit human approval —
places them through a brokerage. Long-term broker target is **Interactive Brokers**.

To get a quick win, **Phase 0 ships in ~1 week on Alpaca paper trading**, not IBKR.
Alpaca's API and Level-3 multi-leg options work without a desktop gateway and
let us prove the end-to-end research → propose → approve → execute loop before we
take on IBKR's heavier integration. IBKR comes online in Phase 2.

The plan leans heavily on existing OSS — almost every box on the wishlist already has
a working library or MCP server. The build effort is the **orchestration layer** and
the **thesis-to-strategy reasoning**, not the plumbing.

## 2. Vision & non-goals

**Vision.** A research analyst, options strategist, and execution assistant in one,
that I trust enough to let it click "buy" only after I review its plan.

**In scope (eventually):**
- Per-ticker deep research: business model, 10-K/10-Q sections, financials, news, technicals.
- Options strategy suggestions matched to a thesis (directional, volatility, income).
- Smart-money tracking: 13F holdings, Form 4 insiders, congressional trades, unusual options flow.
- Backtesting and paper-trading any proposed trade.
- IBKR live execution with hard guardrails (per-trade dollar caps, approval-required).

**Out of scope (forever, unless explicitly added later):**
- Fully autonomous trading (no human in the loop).
- High-frequency or intraday scalping strategies.
- Non-US markets, futures, FX, crypto (until US equities + options are solid).
- Selling this as a product to others (personal use, single-user).

**Non-goals up front:**
- Building anything from scratch we can fork. We are integrators in Phases 0–2.
- Pretty UI. CLI / Claude Code chat / a thin Streamlit panel is fine through Phase 2.

## 3. Reference architecture

```
                            ┌──────────────────────────────┐
                            │   LLM Agent Orchestrator     │
                            │   (LangGraph + Claude SDK)   │
                            │   - research graph           │
                            │   - strategy graph           │
                            │   - approval gate (interrupt)│
                            └───────────────┬──────────────┘
                                            │  MCP tools
   ┌────────────┬───────────────┬───────────┴───────────┬────────────────┐
   ▼            ▼               ▼                       ▼                ▼
[edgar MCP] [OpenBB SDK     [options chains:        [broker MCP]    [signals MCP]
 (10-K,      wrapped as     Tradier / yfinance /     P0: Alpaca      P3+: 13F,
 13F, F4)    custom MCP]    Polygon]                 P2+: IBKR       Form 4, UW
   │            │                │                        │                │
   ▼            ▼                ▼                        ▼                ▼
                       Local cache (SQLite + Parquet + filings text)
                       Vector store for 10-K sections (sqlite-vec or Chroma)
```

Key principles:
- **Tools are MCP servers behind a thin local registry**, so any model (Claude, GPT, Gemini) can drive them.
- **Broker is an interface** with two adapters (Alpaca first, IBKR second). Strategy code never imports the broker SDK directly.
- **Every state-changing action requires `interrupt()`** (LangGraph human-in-the-loop) and prints a typed trade ticket the human signs off on.

## 4. Build vs. reuse — landscape summary

Full source briefs are in §10. Headlines:

| Need | Best free OSS | Paid option (when ready) | Verdict |
|---|---|---|---|
| 10-K / 10-Q / 13F / Form 4 parsing | `dgunning/edgartools` (MIT, active, EdgarTools MCP included) | sec-api.io ($55/mo) | **Reuse edgartools.** Gold standard. |
| Fundamentals normalization & data backbone | `OpenBB-finance/OpenBB` (AGPL Platform, 100+ providers) | FMP $19, Polygon $29 | **Reuse OpenBB** as a normalization layer, wrap in our own MCP. |
| Equity quotes / charts / news | yfinance, OpenBB, `Alex2Yang97/yahoo-finance-mcp` | Polygon, FMP | Reuse free first. |
| Options chains + Greeks | Tradier sandbox (free) + `py_vollib_vectorized` | Polygon Options $29+ | Reuse. Compute Greeks locally for Yahoo data. |
| Options strategy modeling (PoP, payoff, breakevens) | `rgaveiga/optionlab` (GPL-3, very active) | — | **Reuse optionlab.** No mature alternative. |
| Options backtesting | `goldspanlabs/optopsy` (AGPL-3, active fork) | OptionNet Explorer (paid GUI) | Reuse for Phase 4. |
| Thesis → strategy mapping | **None mature** in OSS | OptionStrat / OptionsPlay (web only) | **Build in-house.** Rules + LLM. |
| Broker — quick MVP | `alpaca-py` + `laukikk/alpaca-mcp` | — | **Phase 0** uses Alpaca paper. |
| Broker — production target | `ib-api-reloaded/ib_async` v2.1.0 (Dec 2025) | — | **Phase 2.** Dockerized IB Gateway + `ib_async` paper, then live. |
| 13F (smart-money holdings) | edgartools | WhaleWisdom, sec-api.io | Reuse edgartools. |
| Form 4 (insider buys) | edgartools, openinsider scrape | sec-api.io | Reuse. |
| Congressional trades | `quiverquant` ($30/mo), `senate-stock-watcher-data` (free) | — | Free dataset for Phase 3. |
| Options flow (unusual activity) | — | **Unusual Whales API ($250/mo)** + official MCP | **Phase 4+ only.** Defer. |
| Sentiment | ApeWisdom (free), StockTwits trending | — | Phase 4. |
| Agent reference architecture | `virattt/ai-hedge-fund` (MIT, 57k★, LangGraph + 18 investor agents) | — | **Fork the skeleton.** Closest match to our scope. |
| Agent orchestration | LangGraph (interrupt + checkpoints) | — | Reuse. |
| LLM SDK | Claude Agent SDK (deep MCP support, `always_ask` permission) | — | Reuse. |

What this leaves us to build:
1. The **broker abstraction** with Alpaca + IBKR adapters.
2. The **thesis → options strategy** reasoning layer (rules + LLM, on top of optionlab).
3. The **research graph** that pulls together 10-K sections, fundamentals, recent news, and produces a one-page thesis.
4. The **approval ticket + audit log** that records every recommendation, decision, and fill.
5. **Guardrails**: per-trade $ caps, daily loss caps, position-size limits, blocked-symbol list.

## 5. Phased plan

The first phase is the quick win. Each phase is shippable on its own.

### Phase 0 — "Hello, Trade" (≈ 1 week)

**Goal:** prove the loop end-to-end on a single ticker with one strategy and Alpaca paper.

**Why Alpaca, not IBKR, for Phase 0:**
- No desktop gateway. Hosted REST API. Cloud-deployable.
- Free paper trading with Level-3 multi-leg options enabled by default since 2025.
- 1-day broker integration vs. 3–5 days for IBKR's Gateway + IBC + Docker dance.
- IBKR is still the production target (Phase 2) — Alpaca just gets us to first trade faster.

**Scope:**
- CLI tool: `research <TICKER>` → prints a one-page thesis using:
  - Latest 10-K Items 1, 1A, 7 via `edgartools`.
  - Last 4 quarters of financials from edgartools companyfacts.
  - Last 30 days of price + 50/200 SMA via yfinance.
  - LLM (Claude) synthesizes a buy / hold / avoid thesis with rationale.
- CLI tool: `propose <TICKER>` → returns **one** simple trade idea, either:
  - Buy 1 share, OR
  - A long single-leg call or put if the thesis is directional.
  - No multi-leg yet.
- CLI tool: `execute <TICKET_ID>` → confirmation prompt → places paper order via Alpaca.
- SQLite log of every (research, proposal, execution) tuple.
- Guardrail: max $500 notional per paper trade.

**Stack:**
- Python 3.11, `uv`, pyproject.
- `edgartools`, `yfinance`, `alpaca-py`.
- `anthropic` SDK (Claude Opus 4.7 for research, Haiku for routing).
- No MCP yet — direct library calls. Keep it simple.
- SQLite for state.

**Definition of done:**
- `uv run argo research AAPL` outputs a thesis in under 60s.
- `uv run argo propose AAPL` outputs a typed trade ticket.
- `uv run argo execute <id> --confirm` places a filled paper order on Alpaca and logs the fill.
- Unit tests on the broker adapter using Alpaca's sandbox.
- README with a 5-minute "run it yourself" path.

**Deliberately deferred from Phase 0:** options spreads, IBKR, MCP servers, vector store, web UI, 13F, options flow, backtesting.

### Phase 1 — Multi-leg options + better research (≈ 2 weeks)  ✅ shipped

**Goal:** propose and execute real options strategies (verticals, covered calls, cash-secured puts, iron condors) on Alpaca paper.

**Adds:**
- Option chain ingestion via Tradier sandbox (and yfinance fallback).
- Greeks + IV via `py_vollib_vectorized`.
- IV rank / percentile calculation from rolling 52-week IV history.
- `optionlab` integration for PoP, breakevens, P/L charts (rendered as PNG saved to disk).
- Strategy templates as YAML/Python:
  - Bullish + IV-rich → short put vertical.
  - Bullish + IV-cheap → long call or call vertical.
  - Neutral + IV-rich → iron condor.
  - Long stock + want income → covered call (30Δ, 30–45 DTE).
  - Want to own at lower price → cash-secured put.
- Strategy selector: LLM picks a template given (thesis, IV rank, account size, risk tolerance), then a deterministic Python builder fills in strikes/expiries.
- Vector store (`sqlite-vec` to keep it dependency-light) for embedded 10-K sections.

**Definition of done:**
- `propose AAPL --thesis bullish` returns a vertical with strikes, PoP, max loss, max gain.
- `execute <id>` places a multi-leg paper order on Alpaca Level 3.
- All proposals stored with the rationale and the inputs that produced them.

**Status (shipped):**
- `src/argo/options/` package: `chains.py` (yfinance + py_vollib_vectorized Greeks),
  `iv_rank.py` (realized-vol proxy until paid IV history is wired), `strategies.py`
  (7 templates: long call/put, bull call spread, short put vertical, iron condor,
  covered call, cash-secured put), `selector.py` (deterministic table on
  thesis × IV regime; LLM picker deferred), `analytics.py` (optionlab wrapper with
  closed-form fallback for verticals/condors).
- New CLI commands: `argo propose-options`, `argo strategies`, `argo expiries`.
- New HTTP endpoints: `POST /propose-options/{ticker}`, `GET /strategies`,
  `GET /expiries/{ticker}`.
- Alpaca `place_multi_leg_order` using `OrderClass.MLEG` + `OptionLegRequest`.
- DB extended with `strategy_template`, `legs_json`, `analysis_json` columns
  (additive ALTER on upgrade; no migration required for fresh installs).
- React frontend: new **Options** tab with full proposer (strategy override, DTE,
  delta, width, IV-rank override, qty, own-shares flag), plus multi-leg display
  + analysis metrics on `TicketDetailPage`.
- 35 new tests added; full suite 57/57 green.

**Deferred to a later phase:**
- LLM-driven strategy selector (rules table is sufficient for now).
- Tradier chain ingestion (yfinance + computed Greeks works).
- PNG payoff diagrams (numeric breakevens + PoP shown; can add later).
- `sqlite-vec` 10-K vector store (not blocking the options DoD; deferred to Phase 3).

### Phase 2 — IBKR adapter + go-live readiness (≈ 2 weeks)

**Goal:** swap the broker behind the same interface. Run on **IBKR paper** end to end.

**Adds:**
- Dockerized IB Gateway (`gnzsnz/ib-gateway-docker`) + IBC auto-login (paper, 2FA disabled — paper-only IBKR perk).
- `ib_async` v2.1.0 adapter implementing the same `BrokerClient` interface as Alpaca.
- Combo order placement via `BAG` secType + `ComboLeg` (verticals, condors).
- Per-trade hard caps configurable via `config/risk.yaml`.
- Daily P&L summary + circuit breaker (stop placing trades after configurable daily loss).
- Migrate broker MCP server (fork `code-rabi/interactive-brokers-mcp` or `YoungMoneyInvestments/ibkr-mcp` as the starting point).
- Audit log signed (HMAC) so we can prove which approvals fired which orders.

**Definition of done:**
- Same `propose` → `execute` flow works against IBKR paper.
- Killswitch tested (`argo halt` cancels all open orders, blocks new ones).
- A written go-live runbook covering: switching to live account, 2FA, IBKR Pro requirement, weekly reauth.

**Go-live decision is owner-controlled, not automatic.** Phase 2 only proves we *can* go live.

### Phase 3 — Smart-money signals (≈ 2 weeks)

**Goal:** add the "what are top traders doing" channel.

**Adds:**
- 13F ingestion via edgartools (quarterly cadence, store changes per filer).
- Form 4 ingestion via edgartools daily feed.
- Congressional trades via `senate-stock-watcher-data` (free) + optional Quiver Hobbyist ($30/mo).
- Per-ticker "smart-money panel" in the research output: who's accumulating, who's distributing, insider cluster buys, congressional activity.
- A "follow-the-money" screener: every Friday, list tickers where ≥N tracked filers added in the latest quarter.

**Deferred deliberately:** options flow (Unusual Whales). Wait until we know we'd use it, because $250/mo is real money.

### Phase 4 — Backtesting + signal weighting (≈ 3 weeks)

**Goal:** stop guessing whether the proposals are actually any good.

**Adds:**
- `optopsy` integration for historical option-strategy backtests.
- A vectorized equity backtester (just enough — vectorbt OSS or hand-rolled pandas).
- Walk-forward harness: for each historical proposal we *would* have made, what would have happened? Surface win-rate, average return, max drawdown per strategy template.
- Calibration: surface where the LLM thesis was wrong vs. where the strategy template was wrong, separately.
- Optional: Unusual Whales API tier ($250/mo) for options flow if backtests show it's worth it.

### Phase 5 — UI + automation (≈ open-ended)

**Goal:** stop living in the CLI.

**Adds:**
- Streamlit or Next.js panel: ticker search, thesis view, proposed ticket, approve button, position dashboard.
- Scheduled jobs: nightly research on a watchlist; pre-market summary email; post-close P&L summary.
- Mobile push (via ntfy.sh or similar) to approve tickets from a phone.

Anything beyond Phase 5 is open-ended (e.g., multi-account, additional asset classes, multiplayer).

## 6. Quick-win specifics — what we ship first

The fastest credible demo, in concrete terms:

```bash
$ argo research NVDA
# Pulls latest 10-K (FY2025), summarizes Item 1 (business),
# Item 1A (risk factors), Item 7 (MD&A) via Claude.
# Pulls last 8 quarters of revenue, gross margin, FCF from companyfacts.
# Pulls 6-month price + 50/200 SMA via yfinance.
# Prints a 1-page thesis to stdout and saves it to ~/.argo/research/NVDA-<date>.md

$ argo propose NVDA --thesis bullish --capital 500
# Generates ticket TKT-001:
#   Action: BUY 1 share NVDA @ market
#   Rationale: <2-paragraph LLM summary referencing the research>
#   Risk: max loss = current price (~$X), capital used $X
# Saves to SQLite, prints ticket.

$ argo tickets list
# TKT-001  NVDA  BUY 1 share  pending  created 14:02

$ argo execute TKT-001 --confirm
# Type: APPROVE NVDA TKT-001
# > APPROVE NVDA TKT-001
# Placing paper order via Alpaca... filled at $X. Ticket TKT-001 -> EXECUTED.
```

That's the whole Phase 0 surface. One ticker, one strategy template (long stock),
one broker (Alpaca paper), one approval path.

## 7. Risks & legal

- **Not investment advice.** Repo README must include the obligatory disclaimer. Personal use only; do not redistribute outputs as advice.
- **License hygiene.** Several upstream libraries (`optionlab`, `optopsy`, `FinancePy`, `OpenBB Platform`) are **GPL/AGPL**. We can use them locally for personal use but cannot ship a closed-source SaaS built on them. Keep that constraint in mind if scope ever changes.
- **SEC data redistribution.** Public domain content, but EDGAR requires User-Agent identification and ≤10 req/s. We will set both.
- **IBKR account types.** Lean's IBKR module and CPAPI require **IBKR Pro**, not Lite. Confirm your account type before Phase 2.
- **Paper-only at first.** All phases are paper-only by default. Live trading is a deliberate, one-line config flip in Phase 2, gated on the runbook checklist.
- **Killswitch.** Every phase ships with `argo halt`. Non-negotiable.
- **Model identity.** Don't reference internal model identifiers in any artifact we ship to a repo — chat-only.

## 8. Open questions for you

1. **Alpaca-first for Phase 0 — OK?** Or do you want IBKR from day one (adds ~4 days)?
2. **Capital scale.** What's the realistic max position size we'd ever want to size for? Drives the risk config defaults.
3. **Watchlist.** Hardcode a small list (e.g., 20 tickers) or universal? Affects how much pre-caching makes sense.
4. **Hosting.** Run locally on your machine, or on a small cloud VM from day one? (Affects how aggressive we should be about cloud-native choices like Alpaca/Web API OAuth.)
5. **Smart-money depth.** Is Phase 3 (13F + Form 4 + Congress, free) enough, or do you want Unusual Whales options flow earlier ($250/mo)?
6. **UI patience.** Can you live in the CLI through Phase 4, or do you want a minimal Streamlit panel earlier?

Answer those six and I'll cut Phase 0 into tickets.

## 9. Success criteria

- **Phase 0:** end-to-end research → proposal → human-approved paper execution on Alpaca, in under 60 seconds for the research step. One bug-free demo on AAPL, MSFT, NVDA.
- **Phase 2:** same flow on IBKR paper, with a written go-live runbook reviewed by you.
- **Phase 4:** backtest report that says, per strategy template, "this would have made / lost X over the last 5 years on these tickers" — and we use that report to prune or keep templates.

## 10. Source briefs (raw research, condensed)

The five research areas were investigated in parallel. Concise version of each:

### 10.1 IBKR integration

- **Wrappers:** `ib_async` v2.1.0 (Dec 2025) is the maintained successor to `ib_insync`
  (deprecated after Ewald de Wit's death in 2024). NautilusTrader added option-combo
  support Sept 2025. Lean's IBKR brokerage works but requires IBKR Pro.
- **Transport options:** TWS API (needs local Gateway), Client Portal API (needs CP
  Gateway), new **Web API OAuth 2.0** (cloud-friendly, no gateway, requires JWT public
  key registration). As of 2026-03-12 the Web API requires `sessionToken` on
  WebSocket connections.
- **Lowest-friction MVP path:** Dockerized IB Gateway (`gnzsnz/ib-gateway-docker` or
  `extrange/ibkr-docker`) + IBC auto-login + `ib_async`, talking to port 4002 paper.
- **MCP servers:** several community options (`code-rabi/interactive-brokers-mcp`,
  `YoungMoneyInvestments/ibkr-mcp`, `rcontesti/IB_MCP`, `ib-mcp` on PyPI). None are
  battle-tested — fork rather than depend. `ArjunDivecha/ibkr-mcp-server` was
  archived April 2026.
- **Options:** multi-leg spreads are supported via TWS API `secType="BAG"` + `ComboLeg`.

### 10.2 SEC EDGAR & 10-K data

- **Free path is excellent.** EDGAR `submissions.json`, `companyfacts.json`,
  `companyconcept` endpoints + full-text search are free; rate limit 10 req/s with a
  User-Agent containing name + email.
- **`dgunning/edgartools`** (MIT, very active, v5.31.2 May 2026) is best-in-class: typed
  10-K Item 1/1A/7 parsing, XBRL → DataFrame, also ships an MCP server with 13 tools.
- **Other options:** `sec-edgar-downloader` (raw filings only), `stefanoamorelli/sec-edgar-toolkit`
  (active, sections), `finagg` (aggregates EDGAR + FRED + Yahoo into SQLite).
- **Paid:** sec-api.io ($55/mo entry) is the best paid alternative; FMP ($19/mo) is
  cheapest for normalized fundamentals.
- **Storage footprint for S&P 500 × 10 yrs:** ~5–15 GB primary HTML, ~1–2.5 GB cleaned
  section text, bulk pull takes 10–20 hours at 8 req/s.

### 10.3 Smart-money signals

- **13F (institutional holdings):** edgartools is free and best. WhaleWisdom and
  sec-api.io are paid alternatives. Dataroma is a free curated "superinvestor" subset
  (scrape only).
- **Form 4 (insider buys):** edgartools or openinsider.com (free, scrape).
- **Congressional trades:** `quiverquant` ($30/mo Hobbyist, $75 Trader),
  `senate-stock-watcher-data` (free pre-parsed JSON, weekly refresh).
- **Options flow:** Unusual Whales API ($250/mo) is the price/coverage leader; has
  official hosted MCP. Cheddar Flow and FlowAlgo have no public API.
- **Sentiment:** ApeWisdom (free REST), SwaggyStocks (free), StockTwits trending (gated
  developer API). Twitter/X effectively unusable for cheap.
- **MCPs:** EdgarTools MCP (recommended), Unusual Whales official MCP, several
  community SEC MCP variants.

### 10.4 Options strategies

- **Data:** Tradier sandbox is the cleanest free option-chain + Greeks source. Polygon
  $29+ for production. yfinance has chains but no Greeks (compute locally).
- **Pricing/Greeks:** `py_vollib_vectorized` (semi-stale but fast and works),
  `QuantLib-SWIG` (heavyweight), `FinancePy` (active, numba). mibian and `backtrader`
  are stale.
- **Strategy modeling:** `rgaveiga/optionlab` (GPL-3, very active) is the recommended
  primary tool — PoP, P/L profile, Greeks per leg, breakevens.
- **Backtesting:** `goldspanlabs/optopsy` (AGPL-3, active fork; original is dormant).
- **No mature OSS "thesis → strategy" library.** This is what we build.
- **Visualization:** prefer `optionlab` over `opstrat` (stale).
- **MCPs:** several Tradier and IBKR options MCPs exist (`walkerhughes/tastytrade-mcp`,
  `fiorelorenzo/ibkr-mcp`, `blake365/options-chain`), all early-stage.

### 10.5 LLM agent landscape & reference apps

- **Closest prior art:** `virattt/ai-hedge-fund` (MIT, 57k★) — LangGraph-based
  multi-agent system with 18 "famous-investor" agents, FastAPI + React, backtester.
  Educational, no live execution. **Worth forking as a skeleton.**
- **Also relevant:** `AI4Finance-Foundation/FinRobot` (Apache, multi-agent analysis),
  `TauricResearch/TradingAgents` (Apache, risk-management agent patterns, v0.2.5 in
  2026).
- **OpenBB Platform** (AGPL): 100+ data provider integrations, Python-first SDK.
  Recommended as our data normalization layer wrapped behind our own MCP.
- **Brokers:** Alpaca has Level-3 multi-leg options live since 2025, paper-trading
  is the easiest possible MVP path. IBKR remains the production target.
- **Agent orchestration:** LangGraph's `interrupt()` + checkpoints fits the
  research→propose→approve→execute flow best. Claude Agent SDK adds deep MCP support
  and `always_ask` permissions on tools. CrewAI is weak on HITL — skip.

## 11. Decision log (for review)

These are the decisions baked into this PRD. Tell me which to flip.

1. **Quick-win broker = Alpaca paper, not IBKR.** Saves ~4 days. IBKR comes in Phase 2.
2. **Agent framework = LangGraph + Claude Agent SDK.** LangGraph's HITL is the killer feature; Claude SDK's MCP support is the deepest.
3. **Data backbone = `edgartools` + OpenBB + Tradier sandbox.** All free for what we need.
4. **Options strategy modeling = `optionlab`.** Build the thesis-to-template layer on top.
5. **No options flow until Phase 4 at earliest.** $250/mo Unusual Whales waits until we can prove it pays for itself.
6. **No UI until Phase 5.** CLI and Markdown reports through Phases 0–4.
7. **License posture: personal use only.** GPL/AGPL dependencies make commercial productization a separate conversation.
