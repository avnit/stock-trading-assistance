from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class IVRank:
    current_iv: float
    min_iv_52w: float
    max_iv_52w: float
    mean_iv_52w: float
    iv_rank: float
    iv_percentile: float


def compute_iv_rank(current_iv: float, historical_iv: list[float]) -> IVRank:
    """Standard definitions:
      IV rank       = (current - 52w_min) / (52w_max - 52w_min)    [scaled 0..100]
      IV percentile = fraction of historical days where IV < current [scaled 0..100]
    """
    if current_iv is None or current_iv != current_iv:
        raise ValueError("current_iv is invalid")
    series = [v for v in historical_iv if v is not None and v == v and v > 0]
    if not series:
        return IVRank(current_iv, current_iv, current_iv, current_iv, 50.0, 50.0)

    lo = min(series)
    hi = max(series)
    mean = sum(series) / len(series)
    rank = 50.0 if hi == lo else (current_iv - lo) / (hi - lo) * 100.0
    pct = (sum(1 for v in series if v < current_iv) / len(series)) * 100.0
    return IVRank(
        current_iv=current_iv,
        min_iv_52w=lo,
        max_iv_52w=hi,
        mean_iv_52w=mean,
        iv_rank=max(0.0, min(100.0, rank)),
        iv_percentile=max(0.0, min(100.0, pct)),
    )


def historical_iv_proxy(ticker: str, days: int = 252) -> list[float]:
    """Cheap proxy: realized vol from rolling 30-day log returns of yfinance closes.

    Real IV history requires a paid feed (Polygon/IVolatility/CBOE DataShop). For
    Phase 1's selector this realized-vol proxy is enough to distinguish IV-rich
    from IV-cheap regimes; we'll swap to actual IV history when a paid feed is
    wired up.
    """
    import numpy as np
    import yfinance as yf

    hist = yf.Ticker(ticker.upper()).history(period="2y", auto_adjust=False)
    if hist.empty or len(hist) < 40:
        return []
    closes = hist["Close"].dropna().to_numpy()
    log_rets = np.diff(np.log(closes))
    window = 30
    if len(log_rets) < window + 1:
        return []
    rolling = np.array(
        [log_rets[i - window : i].std(ddof=1) * np.sqrt(252) for i in range(window, len(log_rets))]
    )
    return [float(v) for v in rolling[-days:] if v == v]
