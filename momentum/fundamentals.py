"""Group A/C fundamentals from yfinance (best-effort): quarterly profit & revenue
YoY, forward vs trailing PE, market cap.

Vendored from unusual-activity/fundamentals.py (import repointed). Missing data
-> None (rendered 'n/a' downstream).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fundamentals:
    symbol: str
    mcap_cr: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    eps: float | None = None
    profit_yoy_pct: float | None = None
    revenue_yoy_pct: float | None = None
    prev_profit_yoy_pct: float | None = None
    consecutive_strong: bool = False
    latest_profit_cr: float | None = None
    turnaround: bool = False
    ok: bool = False


def _pct(new, old):
    try:
        if old is None or new is None or old == 0:
            return None
        return (new - old) / abs(old) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def fetch(symbol: str) -> Fundamentals:
    f = Fundamentals(symbol=symbol)
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol + ".NS")
        info = tk.get_info() or {}
    except Exception:  # noqa: BLE001
        return f

    mc = info.get("marketCap")
    f.mcap_cr = round(mc / 1e7, 0) if mc else None
    f.trailing_pe = info.get("trailingPE")
    f.forward_pe = info.get("forwardPE")
    f.eps = info.get("trailingEps")

    try:
        q = tk.quarterly_income_stmt
        if q is not None and q.shape[1] >= 5:
            def row(*names):
                idx = {str(i).lower(): i for i in q.index}
                for n in names:
                    for lo, orig in idx.items():
                        if n in lo:
                            return q.loc[orig]
                return None
            ni = row("net income")
            rev = row("total revenue", "operating revenue", "revenue")
            if ni is not None and len(ni) >= 5:
                latest, yr_ago = float(ni.iloc[0]), float(ni.iloc[4])
                f.latest_profit_cr = round(latest / 1e7, 0)
                f.profit_yoy_pct = _pct(latest, yr_ago)
                f.turnaround = (yr_ago < 0 <= latest)
                if len(ni) >= 6:
                    f.prev_profit_yoy_pct = _pct(float(ni.iloc[1]), float(ni.iloc[5]))
                    from momentum.config import PROFIT_STRONG
                    f.consecutive_strong = (
                        (f.profit_yoy_pct or 0) >= PROFIT_STRONG
                        and (f.prev_profit_yoy_pct or 0) >= PROFIT_STRONG
                    )
            if rev is not None and len(rev) >= 5:
                f.revenue_yoy_pct = _pct(float(rev.iloc[0]), float(rev.iloc[4]))
    except Exception:  # noqa: BLE001
        pass

    f.ok = True
    return f


def nifty_return_pct(sessions: int = 21) -> float | None:
    """Nifty 50 return over the last ``sessions`` trading days (best-effort)."""
    try:
        import yfinance as yf
        h = yf.Ticker("^NSEI").history(period="3mo", interval="1d")
        c = h["Close"].dropna()
        if len(c) > sessions:
            return (float(c.iloc[-1]) / float(c.iloc[-sessions - 1]) - 1) * 100.0
    except Exception:  # noqa: BLE001
        return None
    return None
