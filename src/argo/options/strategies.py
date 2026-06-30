from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from argo.options.chains import OptionChain, OptionContract, OptionType

Action = Literal["buy", "sell"]


class StrategyError(Exception):
    pass


@dataclass
class StrategyLeg:
    contract: OptionContract
    action: Action
    ratio: int = 1

    @property
    def signed_qty(self) -> int:
        return self.ratio if self.action == "buy" else -self.ratio


@dataclass
class Strategy:
    template: str
    underlying: str
    expiry_iso: str
    legs: list[StrategyLeg] = field(default_factory=list)
    net_debit_credit: float | None = None
    notes: str = ""

    @property
    def is_credit(self) -> bool:
        return (self.net_debit_credit or 0) < 0

    @property
    def width(self) -> float | None:
        strikes = sorted({l.contract.strike for l in self.legs if l.contract.option_type == self.legs[0].contract.option_type})
        if len(strikes) < 2:
            return None
        return round(strikes[-1] - strikes[0], 4)


def _net_price(legs: list[StrategyLeg]) -> float | None:
    total = 0.0
    for leg in legs:
        mid = leg.contract.mid
        if mid is None:
            return None
        total += leg.signed_qty * mid
    return round(total, 4)


def _pick_by_delta(
    chain: OptionChain,
    option_type: OptionType,
    target_delta: float,
) -> OptionContract:
    """Pick the contract whose abs(delta) is closest to target_delta. Falls back to
    closest-to-spot strike if Greeks are missing."""
    pool = chain.by_type(option_type)
    if not pool:
        raise StrategyError(f"No {option_type} contracts in chain for {chain.underlying}")
    with_delta = [c for c in pool if c.delta is not None]
    if with_delta:
        return min(with_delta, key=lambda c: abs(abs(c.delta) - target_delta))
    return min(pool, key=lambda c: abs(c.strike - chain.spot_price))


def _strike_offset(
    chain: OptionChain,
    option_type: OptionType,
    anchor: OptionContract,
    direction: Literal["above", "below"],
    width: float,
) -> OptionContract:
    pool = chain.by_type(option_type)
    if direction == "above":
        candidates = [c for c in pool if c.strike >= anchor.strike + width * 0.5]
        return min(candidates, key=lambda c: abs(c.strike - (anchor.strike + width)))
    candidates = [c for c in pool if c.strike <= anchor.strike - width * 0.5]
    return min(candidates, key=lambda c: abs(c.strike - (anchor.strike - width)))


# --- builders ---------------------------------------------------------------


def build_long_call(chain: OptionChain, *, target_delta: float = 0.50, **_: object) -> Strategy:
    leg = _pick_by_delta(chain, "call", target_delta)
    legs = [StrategyLeg(leg, "buy")]
    return Strategy(
        template="long_call",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=f"Long {target_delta:.2f}Δ call",
    )


def build_long_put(chain: OptionChain, *, target_delta: float = 0.50, **_: object) -> Strategy:
    leg = _pick_by_delta(chain, "put", target_delta)
    legs = [StrategyLeg(leg, "buy")]
    return Strategy(
        template="long_put",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=f"Long {target_delta:.2f}Δ put",
    )


def build_bull_call_spread(
    chain: OptionChain, *, target_delta: float = 0.40, width: float = 5.0, **_: object
) -> Strategy:
    long_leg = _pick_by_delta(chain, "call", target_delta)
    short_leg_contract = _strike_offset(chain, "call", long_leg, "above", width)
    legs = [StrategyLeg(long_leg, "buy"), StrategyLeg(short_leg_contract, "sell")]
    return Strategy(
        template="bull_call_spread",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=f"Long {long_leg.strike}C / Short {short_leg_contract.strike}C (~{width}-wide debit)",
    )


def build_short_put_vertical(
    chain: OptionChain, *, target_delta: float = 0.30, width: float = 5.0, **_: object
) -> Strategy:
    short_leg_contract = _pick_by_delta(chain, "put", target_delta)
    long_leg_contract = _strike_offset(chain, "put", short_leg_contract, "below", width)
    legs = [
        StrategyLeg(short_leg_contract, "sell"),
        StrategyLeg(long_leg_contract, "buy"),
    ]
    return Strategy(
        template="short_put_vertical",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=f"Short {short_leg_contract.strike}P / Long {long_leg_contract.strike}P (credit)",
    )


