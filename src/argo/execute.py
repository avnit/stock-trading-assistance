from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from argo.brokers.base import BrokerClient, OptionLegOrder, OrderResult


class GuardrailError(Exception):
    pass


@dataclass
class ExecutionPlan:
    ticket_id: str
    ticker: str
    side: str
    qty: float
    asset_type: str
    expected_confirmation: str


def build_execution_plan(ticket: dict[str, Any]) -> ExecutionPlan:
    if ticket["status"] != "pending":
        raise GuardrailError(
            f"Ticket {ticket['id']} is in status '{ticket['status']}', not 'pending'. Refusing to execute."
        )
    return ExecutionPlan(
        ticket_id=ticket["id"],
        ticker=ticket["ticker"],
        side=ticket["side"],
        qty=float(ticket["qty"]),
        asset_type=ticket.get("asset_type", "stock"),
        expected_confirmation=f"APPROVE {ticket['ticker']} {ticket['id']}",
    )


def execute_ticket(
    *,
    ticket: dict[str, Any],
    broker: BrokerClient,
    max_notional_usd: float,
) -> OrderResult:
    """Place the order. Re-checks the notional cap before submitting."""
    plan = build_execution_plan(ticket)
    if plan.asset_type == "option":
        return _execute_options(ticket, plan, broker, max_notional_usd)
    return _execute_stock(plan, broker, max_notional_usd)


def _execute_stock(plan: ExecutionPlan, broker: BrokerClient, cap: float) -> OrderResult:
    fresh_price = broker.latest_price(plan.ticker)
    if fresh_price is None:
        raise GuardrailError(f"Could not fetch a fresh price for {plan.ticker} — refusing to execute.")
    fresh_notional = fresh_price * plan.qty
    if fresh_notional > cap:
        raise GuardrailError(
            f"Fresh quote ${fresh_price:.2f} × {plan.qty} = ${fresh_notional:.2f} "
            f"exceeds cap ${cap:.2f}. Refusing to execute."
        )
    return broker.place_market_order(plan.ticker, plan.side, plan.qty)


def _execute_options(
    ticket: dict[str, Any],
    plan: ExecutionPlan,
    broker: BrokerClient,
    cap: float,
) -> OrderResult:
    legs_raw = ticket.get("legs_json")
    if not legs_raw:
        raise GuardrailError(f"Ticket {plan.ticket_id} has no legs_json — refusing to execute.")
    legs = json.loads(legs_raw)
    if not legs:
        raise GuardrailError(f"Ticket {plan.ticket_id} legs list is empty.")

    analysis_raw = ticket.get("analysis_json")
    analysis = json.loads(analysis_raw) if analysis_raw else {}
    max_loss = abs(analysis.get("max_loss") or 0.0) * plan.qty
    if max_loss and max_loss > cap:
        raise GuardrailError(
            f"Stored max loss ${max_loss:.2f} (per-contract × {plan.qty}) "
            f"exceeds cap ${cap:.2f}. Refusing to execute."
        )

    limit_price = ticket.get("estimated_price")
    if limit_price is None:
        raise GuardrailError(f"Ticket {plan.ticket_id} has no estimated_price (limit) — refusing.")

    leg_orders = [
        OptionLegOrder(
            symbol=str(leg["symbol"]),
            action=str(leg["action"]),  # type: ignore[arg-type]
            ratio=int(leg.get("ratio", 1)),
        )
        for leg in legs
    ]
    return broker.place_multi_leg_order(
        leg_orders, qty=int(plan.qty), limit_price=float(limit_price)
    )
