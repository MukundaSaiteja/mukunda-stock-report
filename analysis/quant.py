"""Quant factors: momentum, relative strength, CAGR, drawdown."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _r(x, d=1):
    try:
        v = float(x)
        return None if (np.isnan(v) or np.isinf(v)) else round(v, d)
    except (TypeError, ValueError):
        return None


def compute(price: pd.DataFrame, nifty: pd.DataFrame | None) -> dict:
    c = price["Close"].dropna()
    out: dict = {}
    px = float(c.iloc[-1])

    # 12-1 momentum: 12m return excluding the last month (~21 sessions)
    if len(c) > 273:
        p12 = float(c.iloc[-273])
        p1 = float(c.iloc[-21])
        out["mom_12_1_pct"] = _r((p1 / p12 - 1) * 100)

    # Trailing returns
    for label, n in [("ret_1m_pct", 21), ("ret_3m_pct", 63), ("ret_6m_pct", 126), ("ret_1y_pct", 252)]:
        if len(c) > n:
            out[label] = _r((px / float(c.iloc[-n - 1]) - 1) * 100)

    # 5Y CAGR
    if len(c) > 252:
        yrs = len(c) / 252.0
        out["cagr_pct"] = _r(((px / float(c.iloc[0])) ** (1 / yrs) - 1) * 100)

    # Max drawdown over the series
    roll_max = c.cummax()
    dd = (c / roll_max - 1) * 100
    out["max_drawdown_pct"] = _r(dd.min())

    # Relative strength vs Nifty (1y)
    if nifty is not None and len(nifty) > 200:
        nc = nifty["Close"].dropna()
        n1y = float(nc.iloc[-1]) / float(nc.iloc[0]) - 1
        s1y = px / float(c.iloc[-min(len(c), len(nc))]) - 1
        out["rs_vs_nifty_pct"] = _r((s1y - n1y) * 100)
        out["rs_state"] = "outperforming" if (out["rs_vs_nifty_pct"] or 0) > 0 else "lagging"
    return out
