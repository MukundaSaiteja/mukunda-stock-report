"""Single-stock A-F momentum analysis for the PDF report.

Reuses the vendored `unusual-activity` engine but feeds it the report bot's
yfinance data (5Y OHLCV + info + Nifty) instead of the market-wide bhavcopy, plus
best-effort single NSE API calls for the D/E/F + circuit/bulk/stake/series signals.
Never raises: any failure returns {"ok": False, ...} so the PDF still builds.
"""

from __future__ import annotations

import concurrent.futures as _cf
import os

from momentum import config, derivatives, fundamentals, nse_lists, sast, scoring, technical
from momentum.bar import Bar


def _history(symbol: str, price_df, series: str, window: int) -> list[dict]:
    """Newest-first [{symbol: Bar}] built from a yfinance OHLCV frame."""
    df = price_df.dropna(subset=["Close"]).tail(window + 1)
    recs = df.reset_index().to_dict("records")
    hist: list[dict] = []
    for i in range(len(recs) - 1, -1, -1):
        r = recs[i]
        try:
            close = float(r["Close"]); high = float(r["High"])
            low = float(r["Low"]); openp = float(r["Open"])
            vol = float(r.get("Volume") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        prev = float(recs[i - 1]["Close"]) if i - 1 >= 0 else openp
        d = r.get("Date") or r.get("index") or ""
        hist.append({symbol: Bar(
            symbol=symbol, date=str(d)[:10], prev_close=prev, open=openp, high=high,
            low=low, close=close, volume=vol, turnover=close * vol / 1e5, trades=0,
            deliv_qty=0.0, deliv_pct=None, series=series,
        )})
    return hist


def _nifty_ret(nifty_df, sessions: int):
    try:
        c = nifty_df["Close"].dropna()
        if len(c) > sessions:
            return (float(c.iloc[-1]) / float(c.iloc[-sessions - 1]) - 1) * 100.0
    except Exception:  # noqa: BLE001
        return None
    return None


def _fetch_market(symbol: str) -> dict:
    """Best-effort NSE feeds, fetched concurrently and time-bounded."""
    market = {"circuits": {}, "highs": set(), "bulk": {}, "results": set(),
              "news": {}, "oi": {}, "stakes": {}, "quote": {}}
    tasks = {
        "circuits": nse_lists.circuit_hitters,
        "highs": nse_lists.fiftytwo_week_highs,
        "bulk": nse_lists.bulk_block_buys,
        "results": nse_lists.recent_results,
        "news": nse_lists.important_announcements,
        "oi": derivatives.oi_data,
        "stakes": sast.sast_acquisitions,
        "quote": lambda: nse_lists.quote_series_delivery(symbol),
    }
    try:
        with _cf.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {k: ex.submit(fn) for k, fn in tasks.items()}
            for k, fu in futs.items():
                try:
                    v = fu.result(timeout=14)
                    if v:
                        market[k] = v
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    return market


def _verify_note(c: scoring.Candidate) -> list[str]:
    notes = []
    for k in ("profit_exceptional", "profit_strong"):
        v = c.signals.get(k)
        if isinstance(v, dict) and not v.get("rev_ok"):
            notes.append("Profit jump not confirmed by revenue - possible base effect.")
            break
    ctx = c.signals.get("_ctx", {})
    if scoring.segment_tag(ctx.get("series")):
        notes.append("Trade-to-Trade scrip: compulsory delivery, tight band, thin liquidity.")
    if "circuit_streak" in c.signals or "circuit_today" in c.signals:
        notes.append("At the price band - entry can be hard; watch for the unlock.")
    notes.append("Confirm on the official filing/disclosure before acting.")
    return notes


def compute(symbol: str, price_df, info: dict | None = None, nifty_df=None) -> dict:
    """Run the A-F analysis for one symbol. Returns a render-ready dict."""
    try:
        symbol = symbol.strip().upper()
        if price_df is None or len(price_df.dropna(subset=["Close"])) < 5:
            return {"ok": False, "error": "insufficient price history"}

        do_nse = os.environ.get("MOMENTUM_NSE", "1") != "0"
        market = _fetch_market(symbol) if do_nse else {}
        quote = market.get("quote", {}) if market else {}
        series = quote.get("series", "EQ")

        hist = _history(symbol, price_df, series, config.HISTORY_DAYS)
        if not hist:
            return {"ok": False, "error": "could not build price history"}
        # latest-day delivery from the NSE quote (best-effort; enables B/I delivery)
        if quote.get("deliv_pct") is not None:
            hist[0][symbol].deliv_pct = quote["deliv_pct"]

        rs_sessions = min(21, len(hist) - 1)
        nifty_ret = _nifty_ret(nifty_df, rs_sessions) if rs_sessions >= 3 else None

        sig = technical.compute(symbol, hist)
        c = scoring.Candidate(symbol=symbol,
                              signals={k: v for k, v in sig.items() if not k.startswith("_")})
        c.signals["_ctx"] = sig.get("_ctx", {})
        scoring.attach_market(c, symbol, market, hist, nifty_ret, rs_sessions)
        c.fundamentals = fundamentals.fetch(symbol)
        scoring.apply_fundamentals(c)
        scoring.finalize(c)

        groups = scoring.grouped_lines(c)
        ctx = c.signals.get("_ctx", {})
        last = ctx.get("close")
        closes_1y = price_df["Close"].dropna().tail(252)
        hi = float(closes_1y.max()) if len(closes_1y) else None
        lo = float(closes_1y.min()) if len(closes_1y) else None
        pos = ((last - lo) / (hi - lo) * 100) if (hi and lo and hi > lo and last) else None

        return {
            "ok": True,
            "symbol": symbol,
            "tier": c.tier,
            "scenario": c.scenario,
            "score": c.score,
            "n_signals": len([k for k in c.signals if k != "_ctx"]),
            "surfaced": scoring.surfaced(c),
            "segment": scoring.segment_tag(series),
            "groups": groups,
            "group_names": scoring._GROUP_NAME,
            "coverage": {g: bool(groups.get(g)) for g in "ABCDEF"},
            "price": last,
            "day_pct": ctx.get("up_pct"),
            "w52_high": hi, "w52_low": lo, "pos_52w": pos,
            "delivery": ctx.get("deliv_pct"),
            "nse_used": bool(market) and any(market.get(k) for k in
                                             ("circuits", "highs", "bulk", "results", "news", "oi", "stakes")),
            "verify": _verify_note(c),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
