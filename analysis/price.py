"""Live price for one NSE symbol: NSE quote first, yfinance fallback.

Best-effort: returns None on total failure. NSE gives a near-real-time last price
but blocks some datacenter IPs, so yfinance (delayed ~15m) is the safety net.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.parse
import urllib.request

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _nse_quote(symbol: str) -> float | None:
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def _open(url):
        return op.open(urllib.request.Request(url, headers=_HEADERS), timeout=15)

    try:
        try:
            _open("https://www.nseindia.com/").read(1)
        except Exception:  # noqa: BLE001
            pass
        url = f"https://www.nseindia.com/api/quote-equity?symbol={urllib.parse.quote(symbol)}"
        data = json.loads(_open(url).read().decode("utf-8", "ignore"))
        price = (data.get("priceInfo") or {}).get("lastPrice")
        return float(price) if price is not None else None
    except Exception:  # noqa: BLE001
        return None


def _yf_price(symbol: str) -> float | None:
    try:
        import yfinance as yf

        t = symbol if symbol.endswith((".NS", ".BO")) else symbol + ".NS"
        h = yf.Ticker(t).history(period="1d", interval="5m")
        if h is not None and len(h):
            return float(h["Close"].iloc[-1])
    except Exception:  # noqa: BLE001
        return None
    return None


def live_price(symbol: str) -> tuple[float | None, str]:
    """Return (price, source). source in {'nse','yfinance','none'}."""
    sym = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    p = _nse_quote(sym)
    if p is not None:
        return p, "nse"
    p = _yf_price(sym)
    if p is not None:
        return p, "yfinance"
    return None, "none"
