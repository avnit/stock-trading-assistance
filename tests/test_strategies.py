from datetime import date, timedelta

import pytest

from argo.options.chains import OptionChain, OptionContract
from argo.options.strategies import (
    TEMPLATES,
    StrategyError,
    build_bull_call_spread,
    build_cash_secured_put,
    build_covered_call,
    build_iron_condor,
    build_long_call,
    build_long_put,
    build_short_put_vertical,
    build_strategy,
)


def _chain(spot: float = 100.0, strikes=range(80, 121, 5)) -> OptionChain:
    expiry = date.today() + timedelta(days=30)
    calls, puts = [], []
    for k in strikes:
        moneyness = spot - k
        call_delta = max(0.05, min(0.95, 0.5 + moneyness / (spot * 0.5)))
        put_delta = -(1 - call_delta)
        # Crude but monotone: intrinsic + tent-shaped time value peaking ATM.
        time_value = max(0.2, 2.5 - 0.10 * abs(float(k) - spot))
        call_premium = max(0.0, spot - k) + time_value
        put_premium = max(0.0, k - spot) + time_value
        calls.append(
            OptionContract(
                symbol=f"X{k:03d}C", underlying="X", expiry=expiry, strike=float(k),
                option_type="call", bid=call_premium - 0.05, ask=call_premium + 0.05,
                iv=0.30, delta=call_delta, gamma=0.01, theta=-0.02, vega=0.10,
            )
        )
        puts.append(
            OptionContract(
                symbol=f"X{k:03d}P", underlying="X", expiry=expiry, strike=float(k),
                option_type="put", bid=put_premium - 0.05, ask=put_premium + 0.05,
                iv=0.30, delta=put_delta, gamma=0.01, theta=-0.02, vega=0.10,
            )
        )
    return OptionChain(underlying="X", spot_price=spot, expiry=expiry,
                       risk_free_rate=0.04, calls=calls, puts=puts)


def test_templates_dict_has_seven_entries():
    assert set(TEMPLATES) == {
        "long_call", "long_put", "bull_call_spread", "short_put_vertical",
        "iron_condor", "covered_call", "cash_secured_put",
    }


def test_build_long_call_single_leg():
    s = build_long_call(_chain(), target_delta=0.5)
    assert len(s.legs) == 1
    assert s.legs[0].action == "buy"
    assert s.legs[0].contract.option_type == "call"


def test_build_long_put_single_leg():
    s = build_long_put(_chain(), target_delta=0.5)
    assert s.legs[0].action == "buy"
    assert s.legs[0].contract.option_type == "put"


def test_build_bull_call_spread_two_legs_correct_order():
    s = build_bull_call_spread(_chain(), target_delta=0.4, width=5)
    assert len(s.legs) == 2
    buys = [l for l in s.legs if l.action == "buy"]
    sells = [l for l in s.legs if l.action == "sell"]
    assert len(buys) == 1 and len(sells) == 1
    assert buys[0].contract.strike < sells[0].contract.strike  # long ITM-ish, short OTM
    assert s.net_debit_credit is not None and s.net_debit_credit > 0  # debit


def test_build_short_put_vertical_credit():
    s = build_short_put_vertical(_chain(), target_delta=0.3, width=5)
    assert len(s.legs) == 2
    short = next(l for l in s.legs if l.action == "sell")
    long = next(l for l in s.legs if l.action == "buy")
    assert short.contract.strike > long.contract.strike  # short higher, long lower
    assert s.net_debit_credit is not None and s.net_debit_credit < 0  # credit


def test_build_iron_condor_four_legs_call_and_put_wings():
    s = build_iron_condor(_chain(), target_delta=0.20, width=5)
    assert len(s.legs) == 4
    calls = [l for l in s.legs if l.contract.option_type == "call"]
    puts = [l for l in s.legs if l.contract.option_type == "put"]
    assert len(calls) == 2 and len(puts) == 2
    short_call = next(l for l in calls if l.action == "sell")
    long_call = next(l for l in calls if l.action == "buy")
    short_put = next(l for l in puts if l.action == "sell")
    long_put = next(l for l in puts if l.action == "buy")
    assert long_call.contract.strike > short_call.contract.strike
    assert long_put.contract.strike < short_put.contract.strike


def test_build_covered_call_single_short_leg():
    s = build_covered_call(_chain(), target_delta=0.30)
    assert len(s.legs) == 1
    assert s.legs[0].action == "sell"
    assert s.legs[0].contract.option_type == "call"


def test_build_cash_secured_put_single_short_leg():
    s = build_cash_secured_put(_chain(), target_delta=0.30)
    assert len(s.legs) == 1
    assert s.legs[0].action == "sell"
    assert s.legs[0].contract.option_type == "put"


def test_build_strategy_dispatcher():
    s = build_strategy("iron_condor", _chain(), target_delta=0.2, width=5)
    assert s.template == "iron_condor"
    assert len(s.legs) == 4


def test_build_strategy_unknown_key():
    with pytest.raises(StrategyError):
        build_strategy("nonsense", _chain())


def test_strategy_falls_back_to_nearest_strike_when_no_greeks():
    expiry = date.today() + timedelta(days=30)
    calls = [
        OptionContract(symbol="X100C", underlying="X", expiry=expiry, strike=100.0,
                       option_type="call", bid=2.0, ask=2.10),
        OptionContract(symbol="X105C", underlying="X", expiry=expiry, strike=105.0,
                       option_type="call", bid=1.0, ask=1.10),
    ]
    chain = OptionChain(underlying="X", spot_price=100.0, expiry=expiry,
                        risk_free_rate=0.04, calls=calls, puts=[])
    s = build_long_call(chain, target_delta=0.50)
    assert s.legs[0].contract.strike == 100.0  # nearest to spot
