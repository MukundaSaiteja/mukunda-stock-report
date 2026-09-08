"""The per-session price bar the technical signals operate on.

Vendored from unusual-activity/sources/bhavcopy.py (the dataclass only). In the
report bot these bars are built from yfinance OHLCV rather than the NSE bhavcopy,
so ``deliv_pct`` is None and ``trades`` is 0 (yfinance exposes neither) — the
delivery/large-trade signals simply don't fire, exactly like the T2T path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Bar:
    symbol: str
    date: str
    prev_close: float
    open: float
    high: float
    low: float
    close: float
    volume: float          # total traded quantity
    turnover: float        # in lakhs (approx: close * volume / 1e5 from yfinance)
    trades: int
    deliv_qty: float
    deliv_pct: float | None
    series: str = "EQ"     # EQ rolling, BE/BZ = Trade-to-Trade (from NSE quote, best-effort)
