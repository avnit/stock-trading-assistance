import json
from dataclasses import dataclass

import pytest

from argo.brokers.base import OptionLegOrder, OrderResult, Position
from argo.execute import GuardrailError, execute_ticket


@dataclass
class FakeBroker:
    name: str = "fake"
    placed: dict | None = None

    def latest_price(self, ticker):
        return 100.0

    def place_market_order(self, ticker, side, qty):
        return OrderResult(broker=self.name, broker_order_id="o-1", status="filled",
                           fill_price=100.0, fill_qty=qty, raw={})

    def place_multi_leg_order(self, legs, *, qty, limit_price):
        self.placed = {"legs": legs, "qty": qty, "limit_price": limit_price}
        return OrderResult(broker=self.name, broker_order_id="ml-1", status="filled",
                           fill_price=limit_price, fill_qty=qty, raw={})

    def list_positions(self):
        return []

    def cancel_all_open_orders(self):
        return 0


def _options_ticket(**overrides):
    legs = [
        {"symbol": "X100C", "action": "sell", "ratio": 1, "strike": 100, "option_type": "call"},
        {"symbol": "X105C", "action": "buy", "ratio": 1, "strike": 105, "option_type": "call"},
    ]
    base = {
        "id": "TKT-001",
        "ticker": "X",
        "status": "pending",
        "side": "multi",
        "asset_type": "option",
        "qty": 1,
        "estimated_price": -1.20,
        "estimated_notional": -120.0,
        "legs_json": json.dumps(legs),
        "analysis_json": json.dumps({"max_loss": -380.0, "max_gain": 120.0}),
    }
    base.update(overrides)
    return base


def test_execute_options_places_multi_leg_order():
    b = FakeBroker()
    res = execute_ticket(ticket=_options_ticket(), broker=b, max_notional_usd=10_000)
    assert res.status == "filled"
    assert b.placed is not None
    assert b.placed["qty"] == 1
    assert b.placed["limit_price"] == -1.20
    assert len(b.placed["legs"]) == 2
    assert all(isinstance(l, OptionLegOrder) for l in b.placed["legs"])


def test_execute_options_blocked_when_stored_max_loss_exceeds_cap():
    b = FakeBroker()
    with pytest.raises(GuardrailError, match="exceeds cap"):
        execute_ticket(ticket=_options_ticket(), broker=b, max_notional_usd=100)


def test_execute_options_requires_legs():
    b = FakeBroker()
    with pytest.raises(GuardrailError, match="no legs_json"):
        execute_ticket(ticket=_options_ticket(legs_json=None), broker=b, max_notional_usd=10_000)


def test_execute_options_requires_limit_price():
    b = FakeBroker()
    with pytest.raises(GuardrailError, match="no estimated_price"):
        execute_ticket(ticket=_options_ticket(estimated_price=None), broker=b, max_notional_usd=10_000)


def test_execute_stock_path_unchanged():
    b = FakeBroker()
    ticket = {
        "id": "TKT-002", "ticker": "AAPL", "status": "pending", "side": "buy",
        "asset_type": "stock", "qty": 1,
    }
    res = execute_ticket(ticket=ticket, broker=b, max_notional_usd=10_000)
    assert res.status == "filled"
