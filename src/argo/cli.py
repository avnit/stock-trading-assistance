from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from argo.brokers import AlpacaBroker
from argo.config import get_settings
from argo.db import DB
from argo.execute import GuardrailError, build_execution_plan, execute_ticket
from argo.llm import generate_thesis
from argo.options import TEMPLATES, list_expiries
from argo.propose import ProposalError, propose_options, propose_trade
from argo.research import build_snapshot, today_iso

app = typer.Typer(
    help="argo — stock research and trading assistant (Phase 1, Alpaca paper).",
    no_args_is_help=True,
)
console = Console()


def _broker() -> AlpacaBroker:
    s = get_settings()
    return AlpacaBroker(api_key=s.alpaca_api_key, secret_key=s.alpaca_secret_key, paper=s.alpaca_paper)


def _db() -> DB:
    s = get_settings()
    return DB(s.db_path)


@app.command()
def research(ticker: str = typer.Argument(..., help="US-listed ticker, e.g. NVDA")):
    """Pull 10-K + fundamentals + price, synthesize a thesis."""
    s = get_settings()
    if not s.anthropic_api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set.[/red]")
        raise typer.Exit(2)

    ticker = ticker.upper()
    console.print(f"[bold]Researching {ticker}...[/bold]")

    with console.status("Pulling 10-K and price data..."):
        snapshot = build_snapshot(ticker, s.sec_user_agent)

    console.print(f"  Filing: {snapshot.filing_accession or 'unknown'} ({snapshot.filing_date or '?'})")
    console.print(f"  Price: ${snapshot.price} | 50d SMA ${snapshot.sma_50} | 200d SMA ${snapshot.sma_200}")
    console.print(f"  6-month return: {snapshot.return_6mo_pct}%")

    with console.status("Generating thesis with Claude..."):
        result = generate_thesis(
            api_key=s.anthropic_api_key,
            model=s.anthropic_model,
            ticker=ticker,
            research_context=snapshot.to_context(),
            today_iso=today_iso(),
        )

    today = date.today().isoformat()
    report_path = s.research_dir / f"{ticker}-{today}.md"
    report_path.write_text(result.markdown)

    db = _db()
    research_id = db.save_research(
        ticker=ticker,
        thesis_summary=result.markdown[:1000],
        thesis_direction=result.direction,
        full_report_path=report_path,
        inputs={
            "price": snapshot.price,
            "sma_50": snapshot.sma_50,
            "sma_200": snapshot.sma_200,
            "filing": snapshot.filing_accession,
            "usage": result.usage,
        },
    )

    console.print()
    console.print(Markdown(result.markdown))
    console.print()
    console.print(
        Panel.fit(
            f"Saved to [cyan]{report_path}[/cyan] | research id [bold]{research_id}[/bold] | "
            f"recommendation [bold]{result.recommendation}[/bold] | direction [bold]{result.direction}[/bold]",
            title="research",
        )
    )


