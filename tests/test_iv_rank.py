import pytest

from argo.options.iv_rank import compute_iv_rank


def test_iv_rank_basic():
    r = compute_iv_rank(0.30, [0.10, 0.20, 0.30, 0.40, 0.50])
    assert r.min_iv_52w == 0.10
    assert r.max_iv_52w == 0.50
    assert r.iv_rank == pytest.approx(50.0)
    assert r.iv_percentile == pytest.approx(40.0)  # 2 of 5 below current


def test_iv_rank_at_max():
    r = compute_iv_rank(0.80, [0.20, 0.40, 0.80])
    assert r.iv_rank == pytest.approx(100.0)
    assert r.iv_percentile == pytest.approx(66.67, rel=0.01)


def test_iv_rank_at_min():
    r = compute_iv_rank(0.10, [0.10, 0.30, 0.50])
    assert r.iv_rank == pytest.approx(0.0)


def test_iv_rank_empty_history_returns_neutral():
    r = compute_iv_rank(0.35, [])
    assert r.iv_rank == 50.0
    assert r.iv_percentile == 50.0


def test_iv_rank_handles_flat_history():
    r = compute_iv_rank(0.30, [0.30, 0.30, 0.30])
    assert r.iv_rank == 50.0  # hi==lo fallback


def test_iv_rank_invalid_current_raises():
    with pytest.raises(ValueError):
        compute_iv_rank(float("nan"), [0.2, 0.3])
