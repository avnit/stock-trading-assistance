from dataclasses import dataclass

import pytest

from argo.brokers.base import OrderResult, Position
from argo.propose import ProposalError, propose_trade


@dataclass
class FakeBroker:
    name: str = "fake"
    price: float = 100.0

    def latest_price(self, ticker: str):
        return self.price

    def place_market_order(self, ticker: str, side: str, qty: float) -> OrderResult:
        return OrderResult(
            broker=self.name,
            broker_order_id="order-1",
            status="filled",
            fill_price=self.price,
            fill_qty=qty,
            raw={"ticker": ticker, "side": side, "qty": qty},
        )

    def list_positions(self) -> list[Position]:
        return []

    def cancel_all_open_orders(self) -> int:
        return 0


def test_bullish_proposal_long_stock():
    b = FakeBroker(price=50.0)
    p = propose_trade(
        ticker="AAPL",
        thesis_direction="bullish",
        capital_usd=300.0,
        max_notional_usd=500.0,
        broker=b,
        thesis_summary_excerpt="strong",
    )
    assert p.side == "buy"
    assert p.qty == 6
    assert p.estimated_notional == 300.0


def test_cap_clamps_capital():
    b = FakeBroker(price=10.0)
    p = propose_trade(
        ticker="X",
        thesis_direction="bullish",
        capital_usd=10_000.0,
        max_notional_usd=500.0,
        broker=b,
        thesis_summary_excerpt="...",
    )
    assert p.qty == 50
    assert p.estimated_notional == 500.0


def test_bearish_rejected():
    b = FakeBroker(price=50.0)
    with pytest.raises(ProposalError):
        propose_trade(
            ticker="X",
            thesis_direction="bearish",
            capital_usd=300.0,
            max_notional_usd=500.0,
            broker=b,
            thesis_summary_excerpt="...",
        )


def test_insufficient_capital_for_one_share():
    b = FakeBroker(price=600.0)
    with pytest.raises(ProposalError):
        propose_trade(
            ticker="X",
            thesis_direction="bullish",
            capital_usd=300.0,
            max_notional_usd=500.0,
            broker=b,
            thesis_summary_excerpt="...",
        )


def test_zero_capital_rejected():
    b = FakeBroker(price=50.0)
    with pytest.raises(ProposalError):
        propose_trade(
            ticker="X",
            thesis_direction="bullish",
            capital_usd=0,
            max_notional_usd=500.0,
            broker=b,
            thesis_summary_excerpt="...",
        )
