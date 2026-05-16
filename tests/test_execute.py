from dataclasses import dataclass

import pytest

from argo.brokers.base import OrderResult, Position
from argo.execute import GuardrailError, build_execution_plan, execute_ticket


@dataclass
class FakeBroker:
    name: str = "fake"
    price: float = 100.0
    place_called_with: dict = None

    def latest_price(self, ticker: str):
        return self.price

    def place_market_order(self, ticker: str, side: str, qty: float) -> OrderResult:
        self.place_called_with = {"ticker": ticker, "side": side, "qty": qty}
        return OrderResult(
            broker=self.name,
            broker_order_id="order-1",
            status="filled",
            fill_price=self.price,
            fill_qty=qty,
            raw={},
        )

    def list_positions(self) -> list[Position]:
        return []

    def cancel_all_open_orders(self) -> int:
        return 0


def _pending(**overrides):
    base = {
        "id": "TKT-001",
        "ticker": "AAPL",
        "side": "buy",
        "qty": 5,
        "status": "pending",
    }
    base.update(overrides)
    return base


def test_build_plan_pending():
    p = build_execution_plan(_pending())
    assert p.expected_confirmation == "APPROVE AAPL TKT-001"


def test_build_plan_rejects_non_pending():
    with pytest.raises(GuardrailError):
        build_execution_plan(_pending(status="executed"))


def test_execute_places_order():
    b = FakeBroker(price=50.0)
    res = execute_ticket(ticket=_pending(qty=5), broker=b, max_notional_usd=500.0)
    assert b.place_called_with == {"ticker": "AAPL", "side": "buy", "qty": 5.0}
    assert res.status == "filled"


def test_execute_blocks_when_fresh_quote_exceeds_cap():
    b = FakeBroker(price=200.0)
    with pytest.raises(GuardrailError):
        execute_ticket(ticket=_pending(qty=5), broker=b, max_notional_usd=500.0)


def test_execute_blocks_when_no_fresh_price():
    b = FakeBroker(price=None)
    with pytest.raises(GuardrailError):
        execute_ticket(ticket=_pending(), broker=b, max_notional_usd=500.0)
