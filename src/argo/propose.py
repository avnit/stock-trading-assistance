from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from argo.brokers.base import BrokerClient


@dataclass
class TradeProposal:
    ticker: str
    side: str
    asset_type: str
    qty: float
    estimated_price: float | None
    estimated_notional: float | None
    rationale: str
    order_payload: dict[str, Any]


class ProposalError(Exception):
    pass


def propose_trade(
    *,
    ticker: str,
    thesis_direction: str,
    capital_usd: float,
    max_notional_usd: float,
    broker: BrokerClient,
    thesis_summary_excerpt: str,
) -> TradeProposal:
    """Phase 0: stock-only proposals.

    bullish  -> BUY shares, sized to min(capital, max_notional)
    bearish  -> AVOID (we don't short in Phase 0)
    neutral  -> AVOID
    """
    ticker = ticker.upper()
    direction = thesis_direction.lower()

    if direction != "bullish":
        raise ProposalError(
            f"Direction is '{direction}'. Phase 0 only proposes long-stock trades on bullish theses. "
            f"For bearish/neutral, no trade is proposed."
        )

    if capital_usd <= 0:
        raise ProposalError("--capital must be > 0.")

    notional = min(capital_usd, max_notional_usd)
    price = broker.latest_price(ticker)
    if not price or price <= 0:
        raise ProposalError(f"Could not fetch a valid latest price for {ticker}.")

    qty_float = notional / price
    qty = int(qty_float)
    if qty < 1:
        raise ProposalError(
            f"At ${price:.2f}/share, ${notional:.2f} only buys {qty_float:.3f} shares. "
            f"Increase capital or pick a cheaper ticker. (Phase 0 does not use fractional shares.)"
        )

    rationale = (
        f"Long {qty} share(s) of {ticker} at ~${price:.2f}. "
        f"Thesis is bullish. Risk = entire position value (~${qty * price:.2f}). "
        f"Stop discipline: human-decided. "
        f"Excerpt: {thesis_summary_excerpt[:300].strip()}..."
    )

    return TradeProposal(
        ticker=ticker,
        side="buy",
        asset_type="stock",
        qty=qty,
        estimated_price=price,
        estimated_notional=qty * price,
        rationale=rationale,
        order_payload={"ticker": ticker, "side": "buy", "qty": qty, "type": "market"},
    )
