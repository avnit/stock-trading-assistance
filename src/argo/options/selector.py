from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from argo.options.strategies import TEMPLATES, StrategyTemplate

Direction = Literal["bullish", "bearish", "neutral"]
IVRegime = Literal["cheap", "neutral", "rich"]
Risk = Literal["defined", "undefined"]


def classify_iv_regime(iv_rank: float) -> IVRegime:
    if iv_rank >= 60.0:
        return "rich"
    if iv_rank <= 30.0:
        return "cheap"
    return "neutral"


@dataclass
class SelectorResult:
    template: StrategyTemplate
    rationale: str
    alternates: list[str]


def select_template(
    *,
    thesis_direction: str,
    iv_rank: float,
    risk_tolerance: Risk = "defined",
    own_shares: bool = False,
) -> SelectorResult:
    """Deterministic template picker.

    Inputs: thesis direction (bullish/bearish/neutral), iv_rank 0..100, risk_tolerance
    (defined-risk only by default), whether the user already owns 100 shares.

    Returns the best-fit template plus a list of reasonable alternates.
    """
    direction = thesis_direction.lower()
    if direction not in {"bullish", "bearish", "neutral"}:
        raise ValueError(f"Invalid thesis_direction: {thesis_direction}")
    regime = classify_iv_regime(iv_rank)

    table: dict[tuple[Direction, IVRegime], list[str]] = {
        ("bullish", "rich"): ["short_put_vertical", "cash_secured_put", "bull_call_spread"],
        ("bullish", "neutral"): ["bull_call_spread", "short_put_vertical", "long_call"],
        ("bullish", "cheap"): ["long_call", "bull_call_spread"],
        ("bearish", "rich"): ["long_put"],
        ("bearish", "neutral"): ["long_put"],
        ("bearish", "cheap"): ["long_put"],
        ("neutral", "rich"): ["iron_condor", "covered_call"],
        ("neutral", "neutral"): ["covered_call", "iron_condor"],
        ("neutral", "cheap"): ["covered_call"],
    }
    candidates = table[(direction, regime)]  # type: ignore[index]

    if own_shares and "covered_call" not in candidates:
        candidates = ["covered_call", *candidates]
    if not own_shares:
        candidates = [c for c in candidates if c != "covered_call"] or candidates

    if risk_tolerance == "defined":
        candidates = [c for c in candidates if c in {
            "long_call", "long_put", "bull_call_spread",
            "short_put_vertical", "iron_condor",
        }] or ["long_call" if direction == "bullish" else "long_put"]

    chosen_key = candidates[0]
    chosen = TEMPLATES[chosen_key]
    rationale = (
        f"thesis={direction}, IV rank={iv_rank:.1f} (regime={regime}), "
        f"risk={risk_tolerance}, own_shares={own_shares} -> {chosen_key}. "
        f"Strategy is {chosen.description.lower()}."
    )
    return SelectorResult(template=chosen, rationale=rationale, alternates=candidates[1:])