def build_iron_condor(
    chain: OptionChain,
    *,
    target_delta: float = 0.20,
    width: float = 5.0,
    **_: object,
) -> Strategy:
    short_call = _pick_by_delta(chain, "call", target_delta)
    long_call_c = _strike_offset(chain, "call", short_call, "above", width)
    short_put_c = _pick_by_delta(chain, "put", target_delta)
    long_put_c = _strike_offset(chain, "put", short_put_c, "below", width)
    legs = [
        StrategyLeg(short_call, "sell"),
        StrategyLeg(long_call_c, "buy"),
        StrategyLeg(short_put_c, "sell"),
        StrategyLeg(long_put_c, "buy"),
    ]
    return Strategy(
        template="iron_condor",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=(
            f"Short {short_call.strike}C/{short_put_c.strike}P, Long "
            f"{long_call_c.strike}C/{long_put_c.strike}P (credit)"
        ),
    )


def build_covered_call(
    chain: OptionChain, *, target_delta: float = 0.30, **_: object
) -> Strategy:
    """Just the short-call leg. Underlying shares must already be held; the proposer
    will surface that requirement to the user."""
    leg = _pick_by_delta(chain, "call", target_delta)
    legs = [StrategyLeg(leg, "sell")]
    return Strategy(
        template="covered_call",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=f"Short {target_delta:.2f}Δ call against 100 shares (income)",
    )


def build_cash_secured_put(
    chain: OptionChain, *, target_delta: float = 0.30, **_: object
) -> Strategy:
    leg = _pick_by_delta(chain, "put", target_delta)
    legs = [StrategyLeg(leg, "sell")]
    return Strategy(
        template="cash_secured_put",
        underlying=chain.underlying,
        expiry_iso=chain.expiry.isoformat(),
        legs=legs,
        net_debit_credit=_net_price(legs),
        notes=f"Short {target_delta:.2f}Δ put, fully cash-secured",
    )


@dataclass
class StrategyTemplate:
    key: str
    description: str
    direction_fit: tuple[str, ...]
    iv_fit: tuple[str, ...]
    builder: Callable[..., Strategy]
    default_delta: float
    default_width: float | None


TEMPLATES: dict[str, StrategyTemplate] = {
    "long_call": StrategyTemplate(
        "long_call", "Long call (defined-risk directional)",
        ("bullish",), ("cheap",), build_long_call, 0.50, None,
    ),
    "long_put": StrategyTemplate(
        "long_put", "Long put (defined-risk bearish)",
        ("bearish",), ("cheap",), build_long_put, 0.50, None,
    ),
    "bull_call_spread": StrategyTemplate(
        "bull_call_spread", "Bull call spread (debit, capped upside)",
        ("bullish",), ("cheap", "neutral"), build_bull_call_spread, 0.40, 5.0,
    ),
    "short_put_vertical": StrategyTemplate(
        "short_put_vertical", "Short put vertical (credit, bullish/IV-rich)",
        ("bullish",), ("rich",), build_short_put_vertical, 0.30, 5.0,
    ),
    "iron_condor": StrategyTemplate(
        "iron_condor", "Iron condor (credit, neutral, IV-rich)",
        ("neutral",), ("rich",), build_iron_condor, 0.20, 5.0,
    ),
    "covered_call": StrategyTemplate(
        "covered_call", "Covered call (income on owned shares)",
        ("neutral", "bullish"), ("rich", "neutral", "cheap"), build_covered_call, 0.30, None,
    ),
    "cash_secured_put": StrategyTemplate(
        "cash_secured_put", "Cash-secured put (income / acquire at lower price)",
        ("bullish", "neutral"), ("rich", "neutral"), build_cash_secured_put, 0.30, None,
    ),
}


def build_strategy(
    template_key: str,
    chain: OptionChain,
    *,
    target_delta: float | None = None,
    width: float | None = None,
) -> Strategy:
    if template_key not in TEMPLATES:
        raise StrategyError(
            f"Unknown template '{template_key}'. Known: {sorted(TEMPLATES.keys())}"
        )
    tpl = TEMPLATES[template_key]
    return tpl.builder(
        chain,
        target_delta=target_delta if target_delta is not None else tpl.default_delta,
        width=width if width is not None else (tpl.default_width or 0.0),
    )
