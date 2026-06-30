from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

OptionType = Literal["call", "put"]


@dataclass
class OptionContract:
    symbol: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        if self.bid <= 0 and self.ask <= 0:
            return None
        return round((self.bid + self.ask) / 2, 4)

    @property
    def dte(self) -> int:
        return max(0, (self.expiry - date.today()).days)


@dataclass
class OptionChain:
    underlying: str
    spot_price: float
    expiry: date
    risk_free_rate: float
    calls: list[OptionContract] = field(default_factory=list)
    puts: list[OptionContract] = field(default_factory=list)

    def all(self) -> list[OptionContract]:
        return [*self.calls, *self.puts]

    def by_type(self, option_type: OptionType) -> list[OptionContract]:
        return self.calls if option_type == "call" else self.puts


def list_expiries(ticker: str) -> list[date]:
    import yfinance as yf

    t = yf.Ticker(ticker.upper())
    out: list[date] = []
    for e in t.options or []:
        try:
            out.append(datetime.strptime(e, "%Y-%m-%d").date())
        except ValueError:
            continue
    return out


def _compute_greeks(
    contracts: list[OptionContract],
    spot: float,
    risk_free_rate: float,
    today: date,
) -> None:
    """Fill missing IV/delta/gamma/theta/vega using py_vollib_vectorized."""
    rows = [c for c in contracts if c.mid is not None and c.dte > 0]
    if not rows:
        return

    import numpy as np
    from py_vollib_vectorized import (
        vectorized_implied_volatility,
        vectorized_delta,
        vectorized_gamma,
        vectorized_theta,
        vectorized_vega,
    )

    prices = np.array([c.mid for c in rows], dtype=float)
    strikes = np.array([c.strike for c in rows], dtype=float)
    spots = np.full(len(rows), spot, dtype=float)
    ttes = np.array([max(c.dte, 1) / 365.0 for c in rows], dtype=float)
    rates = np.full(len(rows), risk_free_rate, dtype=float)
    flags = np.array(["c" if c.option_type == "call" else "p" for c in rows])

    try:
        iv = vectorized_implied_volatility(
            prices, spots, strikes, ttes, rates, flags, return_as="numpy"
        )
        delta = vectorized_delta(flags, spots, strikes, ttes, rates, iv, return_as="numpy")
        gamma = vectorized_gamma(flags, spots, strikes, ttes, rates, iv, return_as="numpy")
        theta = vectorized_theta(flags, spots, strikes, ttes, rates, iv, return_as="numpy")
        vega = vectorized_vega(flags, spots, strikes, ttes, rates, iv, return_as="numpy")
    except Exception:
        return

    for i, c in enumerate(rows):
        if c.iv is None and float(iv[i]) > 0:
            c.iv = float(iv[i])
        if c.delta is None:
            c.delta = float(delta[i])
        if c.gamma is None:
            c.gamma = float(gamma[i])
        if c.theta is None:
            c.theta = float(theta[i]) / 365.0
        if c.vega is None:
            c.vega = float(vega[i]) / 100.0


def fetch_chain(
    ticker: str,
    expiry: date,
    *,
    spot_override: float | None = None,
    risk_free_rate: float = 0.045,
    compute_missing_greeks: bool = True,
) -> OptionChain:
    """Fetch an option chain via yfinance and (optionally) compute missing Greeks."""
    import yfinance as yf

    underlying = ticker.upper()
    t = yf.Ticker(underlying)
    if spot_override is not None:
        spot = float(spot_override)
    else:
        hist = t.history(period="1d", auto_adjust=False)
        if hist.empty:
            raise ValueError(f"No price history for {underlying}")
        spot = float(hist["Close"].iloc[-1])

    raw = t.option_chain(expiry.strftime("%Y-%m-%d"))
    calls: list[OptionContract] = []
    puts: list[OptionContract] = []

    for df, side, bucket in [(raw.calls, "call", calls), (raw.puts, "put", puts)]:
        if df is None or df.empty:
            continue
        for row in df.itertuples(index=False):
            bucket.append(
                OptionContract(
                    symbol=str(getattr(row, "contractSymbol", "")),
                    underlying=underlying,
                    expiry=expiry,
                    strike=float(getattr(row, "strike")),
                    option_type=side,  # type: ignore[arg-type]
                    bid=_nullable(getattr(row, "bid", None)),
                    ask=_nullable(getattr(row, "ask", None)),
                    last=_nullable(getattr(row, "lastPrice", None)),
                    iv=_nullable(getattr(row, "impliedVolatility", None)),
                    open_interest=_nullable_int(getattr(row, "openInterest", None)),
                    volume=_nullable_int(getattr(row, "volume", None)),
                )
            )

    chain = OptionChain(
        underlying=underlying,
        spot_price=spot,
        expiry=expiry,
        risk_free_rate=risk_free_rate,
        calls=sorted(calls, key=lambda c: c.strike),
        puts=sorted(puts, key=lambda c: c.strike),
    )
    if compute_missing_greeks:
        _compute_greeks(chain.all(), spot, risk_free_rate, date.today())
    return chain


def _nullable(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _nullable_int(value) -> int | None:
    f = _nullable(value)
    if f is None:
        return None
    return int(f)
