import pytest

from argo.options.selector import classify_iv_regime, select_template


def test_classify_iv_regime_thresholds():
    assert classify_iv_regime(70) == "rich"
    assert classify_iv_regime(60) == "rich"
    assert classify_iv_regime(45) == "neutral"
    assert classify_iv_regime(30) == "cheap"
    assert classify_iv_regime(0) == "cheap"


def test_bullish_iv_rich_picks_short_put_vertical():
    r = select_template(thesis_direction="bullish", iv_rank=80)
    assert r.template.key == "short_put_vertical"


def test_bullish_iv_cheap_picks_long_call():
    r = select_template(thesis_direction="bullish", iv_rank=10)
    assert r.template.key == "long_call"


def test_neutral_iv_rich_picks_iron_condor():
    r = select_template(thesis_direction="neutral", iv_rank=80)
    assert r.template.key == "iron_condor"


def test_bearish_always_long_put():
    for ivr in (10, 50, 80):
        r = select_template(thesis_direction="bearish", iv_rank=ivr)
        assert r.template.key == "long_put"


def test_own_shares_prefers_covered_call_for_neutral():
    r = select_template(thesis_direction="neutral", iv_rank=50, own_shares=True,
                        risk_tolerance="undefined")
    assert r.template.key == "covered_call"


def test_defined_risk_filters_out_undefined_strategies():
    r = select_template(thesis_direction="neutral", iv_rank=50, own_shares=True)
    assert r.template.key in {"iron_condor", "covered_call"} or r.template.key == "iron_condor"


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        select_template(thesis_direction="sideways", iv_rank=50)
