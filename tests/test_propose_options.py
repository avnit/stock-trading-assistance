from datetime import date, timedelta

import pytest

from argo.options.chains import OptionChain, OptionContract
from argo.propose import ProposalError, propose_options


def _chain(spot=100.0) -> OptionChain:
    expiry = date.today() + timedelta(days=30)
    strikes = list(range(80, 121, 5))
    calls, puts = [], []
    for k in strikes:
        moneyness = spot - k
        call_delta = max(0.05, min(0.95, 0.5 + moneyness / 50.0))
        put_delta = -(1 - call_delta)
        calls.append(
            OptionContract(
                symbol=f"X{k:03d}C", underlying="X", expiry=expiry, strike=float(k),
                option_type="call", bid=max(0.5, moneyness + 1.0) if moneyness > 0 else 1.5,
                ask=(max(0.5, moneyness + 1.0) if moneyness > 0 else 1.5) + 0.1,
                iv=0.30, delta=call_delta,
            )
        )
        puts.append(
            OptionContract(
                symbol=f"X{k:03d}P", underlying="X", expiry=expiry, strike=float(k),
                option_type="put", bid=max(0.5, -moneyness + 1.0) if moneyness < 0 else 1.5,
                ask=(max(0.5, -moneyness + 1.0) if moneyness < 0 else 1.5) + 0.1,
                iv=0.30, delta=put_delta,
            )
        )
    return OptionChain(underlying="X", spot_price=spot, expiry=expiry,
                       risk_free_rate=0.04, calls=calls, puts=puts)


def test_propose_options_selector_chooses_template():
    p = propose_options(
        ticker="X",
        thesis_direction="bullish",
        max_notional_usd=10_000,
        iv_rank=80,
        chain=_chain(),
    )
    assert p.strategy_template == "short_put_vertical"
    assert p.asset_type == "option"
    assert p.side == "multi"
    assert len(p.legs) == 2
    assert p.analysis is not None


def test_propose_options_explicit_template_overrides_selector():
    p = propose_options(
        ticker="X",
        thesis_direction="bullish",
        max_notional_usd=10_000,
        template_key="bull_call_spread",
        iv_rank=80,
        chain=_chain(),
    )
    assert p.strategy_template == "bull_call_spread"


def test_propose_options_rejects_when_max_loss_exceeds_cap():
    with pytest.raises(ProposalError, match="exceeds notional cap"):
        propose_options(
            ticker="X",
            thesis_direction="neutral",
            max_notional_usd=10,
            template_key="iron_condor",
            iv_rank=80,
            chain=_chain(),
            qty=10,
        )


def test_propose_options_unknown_strategy_raises():
    with pytest.raises(ProposalError, match="Unknown strategy"):
        propose_options(
            ticker="X",
            thesis_direction="bullish",
            max_notional_usd=10_000,
            template_key="nonsense",
            iv_rank=50,
            chain=_chain(),
        )


def test_propose_options_legs_have_required_fields():
    p = propose_options(
        ticker="X",
        thesis_direction="neutral",
        max_notional_usd=100_000,
        iv_rank=80,
        chain=_chain(),
    )
    assert p.strategy_template == "iron_condor"
    for leg in p.legs:
        assert leg["symbol"]
        assert leg["action"] in {"buy", "sell"}
        assert leg["option_type"] in {"call", "put"}
        assert "strike" in leg
        assert "expiry" in leg
