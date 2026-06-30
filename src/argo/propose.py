from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from argo.brokers.base import BrokerClient
from argo.options.analytics import StrategyAnalysis, analyze_strategy
from argo.options.chains import OptionChain, fetch_chain, list_expiries
from argo.options.iv_rank import compute_iv_rank, historical_iv_proxy
from argo.options.selector import select_template
from argo.options.strategies import (
    Strategy,
    StrategyError,
    StrategyLeg,
    TEMPLATES,
    build_strategy,
)


class ProposalError(Exception):
    pass


@dataclass
class TradeProposal:
    ticker: str
    side: str                      # "buy" or "sell" (single-leg) | "multi" (multi-leg)
    asset_type: str                # "stock" | "option"
    qty: float
    estimated_price: float | None
    estimated_notional: float | None
    rationale: str
    order_payload: dict[str, Any]
    strategy_template: str | None = None
    legs: list[dict[str, Any]] = field(default_factory=list)
    analysis: dict[str, Any] | None = None


# --- Phase 0: long stock on bullish thesis ----------------------------------


def propose_trade(
    *,
    ticker: str,
    thesis_direction: str,
    capital_usd: float,
    max_notional_usd: float,
    broker: BrokerClient,
    thesis_summary_excerpt: str,
) -> TradeProposal:
    """Phase 0 stock proposal (long stock on bullish thesis)."""
    ticker = ticker.upper()
    direction = thesis_direction.lower()

    if direction != "bullish":
        raise ProposalError(
            f"Direction is '{direction}'. Long-stock proposals require a bullish thesis. "
            f"For bearish/neutral, use an options strategy via `propose_options(...)`."
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
            f"Increase capital or pick a cheaper ticker. (Stock proposals don't use fractional shares.)"
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


# --- Phase 1: options strategies --------------------------------------------


def _pick_expiry(ticker: str, target_dte: int) -> date:
    expiries = list_expiries(ticker)
    if not expiries:
        raise ProposalError(f"No option expiries listed for {ticker}.")
    today = date.today()
    target = today + timedelta(days=target_dte)
    return min(expiries, key=lambda d: abs((d - target).days))


def _leg_to_dict(leg: StrategyLeg) -> dict[str, Any]:
    c = leg.contract
    return {
        "symbol": c.symbol,
        "underlying": c.underlying,
        "expiry": c.expiry.isoformat(),
        "strike": c.strike,
        "option_type": c.option_type,
        "action": leg.action,
        "ratio": leg.ratio,
        "mid": c.mid,
        "iv": c.iv,
        "delta": c.delta,
        "bid": c.bid,
        "ask": c.ask,
    }


def _max_loss_from_analysis(strategy: Strategy, analysis: StrategyAnalysis) -> float:
    """Upper-bound notional risk for the cap check, per single-contract."""
    if analysis.max_loss is not None:
        return abs(analysis.max_loss)
    if strategy.template == "cash_secured_put":
        short_leg = strategy.legs[0]
        return short_leg.contract.strike * 100
    if strategy.template == "covered_call":
        return 0.0
    if strategy.template in {"long_call", "long_put"}:
        return abs((strategy.net_debit_credit or 0)) * 100
    return float("inf")


def propose_options(
    *,
    ticker: str,
    thesis_direction: str,
    max_notional_usd: float,
    template_key: str | None = None,
    iv_rank: float | None = None,
    target_dte: int = 35,
    target_delta: float | None = None,
    width: float | None = None,
    own_shares: bool = False,
    thesis_summary_excerpt: str = "",
    qty: int = 1,
    chain: OptionChain | None = None,
) -> TradeProposal:
    """Generate a multi-leg options proposal.

    `chain` is exposed for tests; production callers leave it None and the chain
    is fetched via yfinance.
    """
    ticker = ticker.upper()
    if qty < 1:
        raise ProposalError("qty must be >= 1.")

    if chain is None:
        expiry = _pick_expiry(ticker, target_dte)
        chain = fetch_chain(ticker, expiry)

    if iv_rank is None:
        atm_iv = _atm_iv(chain)
        if atm_iv is None:
            iv_rank_val = 50.0
        else:
            history = historical_iv_proxy(ticker)
            iv_rank_val = compute_iv_rank(atm_iv, history).iv_rank if history else 50.0
    else:
        iv_rank_val = float(iv_rank)

    if template_key is None:
        sel = select_template(
            thesis_direction=thesis_direction,
            iv_rank=iv_rank_val,
            own_shares=own_shares,
        )
        template_key = sel.template.key
        selector_note = sel.rationale
    else:
        if template_key not in TEMPLATES:
            raise ProposalError(
                f"Unknown strategy '{template_key}'. Known: {sorted(TEMPLATES.keys())}"
            )
        selector_note = f"Strategy '{template_key}' provided explicitly."

    try:
        strategy = build_strategy(
            template_key, chain, target_delta=target_delta, width=width
        )
    except StrategyError as exc:
        raise ProposalError(str(exc)) from exc

    analysis = analyze_strategy(
        strategy,
        spot=chain.spot_price,
        volatility=_atm_iv(chain) or 0.3,
        risk_free_rate=chain.risk_free_rate,
    )

    max_loss_per_contract = _max_loss_from_analysis(strategy, analysis)
    total_max_loss = max_loss_per_contract * qty
    if total_max_loss > max_notional_usd:
        raise ProposalError(
            f"Max loss ${total_max_loss:.2f} (per-contract ${max_loss_per_contract:.2f} × {qty}) "
            f"exceeds notional cap ${max_notional_usd:.2f}. "
            f"Reduce qty, pick a tighter width, or raise ARGO_MAX_NOTIONAL_USD."
        )

    legs_payload = [_leg_to_dict(l) for l in strategy.legs]
    net = strategy.net_debit_credit or 0.0
    estimated_price = round(net, 4)
    estimated_notional = round(net * 100 * qty, 2)

    rationale = (
        f"{strategy.notes}. {selector_note} "
        f"Net {'credit' if net < 0 else 'debit'} ~${abs(net):.2f}/contract × {qty}. "
        f"Max loss ${analysis.max_loss}, max gain ${analysis.max_gain}, "
        f"PoP {analysis.to_dict()['pop_pct']}%, breakevens {analysis.breakevens}. "
        f"IV rank {iv_rank_val:.1f}. Thesis: {thesis_summary_excerpt[:200].strip()}..."
    )

    order_payload = {
        "asset_type": "option",
        "underlying": ticker,
        "strategy": template_key,
        "qty": qty,
        "limit_price": estimated_price,
        "legs": legs_payload,
    }

    return TradeProposal(
        ticker=ticker,
        side="multi",
        asset_type="option",
        qty=qty,
        estimated_price=estimated_price,
        estimated_notional=estimated_notional,
        rationale=rationale,
        order_payload=order_payload,
        strategy_template=template_key,
        legs=legs_payload,
        analysis=analysis.to_dict(),
    )


def _atm_iv(chain: OptionChain) -> float | None:
    candidates = [c for c in chain.all() if c.iv is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c.strike - chain.spot_price)).iv
