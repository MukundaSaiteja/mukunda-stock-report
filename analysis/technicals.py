"""Technical indicators + support/resistance for one stock.

Computes the full suite (50/200-DMA, RSI, MACD, ADX, Bollinger, ATR, Stochastic,
volume, 52W position) and real support/resistance: classic pivots (S1/S2/S3,
R1/R2/R3) from the prior period, plus recent swing highs/lows and 52W levels.
All best-effort; missing values -> None.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn)


def _adx(h, l, c, n: int = 14):
    up = h.diff()
    dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n).mean()
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1 / n).mean() / atr
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1 / n).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1 / n).mean(), pdi, mdi


def _r(x, d=2):
    try:
        v = float(x)
        return None if (np.isnan(v) or np.isinf(v)) else round(v, d)
    except (TypeError, ValueError):
        return None


def compute(price: pd.DataFrame) -> dict:
    """Return a dict of indicators + S/R levels for the latest bar."""
    h = price.dropna(subset=["Close"]).copy()
    c, hi, lo, v = h["Close"], h["High"], h["Low"], h["Volume"]
    px = float(c.iloc[-1])
    out: dict = {"last_close": _r(px)}

    # Moving averages
    s20, s50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
    s200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else np.nan
    out["sma20"], out["sma50"] = _r(s20, 1), _r(s50, 1)
    out["sma200"] = _r(s200, 1)
    out["px_vs_50dma_pct"] = _r((px / s50 - 1) * 100, 1) if s50 else None
    out["px_vs_200dma_pct"] = _r((px / s200 - 1) * 100, 1) if s200 and not np.isnan(s200) else None
    out["ma_cross"] = None
    if s200 and not np.isnan(s200):
        out["ma_cross"] = "golden (50>200)" if s50 > s200 else "death (50<200)"

    # RSI / MACD
    out["rsi14"] = _r(_rsi(c).iloc[-1], 1)
    e12, e26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = e12 - e26
    sig = macd.ewm(span=9).mean()
    out["macd"] = _r(macd.iloc[-1])
    out["macd_signal"] = _r(sig.iloc[-1])
    out["macd_hist"] = _r((macd - sig).iloc[-1])
    out["macd_state"] = "bullish" if (out["macd_hist"] or 0) > 0 else "bearish"

    # Bollinger(20,2)
    mb, sd = c.rolling(20).mean(), c.rolling(20).std()
    ub, lb = mb + 2 * sd, mb - 2 * sd
    if ub.iloc[-1] != lb.iloc[-1]:
        out["boll_pctB"] = _r((px - lb.iloc[-1]) / (ub.iloc[-1] - lb.iloc[-1]) * 100, 1)
    out["boll_upper"], out["boll_lower"] = _r(ub.iloc[-1], 1), _r(lb.iloc[-1], 1)

    # ATR(14)
    tr = pd.concat([hi - lo, (hi - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    out["atr14"] = _r(atr, 1)
    out["atr_pct"] = _r(atr / px * 100, 1) if px else None

    # ADX(14)
    adx, pdi, mdi = _adx(hi, lo, c)
    out["adx14"] = _r(adx.iloc[-1], 1)
    out["di_state"] = "+DI>-DI (up)" if pdi.iloc[-1] > mdi.iloc[-1] else "-DI>+DI (down)"

    # Stochastic(14,3)
    ll = lo.rolling(14).min()
    hh = hi.rolling(14).max()
    k = 100 * (c - ll) / (hh - ll)
    out["stoch_k"] = _r(k.iloc[-1], 1)
    out["stoch_d"] = _r(k.rolling(3).mean().iloc[-1], 1)

    # Volume vs 20d avg
    vavg = v.rolling(20).mean().iloc[-1]
    out["vol_vs_avg_pct"] = _r((v.iloc[-1] / vavg - 1) * 100, 0) if vavg else None

    # 52-week position
    w52 = c.tail(252)
    hi52, lo52 = float(w52.max()), float(w52.min())
    out["high_52w"], out["low_52w"] = _r(hi52, 1), _r(lo52, 1)
    if hi52 != lo52:
        out["pos_52w_pct"] = _r((px - lo52) / (hi52 - lo52) * 100, 0)

    # Market structure (last ~40 bars higher-highs/higher-lows heuristic)
    recent = c.tail(40)
    out["structure"] = "uptrend (HH/HL)" if recent.iloc[-1] > recent.iloc[0] and s50 > (s200 or s50) else "range/down"

    out["support_resistance"] = _support_resistance(h, px, hi52, lo52)
    return out


def _support_resistance(h: pd.DataFrame, px: float, hi52: float, lo52: float) -> dict:
    """Classic pivots from the prior ~21 sessions + swings + 52W levels."""
    prev = h.tail(21)
    P = float((prev["High"].max() + prev["Low"].min() + prev["Close"].iloc[-1]) / 3)
    hh, ll = float(prev["High"].max()), float(prev["Low"].min())
    r1 = 2 * P - ll
    s1 = 2 * P - hh
    r2 = P + (hh - ll)
    s2 = P - (hh - ll)
    r3 = hh + 2 * (P - ll)
    s3 = ll - 2 * (hh - P)

    # Recent swing high/low over ~60 bars (local extremes)
    win = h.tail(60)
    swing_hi = float(win["High"].max())
    swing_lo = float(win["Low"].min())

    return {
        "pivot": _r(P, 1),
        "R1": _r(r1, 1), "R2": _r(r2, 1), "R3": _r(r3, 1),
        "S1": _r(s1, 1), "S2": _r(s2, 1), "S3": _r(s3, 1),
        "swing_high_60d": _r(swing_hi, 1),
        "swing_low_60d": _r(swing_lo, 1),
        "high_52w": _r(hi52, 1),
        "low_52w": _r(lo52, 1),
        "nearest_support": _r(max([x for x in [s1, s2, s3, swing_lo, lo52] if x < px], default=None), 1),
        "nearest_resistance": _r(min([x for x in [r1, r2, r3, swing_hi, hi52] if x > px], default=None), 1),
    }
