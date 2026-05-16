from __future__ import annotations

from typing import Any

from argo.brokers.base import OrderResult, Position


class AlpacaBroker:
    name = "alpaca"

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        if not api_key or not secret_key:
            raise ValueError("Alpaca credentials missing — set ALPACA_API_KEY and ALPACA_SECRET_KEY.")

        self.paper = paper
        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.data = StockHistoricalDataClient(api_key, secret_key)

    def latest_price(self, ticker: str) -> float | None:
        from alpaca.data.requests import StockLatestTradeRequest

        req = StockLatestTradeRequest(symbol_or_symbols=ticker.upper())
        trade = self.data.get_stock_latest_trade(req)
        rec = trade.get(ticker.upper()) if isinstance(trade, dict) else None
        return float(rec.price) if rec else None

    def place_market_order(self, ticker: str, side: str, qty: float) -> OrderResult:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=ticker.upper(),
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self.trading.submit_order(req)
        raw = self._dump(order)
        return OrderResult(
            broker=self.name,
            broker_order_id=str(order.id) if getattr(order, "id", None) else None,
            status=str(getattr(order, "status", "submitted")),
            fill_price=float(order.filled_avg_price) if getattr(order, "filled_avg_price", None) else None,
            fill_qty=float(order.filled_qty) if getattr(order, "filled_qty", None) else None,
            raw=raw,
        )

    def list_positions(self) -> list[Position]:
        positions = self.trading.get_all_positions()
        out: list[Position] = []
        for p in positions:
            out.append(
                Position(
                    ticker=str(p.symbol),
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    market_value=float(p.market_value),
                    unrealized_pl=float(p.unrealized_pl),
                )
            )
        return out

    def cancel_all_open_orders(self) -> int:
        cancelled = self.trading.cancel_orders()
        return len(cancelled or [])

    @staticmethod
    def _dump(obj: Any) -> dict[str, Any]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if hasattr(obj, "_raw"):
            return dict(obj._raw)
        return {"repr": repr(obj)}
