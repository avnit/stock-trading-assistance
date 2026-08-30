from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass
class OrderResult:
    broker: str
    broker_order_id: str | None
    status: str
    fill_price: float | None
    fill_qty: float | None
    raw: dict[str, Any]


@dataclass
class Position:
    ticker: str
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pl: float


@dataclass
class OptionLegOrder:
    """One leg of a multi-leg options order. Symbol is the OCC contract symbol."""
    symbol: str
    action: Literal["buy", "sell"]
    ratio: int = 1


class BrokerClient(Protocol):
    name: str

    def latest_price(self, ticker: str) -> float | None: ...
    def place_market_order(self, ticker: str, side: str, qty: float) -> OrderResult: ...
    def place_multi_leg_order(
        self,
        legs: list[OptionLegOrder],
        *,
        qty: int,
        limit_price: float | None,
    ) -> OrderResult: ...
    def list_positions(self) -> list[Position]: ...
    def cancel_all_open_orders(self) -> int: ...
