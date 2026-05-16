from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from argo import __version__
from argo.brokers import AlpacaBroker
from argo.config import get_settings
from argo.db import DB
from argo.execute import GuardrailError, build_execution_plan, execute_ticket
from argo.llm import generate_thesis
from argo.propose import ProposalError, propose_trade
from argo.research import build_snapshot, today_iso

app = FastAPI(title="argo", version=__version__)


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


def _broker() -> AlpacaBroker:
    s = get_settings()
    return AlpacaBroker(api_key=s.alpaca_api_key, secret_key=s.alpaca_secret_key, paper=s.alpaca_paper)


def _db() -> DB:
    return DB(get_settings().db_path)


class ProposeBody(BaseModel):
    thesis_direction: str | None = Field(
        default=None, description="bullish | bearish | neutral; defaults to latest stored research"
    )
    capital_usd: float = Field(..., gt=0)


class ExecuteBody(BaseModel):
    confirmation: str = Field(..., description="Must equal exactly: APPROVE <TICKER> <TICKET_ID>")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/config")
def show_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "model": s.anthropic_model,
        "alpaca_paper": s.alpaca_paper,
        "max_notional_usd": s.max_notional_usd,
        "data_dir": str(s.data_dir),
        "anthropic_key_set": bool(s.anthropic_api_key),
        "alpaca_keys_set": bool(s.alpaca_api_key and s.alpaca_secret_key),
        "sec_user_agent_set": bool(s.sec_user_agent),
    }


@app.post("/research/{ticker}")
def research(ticker: str) -> dict[str, Any]:
    s = get_settings()
    if not s.anthropic_api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
    ticker = ticker.upper()
    snapshot = build_snapshot(ticker, s.sec_user_agent)
    result = generate_thesis(
        api_key=s.anthropic_api_key,
        model=s.anthropic_model,
        ticker=ticker,
        research_context=snapshot.to_context(),
        today_iso=today_iso(),
    )
    report_path = s.research_dir / f"{ticker}-{today_iso()}.md"
    report_path.write_text(result.markdown)
    research_id = _db().save_research(
        ticker=ticker,
        thesis_summary=result.markdown[:1000],
        thesis_direction=result.direction,
        full_report_path=report_path,
        inputs={
            "price": snapshot.price,
            "filing": snapshot.filing_accession,
            "usage": result.usage,
        },
    )
    return {
        "research_id": research_id,
        "ticker": ticker,
        "recommendation": result.recommendation,
        "direction": result.direction,
        "thesis_markdown": result.markdown,
        "snapshot": {
            "price": snapshot.price,
            "sma_50": snapshot.sma_50,
            "sma_200": snapshot.sma_200,
            "return_6mo_pct": snapshot.return_6mo_pct,
            "filing_accession": snapshot.filing_accession,
            "filing_date": snapshot.filing_date,
        },
        "usage": result.usage,
    }


@app.post("/propose/{ticker}")
def propose(ticker: str, body: ProposeBody) -> dict[str, Any]:
    s = get_settings()
    ticker = ticker.upper()
    db = _db()
    research_row = db.latest_research(ticker)
    if body.thesis_direction is None:
        if not research_row:
            raise HTTPException(409, f"No stored research for {ticker}; pass thesis_direction or call /research first")
        direction = research_row["thesis_direction"] or "neutral"
        excerpt = research_row["thesis_summary"]
        research_id = research_row["id"]
    else:
        direction = body.thesis_direction.lower()
        excerpt = f"User-provided thesis direction: {direction}"
        research_id = research_row["id"] if research_row else None

    try:
        proposal = propose_trade(
            ticker=ticker,
            thesis_direction=direction,
            capital_usd=body.capital_usd,
            max_notional_usd=s.max_notional_usd,
            broker=_broker(),
            thesis_summary_excerpt=excerpt,
        )
    except ProposalError as exc:
        raise HTTPException(409, str(exc))

    ticket_id = db.next_ticket_id()
    db.save_ticket(
        ticket_id=ticket_id,
        ticker=proposal.ticker,
        side=proposal.side,
        asset_type=proposal.asset_type,
        qty=proposal.qty,
        estimated_price=proposal.estimated_price,
        estimated_notional=proposal.estimated_notional,
        rationale=proposal.rationale,
        research_id=research_id,
        order_payload=proposal.order_payload,
    )
    return {
        "ticket_id": ticket_id,
        "ticker": proposal.ticker,
        "side": proposal.side,
        "qty": proposal.qty,
        "estimated_price": proposal.estimated_price,
        "estimated_notional": proposal.estimated_notional,
        "rationale": proposal.rationale,
        "approve_with": f"POST /tickets/{ticket_id}/execute body: {{\"confirmation\": \"APPROVE {proposal.ticker} {ticket_id}\"}}",
    }


@app.get("/tickets")
def list_tickets(status: str | None = None) -> dict[str, Any]:
    return {"tickets": _db().list_tickets(status=status)}


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict[str, Any]:
    row = _db().get_ticket(ticket_id)
    if not row:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return row


@app.post("/tickets/{ticket_id}/execute")
def execute_endpoint(ticket_id: str, body: ExecuteBody) -> dict[str, Any]:
    s = get_settings()
    db = _db()
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    try:
        plan = build_execution_plan(ticket)
    except GuardrailError as exc:
        raise HTTPException(409, str(exc))

    if body.confirmation.strip() != plan.expected_confirmation:
        raise HTTPException(
            400,
            f"confirmation must equal exactly: {plan.expected_confirmation}",
        )

    try:
        result = execute_ticket(ticket=ticket, broker=_broker(), max_notional_usd=s.max_notional_usd)
    except GuardrailError as exc:
        raise HTTPException(409, f"Guardrail tripped: {exc}")

    db.save_execution(
        ticket_id=plan.ticket_id,
        broker=result.broker,
        broker_order_id=result.broker_order_id,
        fill_price=result.fill_price,
        fill_qty=result.fill_qty,
        status=result.status,
        raw_response=result.raw,
    )
    db.update_ticket_status(plan.ticket_id, "executed")
    return {
        "ticket_id": plan.ticket_id,
        "broker_order_id": result.broker_order_id,
        "status": result.status,
        "fill_price": result.fill_price,
        "fill_qty": result.fill_qty,
    }


@app.get("/positions")
def positions() -> dict[str, Any]:
    pos = _broker().list_positions()
    return {
        "positions": [
            {
                "ticker": p.ticker,
                "qty": p.qty,
                "avg_entry_price": p.avg_entry_price,
                "market_value": p.market_value,
                "unrealized_pl": p.unrealized_pl,
            }
            for p in pos
        ]
    }


@app.post("/halt")
def halt() -> dict[str, int]:
    cancelled = _broker().cancel_all_open_orders()
    blocked = _db().block_pending_tickets()
    return {"cancelled_open_orders": cancelled, "blocked_pending_tickets": blocked}


_FRONTEND_DIR = Path(__file__).resolve().parent / "static" / "ui"
if _FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=_FRONTEND_DIR, html=True), name="ui")
