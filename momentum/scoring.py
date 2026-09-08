"""Scoring, tiering, scenario labelling + A-F grouping and PLAIN-TEXT rendering.

Vendored/condensed from unusual-activity/scan.py + digest.py. The renderers here
emit plain ASCII-ish text (no emoji) because the PDF core font can't draw emoji.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from momentum import config
from momentum import derivatives


@dataclass
class Candidate:
    symbol: str
    signals: dict = field(default_factory=dict)
    fundamentals: object | None = None
    score: int = 0
    tier: str = ""
    scenario: str = ""


# Signal weights (footprints + causes). Higher = stronger momentum explainer.
_WEIGHTS = {
    "circuit_streak": 3, "delivery_spike": 2, "volume_spike": 2, "turnover_surge": 1,
    "big_move": 1, "window_high": 1, "breakout": 2, "quiet_accumulation": 3,
    "large_trades": 2, "down_day_accum": 3, "multiday_advance": 2,
    "new_52w_high": 2, "bulk_buy": 3, "circuit_today": 2,
    "long_buildup": 3, "short_covering": 2, "oi_spurt": 1,
    "sast_stake": 3, "news": 2, "relative_strength": 2, "consecutive_growth": 2,
    "profit_exceptional": 3, "profit_strong": 2, "turnaround": 2, "results_filed": 1,
    "pe_rerating": 1, "forward_growth": 1,
}

# Which A-F group each signal belongs to (root-cause framework).
_GROUP = {
    "A": ("profit_exceptional", "profit_strong", "turnaround", "consecutive_growth", "results_filed"),
    "B": ("circuit_streak", "circuit_today", "delivery_spike", "volume_spike", "turnover_surge",
          "big_move", "window_high", "new_52w_high", "breakout", "multiday_advance",
          "relative_strength", "large_trades", "quiet_accumulation", "down_day_accum"),
    "C": ("forward_growth", "pe_rerating"),
    "D": ("news",),
    "E": ("long_buildup", "short_covering", "oi_spurt"),
    "F": ("sast_stake", "bulk_buy"),
}
_GROUP_NAME = {"A": "Results", "B": "Accumulation", "C": "Valuation",
               "D": "News", "E": "Derivatives (OI)", "F": "Flows/stake"}


def stock_return_pct(symbol, history, sessions: int) -> float | None:
    closes = []
    for day in history:
        b = day.get(symbol)
        if b is not None:
            closes.append(b.close)
    n = min(sessions, len(closes) - 1)
    if n >= 3 and closes[n] > 0:
        return (closes[0] / closes[n] - 1) * 100.0
    return None


def attach_market(c: Candidate, sym: str, market, history, nifty_ret=None, rs_sessions=0) -> None:
    """Attach external (D/E/F + circuit-today/52w/bulk) signals, best-effort."""
    ctx = c.signals.get("_ctx", {})
    circuits = market.get("circuits", {})
    if sym in circuits and circuits[sym] == "upper" and "circuit_streak" not in c.signals:
        c.signals["circuit_today"] = True
    if sym in market.get("highs", set()):
        c.signals["new_52w_high"] = True
    if sym in market.get("bulk", {}):
        c.signals["bulk_buy"] = market["bulk"][sym][:2]
    if sym in market.get("results", set()):
        c.signals["results_filed"] = True
    if sym in market.get("news", {}):
        c.signals["news"] = market["news"][sym]
    if sym in market.get("stakes", {}):
        c.signals["sast_stake"] = market["stakes"][sym]

    if nifty_ret is not None and ctx.get("is_up"):
        sret = stock_return_pct(sym, history, rs_sessions)
        if sret is not None and sret - nifty_ret >= 5.0:
            c.signals["relative_strength"] = {"stock": round(sret, 1), "nifty": round(nifty_ret, 1)}

    oi = market.get("oi", {})
    oic = derivatives.classify(sym, bool(ctx.get("is_up")), oi)
    if oic:
        c.signals[oic[0]] = round(oic[1], 0)
    spurt = derivatives.oi_spurt(sym, oi)
    if spurt is not None and oic is None:
        c.signals["oi_spurt"] = round(spurt, 1)


def apply_fundamentals(c: Candidate) -> None:
    f = c.fundamentals
    if not f or not getattr(f, "ok", False):
        return
    if f.turnaround and (f.latest_profit_cr or 0) >= config.PROFIT_FLOOR_CR:
        c.signals["turnaround"] = True
    elif f.profit_yoy_pct is not None and (f.latest_profit_cr or 0) >= config.PROFIT_FLOOR_CR:
        rev_ok = (f.revenue_yoy_pct or 0) >= config.REVENUE_CONFIRM
        if f.profit_yoy_pct >= config.PROFIT_EXCEPTIONAL:
            c.signals["profit_exceptional"] = {"pct": round(f.profit_yoy_pct), "rev_ok": rev_ok}
        elif f.profit_yoy_pct >= config.PROFIT_STRONG:
            c.signals["profit_strong"] = {"pct": round(f.profit_yoy_pct), "rev_ok": rev_ok}
    if f.consecutive_strong:
        c.signals["consecutive_growth"] = {"latest": round(f.profit_yoy_pct or 0),
                                           "prev": round(f.prev_profit_yoy_pct or 0)}
    if f.forward_pe and f.trailing_pe and f.forward_pe <= 0.7 * f.trailing_pe:
        c.signals["forward_growth"] = {"fwd": round(f.forward_pe, 1), "ttm": round(f.trailing_pe, 1)}


def finalize(c: Candidate) -> None:
    c.score = sum(_WEIGHTS.get(k, 0) for k in c.signals if k != "_ctx")
    n = len([k for k in c.signals if k != "_ctx"])
    c.tier = "HIGH" if (c.score >= 6 or n >= 3) else "MEDIUM"
    has_result = any(k in c.signals for k in ("profit_exceptional", "profit_strong", "turnaround", "results_filed"))
    has_footprint = any(k in c.signals for k in (
        "circuit_streak", "circuit_today", "delivery_spike", "volume_spike",
        "quiet_accumulation", "long_buildup", "short_covering", "bulk_buy",
        "relative_strength", "down_day_accum", "multiday_advance", "oi_spurt"))
    has_forced = any(k in c.signals for k in ("sast_stake", "long_buildup", "short_covering", "bulk_buy"))
    if has_result and has_footprint:
        c.scenario = "results + accumulation"
    elif has_forced and not has_result:
        c.scenario = "large/forced buying"
    elif has_footprint and not has_result:
        c.scenario = "accumulation, no public news"
    elif has_result:
        c.scenario = "results-driven"
    else:
        c.scenario = "watch"


def surfaced(c: Candidate) -> bool:
    n = len([k for k in c.signals if k != "_ctx"])
    streak = c.signals.get("circuit_streak", 0)
    if isinstance(streak, int) and streak >= config.CIRCUIT_STREAK_STRONG:
        return True
    if "profit_exceptional" in c.signals or "sast_stake" in c.signals:
        return True
    return n >= config.MIN_SIGNALS


def segment_tag(series: str | None) -> str:
    s = (series or "").upper()
    if s == "BE":
        return "T2T (BE)"
    if s == "BZ":
        return "T2T-BZ (surveillance)"
    return ""


def _line(key, v) -> str | None:
    """Plain-text label for one signal (no emoji; PDF-safe)."""
    if key == "circuit_streak":
        return f"Upper circuit: {v} day(s)"
    if key == "circuit_today":
        return "Upper circuit today"
    if key == "delivery_spike":
        m = f" ({v['mult']:.1f}x avg)" if v.get("mult") else ""
        return f"Delivery {v['pct']:.0f}%{m}"
    if key == "quiet_accumulation":
        return f"Quiet accumulation (delivery {v['pct']:.0f}%, price flat)"
    if key == "down_day_accum":
        return f"Accumulation on a down day (delivery {v['pct']:.0f}%, {v['down']}%)"
    if key == "multiday_advance":
        return f"{v['days']}-day advance on volume"
    if key == "volume_spike":
        return f"Volume {v['mult']:.1f}x avg"
    if key == "turnover_surge":
        return f"Turnover {v['mult']:.1f}x avg"
    if key == "large_trades":
        return f"Large avg trade size {v['mult']:.1f}x"
    if key == "breakout":
        return f"Range breakout above Rs {v['above']:.0f}"
    if key in ("new_52w_high", "window_high"):
        return "New 52-week / range high"
    if key == "big_move":
        return f"Up {v['pct']:.1f}% today"
    if key == "long_buildup":
        return f"Long buildup (OI +{v:.0f}%)"
    if key == "short_covering":
        return f"Short covering (OI {v:.0f}%)"
    if key == "oi_spurt":
        return f"OI spurt ({v:.1f}x avg)"
    if key == "bulk_buy":
        who = ", ".join(x for x in v if x)[:40]
        return f"Bulk BUY{': ' + who if who else ''}"
    if key == "relative_strength":
        return f"RS +{v['stock'] - v['nifty']:.0f}% vs Nifty"
    if key == "sast_stake":
        return f"SAST stake buy: {v}"
    if key == "consecutive_growth":
        return f"Two strong quarters (+{v['latest']}%, +{v['prev']}%)"
    if key == "profit_exceptional" or key == "profit_strong":
        tag = "" if v.get("rev_ok") else " (revenue flat - verify)"
        return f"Profit +{v['pct']}% YoY{tag}"
    if key == "turnaround":
        return "Turnaround (loss -> profit)"
    if key == "results_filed":
        return "Just reported results"
    if key == "forward_growth":
        return f"Fwd PE {v['fwd']} << TTM {v['ttm']} (growth priced in)"
    if key == "news":
        return f"News: {v}"
    return None


def grouped_lines(c: Candidate) -> dict:
    """{group_letter: [text lines]} across A-F, plus a coverage summary."""
    out = {}
    for g, keys in _GROUP.items():
        lines, seen = [], set()
        for k in keys:
            if k in c.signals and k != "_ctx":
                s = _line(k, c.signals[k])
                if s and s not in seen:   # dedupe (e.g. window_high + new_52w_high)
                    seen.add(s)
                    lines.append(s)
        out[g] = lines
    return out