@app.command()
def propose(
    ticker: str = typer.Argument(..., help="US-listed ticker"),
    thesis: str = typer.Option(
        None,
        "--thesis",
        help="Override the thesis direction (bullish/bearish/neutral). Defaults to the latest stored research.",
    ),
    capital: float = typer.Option(..., "--capital", help="USD capital to allocate (capped by ARGO_MAX_NOTIONAL_USD)"),
):
    """Generate a trade ticket (Phase 0: long stock on bullish theses only)."""
    s = get_settings()
    ticker = ticker.upper()
    db = _db()

    research_row = db.latest_research(ticker)
    if thesis is None:
        if not research_row:
            console.print(f"[red]No stored research for {ticker}. Run `argo research {ticker}` first or pass --thesis.[/red]")
            raise typer.Exit(2)
        direction = research_row["thesis_direction"] or "neutral"
        thesis_excerpt = research_row["thesis_summary"]
        research_id = research_row["id"]
    else:
        direction = thesis.lower()
        thesis_excerpt = f"User-provided thesis direction: {direction}"
        research_id = research_row["id"] if research_row else None

    broker = _broker()

    try:
        proposal = propose_trade(
            ticker=ticker,
            thesis_direction=direction,
            capital_usd=capital,
            max_notional_usd=s.max_notional_usd,
            broker=broker,
            thesis_summary_excerpt=thesis_excerpt,
        )
    except ProposalError as exc:
        console.print(f"[yellow]No proposal: {exc}[/yellow]")
        raise typer.Exit(1)

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

    table = Table(title=f"Ticket {ticket_id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("ticker", proposal.ticker)
    table.add_row("side", proposal.side)
    table.add_row("asset", proposal.asset_type)
    table.add_row("qty", str(proposal.qty))
    table.add_row("est. price", f"${proposal.estimated_price:.2f}")
    table.add_row("est. notional", f"${proposal.estimated_notional:.2f}")
    table.add_row("cap", f"${s.max_notional_usd:.2f}")
    console.print(table)
    console.print(Panel(proposal.rationale, title="rationale"))
    console.print(
        f"Approve with: [bold cyan]argo execute {ticket_id} --confirm[/bold cyan]"
    )


@app.command("propose-options")
def propose_options_cmd(
    ticker: str = typer.Argument(..., help="US-listed ticker"),
    thesis: str = typer.Option(None, "--thesis", help="bullish | bearish | neutral (defaults to latest research)"),
    strategy: str = typer.Option(None, "--strategy", help=f"One of: {', '.join(sorted(TEMPLATES.keys()))}"),
    dte: int = typer.Option(35, "--dte", help="Target days-to-expiry"),
    delta: float = typer.Option(None, "--delta", help="Target abs(delta) for primary leg"),
    width: float = typer.Option(None, "--width", help="Spread width in $ for verticals/condors"),
    iv_rank: float = typer.Option(None, "--iv-rank", help="Override IV rank 0..100"),
    own_shares: bool = typer.Option(False, "--own-shares", help="100+ shares of underlying held"),
    qty: int = typer.Option(1, "--qty", help="Number of contract sets to trade"),
):
    """Generate a multi-leg options ticket."""
    s = get_settings()
    ticker = ticker.upper()
    db = _db()
    research_row = db.latest_research(ticker)
    if thesis is None:
        if not research_row:
            console.print(f"[red]No stored research for {ticker}. Run `argo research {ticker}` first or pass --thesis.[/red]")
            raise typer.Exit(2)
        direction = research_row["thesis_direction"] or "neutral"
        excerpt = research_row["thesis_summary"]
        research_id = research_row["id"]
    else:
        direction = thesis.lower()
        excerpt = f"User-provided thesis direction: {direction}"
        research_id = research_row["id"] if research_row else None

    console.print(f"[bold]Generating options proposal for {ticker}...[/bold]")
    try:
        proposal = propose_options(
            ticker=ticker,
            thesis_direction=direction,
            max_notional_usd=s.max_notional_usd,
            template_key=strategy,
            iv_rank=iv_rank,
            target_dte=dte,
            target_delta=delta,
            width=width,
            own_shares=own_shares,
            thesis_summary_excerpt=excerpt,
            qty=qty,
        )
    except ProposalError as exc:
        console.print(f"[yellow]No proposal: {exc}[/yellow]")
        raise typer.Exit(1)

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
        strategy_template=proposal.strategy_template,
        legs=proposal.legs,
        analysis=proposal.analysis,
    )

    table = Table(title=f"Ticket {ticket_id} ({proposal.strategy_template})")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("ticker", proposal.ticker)
    table.add_row("strategy", proposal.strategy_template or "")
    table.add_row("qty", str(proposal.qty))
    table.add_row("net price", f"${proposal.estimated_price}")
    table.add_row("net notional", f"${proposal.estimated_notional}")
    if proposal.analysis:
        a = proposal.analysis
        table.add_row("max loss", str(a.get("max_loss")))
        table.add_row("max gain", str(a.get("max_gain")))
        table.add_row("PoP %", str(a.get("pop_pct")))
        table.add_row("breakevens", ", ".join(str(b) for b in (a.get("breakevens") or [])))
    console.print(table)

    leg_table = Table(title="legs")
    for col in ["action", "type", "strike", "expiry", "delta", "iv", "mid", "symbol"]:
        leg_table.add_column(col)
    for leg in proposal.legs:
        leg_table.add_row(
            leg["action"], leg["option_type"], str(leg["strike"]), leg["expiry"],
            f"{leg.get('delta') or 0:.2f}", f"{leg.get('iv') or 0:.3f}",
            f"{leg.get('mid')}", leg["symbol"],
        )
    console.print(leg_table)
    console.print(Panel(proposal.rationale, title="rationale"))
    console.print(f"Approve with: [bold cyan]argo execute {ticket_id} --confirm[/bold cyan]")


@app.command("strategies")
def strategies_cmd():
    """List built-in options strategy templates."""
    table = Table(title="Strategy templates")
    for col in ["key", "directions", "iv fit", "description"]:
        table.add_column(col)
    for tpl in TEMPLATES.values():
        table.add_row(
            tpl.key, ", ".join(tpl.direction_fit), ", ".join(tpl.iv_fit), tpl.description
        )
    console.print(table)


