"""NSE ready-made lists: circuit hitters, 52-week highs, bulk/block deals,
results feed, announcements. All best-effort (None/empty on failure).

Vendored from unusual-activity/sources/nse_lists.py (import repointed).
"""

from __future__ import annotations

from momentum.nse_client import fetch_json


def circuit_hitters() -> dict[str, str]:
    """Return {symbol: 'upper'|'lower'} for stocks at their price band today."""
    d = fetch_json("https://www.nseindia.com/api/live-analysis-price-band-hitter")
    out: dict[str, str] = {}
    if not isinstance(d, dict):
        return out
    for side in ("upper", "lower"):
        block = d.get(side) or {}
        rows = block.get("data") if isinstance(block, dict) else block
        for r in rows or []:
            sym = r.get("symbol") if isinstance(r, dict) else None
            if sym:
                out[sym.upper()] = side
    return out


def fiftytwo_week_highs() -> set[str]:
    d = fetch_json("https://www.nseindia.com/api/live-analysis-52Week?index=high")
    out: set[str] = set()
    if not isinstance(d, dict):
        return out
    for key in ("dataLtpGreater20", "dataLtpLess20", "data"):
        for r in d.get(key, []) or []:
            sym = r.get("symbol") if isinstance(r, dict) else None
            if sym:
                out.add(sym.upper())
    return out


def bulk_block_buys() -> dict[str, list[str]]:
    """Return {symbol: [client names]} for BUY-side bulk/block deals today."""
    d = fetch_json("https://www.nseindia.com/api/snapshot-capital-market-largedeal")
    out: dict[str, list[str]] = {}
    if not isinstance(d, dict):
        return out
    for key in ("BULK_DEALS_DATA", "BLOCK_DEALS_DATA"):
        for r in d.get(key, []) or []:
            if str(r.get("buySell", "")).upper().startswith("B") and r.get("symbol"):
                out.setdefault(r["symbol"].upper(), []).append(r.get("clientName", ""))
    return out


def recent_results() -> set[str]:
    """Symbols that filed quarterly results recently (from the results feed)."""
    d = fetch_json("https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly")
    out: set[str] = set()
    rows = d if isinstance(d, list) else (d.get("data", []) if isinstance(d, dict) else [])
    for r in rows or []:
        sym = r.get("symbol") if isinstance(r, dict) else None
        if sym:
            out.add(sym.upper())
    return out


# High-impact announcement keywords (root cause: new information).
_IMPORTANT = (
    "order", "contract", "awarded", "bags", "loa", "letter of award",
    "acquisition", "acquire", "merger", "amalgamation", "stake",
    "fund rais", "fundrais", "qip", "preferential", "warrant", "rights issue",
    "capacity", "commission", "plant", "expansion", "new product", "launch",
    "rating upgrade", "upgraded", "credit rating",
    "bonus", "split", "buyback", "buy back", "dividend", "record date",
)


def important_announcements() -> dict[str, str]:
    """Return {symbol: headline} for high-impact announcements today."""
    d = fetch_json("https://www.nseindia.com/api/corporate-announcements?index=equities")
    out: dict[str, str] = {}
    rows = d if isinstance(d, list) else (d.get("data", []) if isinstance(d, dict) else [])
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").upper()
        text = f"{r.get('desc','')} {r.get('attchmntText','')}".lower()
        if sym and any(k in text for k in _IMPORTANT):
            headline = (r.get("attchmntText") or r.get("desc") or "").strip()
            out[sym] = headline[:90]
    return out


def quote_series_delivery(symbol: str) -> dict:
    """Best-effort NSE quote for a single symbol -> {series, deliv_pct}.

    Gives the momentum card its T2T (BE/BZ) tag + latest delivery % without the
    market-wide bhavcopy. Empty dict on any failure.
    """
    out: dict = {}
    sym = symbol.strip().upper()
    d = fetch_json(f"https://www.nseindia.com/api/quote-equity?symbol={sym}")
    if isinstance(d, dict):
        info = d.get("info") or {}
        meta = d.get("metadata") or {}
        series = meta.get("series") or info.get("series")
        if series:
            out["series"] = str(series).upper()
    t = fetch_json(f"https://www.nseindia.com/api/quote-equity?symbol={sym}&section=trade_info")
    if isinstance(t, dict):
        sec = (t.get("securityWiseDP") or {})
        dp = sec.get("deliveryToTradedQuantity")
        try:
            if dp is not None:
                out["deliv_pct"] = float(dp)
        except (TypeError, ValueError):
            pass
    return out
