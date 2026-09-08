"""Per-stock signal computation from price history (Groups B, H, I + circuit).

Vendored verbatim from unusual-activity/signals/technical.py (only the imports
are repointed at the momentum package). Pure functions -> unit-testable offline.
"""

from __future__ import annotations

from statistics import mean

from momentum.config import (
    AVG_WINDOW, BIG_MOVE_PCT, DELIV_MULT, DELIV_PCT_MIN, TURNOVER_MULT, VOL_MULT,
)
from momentum.bar import Bar


def _series(symbol: str, history: list[dict[str, Bar]], field: str) -> list[float]:
    vals = []
    for day in history:
        b = day.get(symbol)
        if b is not None:
            v = getattr(b, field, None)
            if v is not None:
                vals.append(float(v))
    return vals


def circuit_streak(symbol: str, history: list[dict[str, Bar]]) -> int:
    """Consecutive days (from latest, backwards) the stock closed at/near upper
    circuit. Proxy: close == high and up strongly and locked (close ~ high ~ low
    band). Newest-first history."""
    streak = 0
    for day in history:
        b = day.get(symbol)
        if b is None or b.prev_close <= 0:
            break
        up = (b.close - b.prev_close) / b.prev_close * 100.0
        locked = b.close >= b.high - 1e-6 and up > 1.5 and (b.high - b.low) / b.close < 0.02
        if locked:
            streak += 1
        else:
            break
    return streak


def compute(symbol: str, history: list[dict[str, Bar]]) -> dict:
    """Return {signal_code: detail} for one stock. Empty if no data."""
    if not history or symbol not in history[0]:
        return {}
    b = history[0][symbol]
    out: dict = {}

    prior = history[1:1 + AVG_WINDOW]
    vol_hist = _series(symbol, prior, "volume")
    turn_hist = _series(symbol, prior, "turnover")
    deliv_hist = [x for x in _series(symbol, prior, "deliv_pct")]

    up_pct = (b.close - b.prev_close) / b.prev_close * 100.0 if b.prev_close else 0.0
    is_up = up_pct > 0

    # B1 circuit streak
    streak = circuit_streak(symbol, history)
    if streak >= 1:
        out["circuit_streak"] = streak

    # B2 delivery spike
    if b.deliv_pct is not None:
        avg_dlv = mean(deliv_hist) if deliv_hist else None
        if b.deliv_pct >= DELIV_PCT_MIN and (avg_dlv is None or b.deliv_pct >= DELIV_MULT * avg_dlv):
            out["delivery_spike"] = {"pct": b.deliv_pct, "mult": (b.deliv_pct / avg_dlv) if avg_dlv else None}

    # B3 volume spike
    if vol_hist and is_up:
        avg_v = mean(vol_hist)
        if avg_v > 0 and b.volume >= VOL_MULT * avg_v:
            out["volume_spike"] = {"mult": b.volume / avg_v}

    # B4 turnover surge
    if turn_hist:
        avg_t = mean(turn_hist)
        if avg_t > 0 and b.turnover >= TURNOVER_MULT * avg_t:
            out["turnover_surge"] = {"mult": b.turnover / avg_t}

    # B / general big move
    if up_pct >= BIG_MOVE_PCT:
        out["big_move"] = {"pct": up_pct}

    # H2 all-time / range high (within loaded window)
    highs = _series(symbol, history, "high")
    if highs and b.high >= max(highs) - 1e-6:
        out["window_high"] = {"days": len(highs)}

    # H1 consolidation breakout: today's range-expansion up-close above prior N highs
    prior_highs = _series(symbol, prior, "high")
    if prior_highs and is_up and b.close > max(prior_highs):
        out["breakout"] = {"above": max(prior_highs)}

    # I1 quiet accumulation: high delivery while price ~flat (last ~5 sessions tight)
    recent_close = _series(symbol, history[:6], "close")
    if b.deliv_pct is not None and b.deliv_pct >= DELIV_PCT_MIN and len(recent_close) >= 5:
        rng = (max(recent_close) - min(recent_close)) / b.close * 100.0
        if rng <= 4.0 and abs(up_pct) < 2.0:
            out["quiet_accumulation"] = {"pct": b.deliv_pct, "range5d": round(rng, 1)}

    # I2 large average trade size vs its average
    if b.trades > 0:
        avg_trade = b.turnover / b.trades
        prior_avg_trades = []
        for day in prior:
            db = day.get(symbol)
            if db and db.trades > 0:
                prior_avg_trades.append(db.turnover / db.trades)
        if prior_avg_trades:
            base = mean(prior_avg_trades)
            if base > 0 and avg_trade >= 2.5 * base:
                out["large_trades"] = {"mult": avg_trade / base}

    # I3 accumulation on a DOWN day
    if b.deliv_pct is not None and b.deliv_pct >= DELIV_PCT_MIN and up_pct < -0.5:
        avg_dlv2 = mean(deliv_hist) if deliv_hist else None
        if avg_dlv2 is None or b.deliv_pct >= DELIV_MULT * avg_dlv2:
            out["down_day_accum"] = {"pct": b.deliv_pct, "down": round(up_pct, 1)}

    # H3 multi-day volume-backed advance
    up_days = 0
    for day in history:
        bb = day.get(symbol)
        if bb and bb.prev_close > 0 and bb.close > bb.prev_close:
            up_days += 1
        else:
            break
    if up_days >= 3 and vol_hist and b.volume > mean(vol_hist):
        out["multiday_advance"] = {"days": up_days}

    out["_ctx"] = {"close": b.close, "up_pct": up_pct, "turnover_cr": b.turnover / 100.0,
                   "is_up": is_up, "deliv_pct": b.deliv_pct, "series": b.series}
    return out
