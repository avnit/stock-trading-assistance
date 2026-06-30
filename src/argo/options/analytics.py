from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from argo.options.strategies import Strategy


@dataclass
class StrategyAnalysis:
    template: str
    max_loss: float | None
    max_gain: float | None
    breakevens: list[float] = field(default_factory=list)
    pop: float | None = None
    expected_profit: float | None = None
    net_debit_credit: float | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "template": self.template,
            "max_loss": self.max_loss,
            "max_gain": self.max_gain,
            "breakevens": self.breakevens,
            "pop_pct": None if self.pop is None else round(self.pop * 100, 2),
            "expected_profit": self.expected_profit,
            "net_debit_credit": self.net_debit_credit,
            "notes": self.notes,
        }


def _optionlab_payload(strategy: Strategy, spot: float, volatility: float, rate: float):
    """Translate our Strategy to optionlab's `Inputs`."""
    today = date.today()
    expiry = date.fromisoformat(strategy.expiry_iso)
    dte_days = max((expiry - today).days, 1)

    legs = []
    for leg in strategy.legs:
        action = "buy" if leg.action == "buy" else "sell"
        legs.append(
            {
                "type": "call" if leg.contract.option_type == "call" else "put",
                "strike": leg.contract.strike,
                "premium": leg.contract.mid or leg.contract.last or 0.0,
                "n": 100 * leg.ratio,
                "action": action,
                "expiration": expiry.isoformat(),
            }
        )
    return {
        "stock_price": spot,
        "start_date": today.isoformat(),
        "target_date": expiry.isoformat(),
        "volatility": max(volatility, 0.01),
        "interest_rate": rate,
        "min_stock": max(spot * 0.5, 1.0),
        "max_stock": spot * 1.5,
        "strategy": legs,
    }


def analyze_strategy(
    strategy: Strategy,
    *,
    spot: float,
    volatility: float,
    risk_free_rate: float = 0.045,
) -> StrategyAnalysis:
    """Wrap optionlab.run_strategy for PoP / max-gain / max-loss / breakevens.

    Falls back to deterministic computation for verticals / iron condors if
    optionlab errors (e.g. legs without enough mid-prices)."""
    try:
        from optionlab import run_strategy  # type: ignore
    except ImportError:
        run_strategy = None  # type: ignore

    if run_strategy is not None:
        try:
            payload = _optionlab_payload(strategy, spot, volatility, risk_free_rate)
            out = run_strategy(payload)
            max_loss = float(getattr(out, "minimum_return_in_the_domain", 0.0) or 0.0)
            max_gain = float(getattr(out, "maximum_return_in_the_domain", 0.0) or 0.0)
            pop = float(getattr(out, "probability_of_profit", 0.0) or 0.0)
            ep = getattr(out, "expected_profit", None)
            breakevens = list(getattr(out, "strategy_breakeven_points", []) or [])
            return StrategyAnalysis(
                template=strategy.template,
                max_loss=max_loss,
                max_gain=max_gain,
                breakevens=[round(float(b), 4) for b in breakevens],
                pop=pop,
                expected_profit=float(ep) if ep is not None else None,
                net_debit_credit=strategy.net_debit_credit,
                notes=strategy.notes,
            )
        except Exception:
            pass

    return _fallback_analysis(strategy)


def _fallback_analysis(strategy: Strategy) -> StrategyAnalysis:
    """Closed-form max-loss/max-gain for verticals + iron condors + single-leg buys."""
    legs = strategy.legs
    net = strategy.net_debit_credit
    template = strategy.template

    if template in {"long_call", "long_put"}:
        return StrategyAnalysis(
            template=template,
            max_loss=-abs((net or 0.0)) * 100,
            max_gain=None,
            breakevens=[
                round(
                    legs[0].contract.strike + (net or 0)
                    if template == "long_call"
                    else legs[0].contract.strike - (net or 0),
                    4,
                )
            ],
            pop=None,
            net_debit_credit=net,
            notes=strategy.notes,
        )

    if template == "bull_call_spread":
        long_l = next(l for l in legs if l.action == "buy")
        short_l = next(l for l in legs if l.action == "sell")
        width = short_l.contract.strike - long_l.contract.strike
        debit = net or 0.0
        return StrategyAnalysis(
            template=template,
            max_loss=-abs(debit) * 100,
            max_gain=(width - abs(debit)) * 100,
            breakevens=[round(long_l.contract.strike + abs(debit), 4)],
            pop=None,
            net_debit_credit=net,
            notes=strategy.notes,
        )

    if template == "short_put_vertical":
        short_l = next(l for l in legs if l.action == "sell")
        long_l = next(l for l in legs if l.action == "buy")
        width = short_l.contract.strike - long_l.contract.strike
        credit = -(net or 0.0)
        return StrategyAnalysis(
            template=template,
            max_loss=-(width - credit) * 100,
            max_gain=credit * 100,
            breakevens=[round(short_l.contract.strike - credit, 4)],
            pop=None,
            net_debit_credit=net,
            notes=strategy.notes,
        )

    if template == "iron_condor":
        short_call = next(l for l in legs if l.action == "sell" and l.contract.option_type == "call")
        long_call = next(l for l in legs if l.action == "buy" and l.contract.option_type == "call")
        short_put = next(l for l in legs if l.action == "sell" and l.contract.option_type == "put")
        long_put = next(l for l in legs if l.action == "buy" and l.contract.option_type == "put")
        width = max(long_call.contract.strike - short_call.contract.strike,
                    short_put.contract.strike - long_put.contract.strike)
        credit = -(net or 0.0)
        return StrategyAnalysis(
            template=template,
            max_loss=-(width - credit) * 100,
            max_gain=credit * 100,
            breakevens=[
                round(short_put.contract.strike - credit, 4),
                round(short_call.contract.strike + credit, 4),
            ],
            pop=None,
            net_debit_credit=net,
            notes=strategy.notes,
        )

    if template == "covered_call":
        short_l = legs[0]
        credit = -(net or 0.0)
        return StrategyAnalysis(
            template=template,
            max_loss=None,
            max_gain=credit * 100,
            breakevens=[],
            pop=None,
            net_debit_credit=net,
            notes=strategy.notes,
        )

    if template == "cash_secured_put":
        short_l = legs[0]
        credit = -(net or 0.0)
        return StrategyAnalysis(
            template=template,
            max_loss=-(short_l.contract.strike - credit) * 100,
            max_gain=credit * 100,
            breakevens=[round(short_l.contract.strike - credit, 4)],
            pop=None,
            net_debit_credit=net,
            notes=strategy.notes,
        )

    return StrategyAnalysis(
        template=template,
        max_loss=None,
        max_gain=None,
        net_debit_credit=net,
        notes=strategy.notes,
    )
