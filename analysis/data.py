"""Data fetch for a single NSE stock (yfinance-first, best-effort).

Everything here degrades gracefully: any missing field comes back as ``None`` and
is rendered ``n/a`` downstream, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


def yf_ticker(symbol: str) -> str:
    """NSE symbol -> Yahoo ticker. RELIANCE -> RELIANCE.NS."""
    s = symbol.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO") or s.startswith("^"):
        return s
    return s + ".NS"


@dataclass
class StockData:
    symbol: str
    yticker: str
    as_of: str
    info: dict = field(default_factory=dict)
    price: pd.DataFrame | None = None          # daily OHLCV, adjusted=False
    financials: pd.DataFrame | None = None      # annual income stmt
    balance_sheet: pd.DataFrame | None = None
    cashflow: pd.DataFrame | None = None
    nifty: pd.DataFrame | None = None           # ^NSEI daily close for RS
    ok: bool = False
    error: str = ""


def fetch(symbol: str) -> StockData:
    """Pull everything we need for the report. Never raises."""
    yt = yf_ticker(symbol)
    as_of = datetime.now(timezone.utc).astimezone().strftime("%d-%b-%Y %H:%M %Z")
    data = StockData(symbol=symbol.strip().upper(), yticker=yt, as_of=as_of)
    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        data.error = f"yfinance import failed: {exc}"
        return data

    try:
        tk = yf.Ticker(yt)
        try:
            data.info = tk.get_info() or {}
        except Exception:  # noqa: BLE001
            data.info = {}
        data.price = tk.history(period="5y", interval="1d", auto_adjust=False, actions=True)
        if data.price is None or len(data.price) < 60:
            data.error = f"insufficient price history for {yt} (needs >= 60 days)"
            return data
        # Financial statements (annual). yfinance returns columns = period end dates.
        try:
            data.financials = tk.financials
        except Exception:  # noqa: BLE001
            data.financials = None
        try:
            data.balance_sheet = tk.balance_sheet
        except Exception:  # noqa: BLE001
            data.balance_sheet = None
        try:
            data.cashflow = tk.cashflow
        except Exception:  # noqa: BLE001
            data.cashflow = None
        # Nifty for relative strength.
        try:
            data.nifty = yf.Ticker("^NSEI").history(period="1y", interval="1d")
        except Exception:  # noqa: BLE001
            data.nifty = None
        data.ok = True
    except Exception as exc:  # noqa: BLE001
        data.error = f"fetch failed for {yt}: {exc}"
    return data
