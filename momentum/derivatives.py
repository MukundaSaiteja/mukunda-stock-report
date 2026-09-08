"""Group E: F&O open-interest positioning (long buildup / short covering / spurt).

Vendored from unusual-activity/sources/derivatives.py (import repointed).
"""

from __future__ import annotations

from momentum.nse_client import fetch_json


def oi_data() -> dict[str, dict]:
    """Return {symbol: {latestOI, prevOI, changeInOI, avgInOI, volume}}."""
    d = fetch_json("https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings")
    out: dict[str, dict] = {}
    rows = d.get("data", []) if isinstance(d, dict) else []
    for r in rows or []:
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue
        out[sym] = {
            "latestOI": r.get("latestOI"),
            "prevOI": r.get("prevOI"),
            "changeInOI": r.get("changeInOI"),
            "avgInOI": r.get("avgInOI"),
            "volume": r.get("volume"),
        }
    return out


def classify(symbol: str, price_up: bool, oi: dict[str, dict]) -> tuple[str, float] | None:
    """Return (label, oi_change_pct) or None. label in {long_buildup, short_covering}."""
    row = oi.get(symbol.upper())
    if not row:
        return None
    try:
        change = float(row.get("changeInOI"))
        prev = float(row.get("prevOI"))
    except (TypeError, ValueError):
        return None
    if prev <= 0:
        return None
    pct = change / prev * 100.0
    if price_up and change > 0:
        return "long_buildup", pct
    if price_up and change < 0:
        return "short_covering", pct
    return None


def oi_spurt(symbol: str, oi: dict[str, dict], min_mult: float = 2.0) -> float | None:
    """E3: unusual OI change vs its average (|changeInOI| >= min_mult * avgInOI)."""
    row = oi.get(symbol.upper())
    if not row:
        return None
    try:
        change = abs(float(row.get("changeInOI")))
        avg = abs(float(row.get("avgInOI")))
    except (TypeError, ValueError):
        return None
    if avg > 0 and change >= min_mult * avg:
        mult = change / avg
        # Guard against a near-zero avgInOI in the feed producing an absurd
        # multiple (e.g. 5000x on a marquee name) - that's data noise, not signal.
        return mult if mult <= 50 else None
    return None
