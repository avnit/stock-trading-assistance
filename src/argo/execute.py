from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from argo.brokers.base import BrokerClient, OrderResult


class GuardrailError(Exception):
    pass


@dataclass
class ExecutionPlan:
    ticket_id: str
    ticker: str
    side: str
    qty: float
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
        expected_confirmation=f"APPROVE {ticket['ticker']} {ticket['id']}",
    )


def execute_ticket(
    *,
    ticket: dict[str, Any],
    broker: BrokerClient,
    max_notional_usd: float,
) -> OrderResult:
    """Place the order. Re-checks the notional cap with a fresh price quote."""
    plan = build_execution_plan(ticket)
    fresh_price = broker.latest_price(plan.ticker)
    if fresh_price is None:
        raise GuardrailError(f"Could not fetch a fresh price for {plan.ticker} — refusing to execute.")
    fresh_notional = fresh_price * plan.qty
    if fresh_notional > max_notional_usd:
        raise GuardrailError(
            f"Fresh quote ${fresh_price:.2f} × {plan.qty} = ${fresh_notional:.2f} "
            f"exceeds cap ${max_notional_usd:.2f}. Refusing to execute."
        )
    return broker.place_market_order(plan.ticker, plan.side, plan.qty)
