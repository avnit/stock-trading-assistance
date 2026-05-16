from argo.llm import _parse_tail


def test_parse_tail_recommendation_and_direction():
    md = """# AAPL — Thesis
...
RECOMMENDATION: BUY
DIRECTION: bullish
"""
    rec, direction = _parse_tail(md)
    assert rec == "BUY"
    assert direction == "bullish"


def test_parse_tail_defaults_to_hold_neutral_when_missing():
    rec, direction = _parse_tail("# AAPL\n\nno tail here")
    assert rec == "HOLD"
    assert direction == "neutral"


def test_parse_tail_handles_mixed_case():
    rec, direction = _parse_tail("recommendation: avoid\ndirection: bearish")
    assert rec == "AVOID"
    assert direction == "bearish"


def test_parse_tail_ignores_unknown_values():
    rec, direction = _parse_tail("RECOMMENDATION: MAYBE\nDIRECTION: sideways")
    assert rec == "HOLD"
    assert direction == "neutral"