@app.command("expiries")
def expiries_cmd(ticker: str = typer.Argument(...)):
    """List available option expiries (yfinance)."""
    expiries = list_expiries(ticker)
    if not expiries:
        console.print(f"(no expiries for {ticker.upper()})")
        return
    for d in expiries[:20]:
        dte = (d - date.today()).days
        console.print(f"  {d.isoformat()}  (DTE={dte})")


@app.command("tickets")
def tickets_cmd(
    status: str = typer.Option(None, "--status", help="Filter by status (pending/executed/blocked)"),
):
    """List trade tickets."""
    rows = _db().list_tickets(status=status)
    if not rows:
        console.print("(no tickets)")
        return
    table = Table(title="tickets")
    for col in ["id", "ticker", "side", "qty", "est_notional", "status", "created_at"]:
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["id"],
            r["ticker"],
            r["side"],
            str(r["qty"]),
            f"${(r['estimated_notional'] or 0):.2f}",
            r["status"],
            r["created_at"],
        )
    console.print(table)


@app.command()
def execute(
    ticket_id: str = typer.Argument(..., help="Ticket ID, e.g. TKT-001"),
    confirm: bool = typer.Option(False, "--confirm", help="Prompts for typed confirmation if set"),
):
    """Execute a pending ticket via Alpaca paper trading."""
    s = get_settings()
    db = _db()
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        console.print(f"[red]Ticket {ticket_id} not found.[/red]")
        raise typer.Exit(2)

    try:
        plan = build_execution_plan(ticket)
    except GuardrailError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if not confirm:
        console.print(
            Panel(
                f"Would execute: {plan.side.upper()} {plan.qty} {plan.ticker}\n"
                f"Cap: ${s.max_notional_usd:.2f}\n\n"
                f"To proceed: rerun with --confirm",
                title=f"DRY RUN {plan.ticket_id}",
            )
        )
        return

    typed = typer.prompt(f"Type exactly: {plan.expected_confirmation}")
    if typed.strip() != plan.expected_confirmation:
        console.print("[red]Confirmation text did not match. Aborting.[/red]")
        raise typer.Exit(1)

    broker = _broker()
    try:
        result = execute_ticket(ticket=ticket, broker=broker, max_notional_usd=s.max_notional_usd)
    except GuardrailError as exc:
        console.print(f"[red]Guardrail tripped: {exc}[/red]")
        raise typer.Exit(1)

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

    console.print(
        Panel.fit(
            f"order id: {result.broker_order_id}\n"
            f"status:   {result.status}\n"
            f"fill:     {result.fill_qty} @ ${result.fill_price}",
            title=f"executed {plan.ticket_id}",
        )
    )


@app.command()
def positions():
    """List current Alpaca paper positions."""
    broker = _broker()
    pos = broker.list_positions()
    if not pos:
        console.print("(no positions)")
        return
    table = Table(title="positions")
    for col in ["ticker", "qty", "avg_entry", "market_value", "unrealized_pl"]:
        table.add_column(col)
    for p in pos:
        table.add_row(
            p.ticker, str(p.qty), f"${p.avg_entry_price:.2f}", f"${p.market_value:.2f}", f"${p.unrealized_pl:.2f}"
        )
    console.print(table)


@app.command()
def halt():
    """Kill switch: cancel all open orders and block pending tickets."""
    broker = _broker()
    cancelled = broker.cancel_all_open_orders()
    blocked = _db().block_pending_tickets()
    console.print(f"[bold red]HALT[/bold red] — cancelled {cancelled} open order(s); blocked {blocked} pending ticket(s).")


@app.command("show")
def show(ticker: str = typer.Argument(..., help="Print the latest stored research markdown for TICKER")):
    """Show the latest stored research markdown."""
    row = _db().latest_research(ticker)
    if not row:
        console.print(f"(no research for {ticker.upper()})")
        raise typer.Exit(1)
    path = Path(row["full_report_path"])
    if path.exists():
        console.print(Markdown(path.read_text()))
    else:
        console.print(row["thesis_summary"])


@app.command()
def export(ticket_id: str = typer.Argument(...)):
    """Dump a ticket's full record as JSON."""
    ticket = _db().get_ticket(ticket_id)
    if not ticket:
        console.print(f"[red]Ticket {ticket_id} not found.[/red]")
        raise typer.Exit(2)
    console.print_json(json.dumps(ticket, default=str))
