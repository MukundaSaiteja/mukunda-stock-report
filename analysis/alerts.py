"""Command handling + checking for price-level alerts.

Commands (post in the channel):
    /alert RELIANCE below 1250        -> manual level alert
    /alert RELIANCE above 1400
    /alert RELIANCE                    -> AUTO: uses computed S1 (below) & R1 (above)
    /alerts                            -> list active alerts
    /cancelalert RELIANCE              -> remove all alerts for a symbol
    /cancelalert RELIANCE below 1250   -> remove one specific alert

One-shot + cooldown: an alert fires once when price crosses the level, then goes
quiet for ALERT_COOLDOWN_HOURS and re-arms when price returns to the safe side.
"""

from __future__ import annotations

import re

from analysis import alerts_store as store
from analysis.alerts_store import Alert, make_id
from analysis.price import live_price

# Bare "/alert" or "@alert" (with nothing after) -> show help.
_HELP = re.compile(r"^[/@]alert(?:@\w+)?\s*$", re.IGNORECASE)
# Set: /alert SYM [above|below PRICE]   (also accepts @alert)
_ALERT = re.compile(
    r"^[/@]alert(?:@\w+)?\s+([A-Za-z0-9&\-\.]{1,20})(?:\s+(above|below)\s+([0-9]+(?:\.[0-9]+)?))?\s*$",
    re.IGNORECASE,
)
_ALERTS = re.compile(r"^[/@]alerts(?:@\w+)?\s*$", re.IGNORECASE)
# Delete, several natural forms:
#   /cancelalert SYM [above|below PRICE]
#   /alert delete SYM   |   /alert SYM delete
#   /stock SYM alert delete   |   /stock SYM delete alert
_CANCEL = re.compile(
    r"^[/@]cancelalert(?:@\w+)?\s+([A-Za-z0-9&\-\.]{1,20})(?:\s+(above|below)\s+([0-9]+(?:\.[0-9]+)?))?\s*$",
    re.IGNORECASE,
)
_DELETE = re.compile(
    r"^(?:[/@]alert(?:@\w+)?\s+delete\s+([A-Za-z0-9&\-\.]{1,20})"
    r"|[/@]alert(?:@\w+)?\s+([A-Za-z0-9&\-\.]{1,20})\s+delete"
    r"|[/@]stock(?:@\w+)?\s+([A-Za-z0-9&\-\.]{1,20})\s+(?:alert\s+delete|delete\s+alert))\s*$",
    re.IGNORECASE,
)

HELP_TEXT = (
    "🔔 *Price alerts — how to use*\n"
    "`/alert RELIANCE below 1250`  — ping when price falls to/below 1250\n"
    "`/alert RELIANCE above 1400`  — ping when price rises to/above 1400\n"
    "`/alert RELIANCE`  — auto: use computed S1 (below) & R1 (above)\n"
    "`/alerts`  — list your active alerts\n"
    "`/stock RELIANCE alert delete`  — remove alerts for a stock\n"
    "`/cancelalert RELIANCE below 1250`  — remove one specific alert\n\n"
    "_Fires once when the level is crossed; won't repeat while price stays there — "
    "it re-arms only after price returns to the safe side._"
)


def _auto_levels(symbol: str):
    """Return (support_S1, resistance_R1) from the analyzer's technicals, or (None,None)."""
    try:
        from analysis.data import fetch
        from analysis.technicals import compute
        d = fetch(symbol)
        if not d.ok:
            return None, None
        sr = compute(d.price).get("support_resistance", {})
        return sr.get("S1"), sr.get("R1")
    except Exception:  # noqa: BLE001
        return None, None


def handle_command(text: str, chat_id: str) -> str | None:
    """Handle an /alert* command. Returns a reply string, or None if not a command."""
    alerts = store.load()

    # Bare "/alert" or "@alert" -> show usage help automatically.
    if _HELP.match(text):
        return HELP_TEXT

    # Delete forms: /alert delete SYM | /alert SYM delete | /stock SYM alert delete
    m = _DELETE.match(text)
    if m:
        sym = (m.group(1) or m.group(2) or m.group(3)).upper()
        alerts, n = store.remove_symbol(alerts, sym)
        store.save(alerts)
        return f"🗑️ Removed {n} alert(s) for {sym}." if n else f"No alerts found for {sym}."

    m = _ALERTS.match(text)
    if m:
        mine = [a for a in alerts if a.chat_id == chat_id]
        if not mine:
            return "No active alerts. Set one with `/alert RELIANCE below 1250`."
        lines = ["🔔 *Active alerts:*"]
        for a in mine:
            state = "armed" if a.armed else "fired today"
            lines.append(f"• {a.symbol} {a.direction} {a.level:g}  ({a.note or 'manual'}, {state})")
        return "\n".join(lines)

    m = _CANCEL.match(text)
    if m:
        sym, direction, level = m.group(1).upper(), m.group(2), m.group(3)
        if direction and level:
            aid = make_id(sym, direction.lower(), float(level))
            alerts, ok = store.remove(alerts, aid)
            store.save(alerts)
            return f"🗑️ Removed alert {sym} {direction} {level}." if ok else f"No such alert: {sym} {direction} {level}."
        alerts, n = store.remove_symbol(alerts, sym)
        store.save(alerts)
        return f"🗑️ Removed {n} alert(s) for {sym}." if n else f"No alerts found for {sym}."

    m = _ALERT.match(text)
    if m:
        sym, direction, level = m.group(1).upper(), m.group(2), m.group(3)
        if direction and level:
            lvl = float(level)
            a = Alert(id=make_id(sym, direction.lower(), lvl), symbol=sym,
                      direction=direction.lower(), level=lvl, chat_id=chat_id, note="manual")
            alerts = store.upsert(alerts, a)
            store.save(alerts)
            return f"✅ Alert set: *{sym}* {direction} *{lvl:g}*. You'll be pinged when it crosses."
        # AUTO from S/R
        s1, r1 = _auto_levels(sym)
        if s1 is None and r1 is None:
            return f"❌ Couldn't compute S/R for *{sym}*. Try a manual level: `/alert {sym} below <price>`."
        created = []
        if s1 is not None:
            alerts = store.upsert(alerts, Alert(id=make_id(sym, "below", s1), symbol=sym,
                                                direction="below", level=float(s1), chat_id=chat_id, note="S1"))
            created.append(f"below {s1:g} (S1)")
        if r1 is not None:
            alerts = store.upsert(alerts, Alert(id=make_id(sym, "above", r1), symbol=sym,
                                                direction="above", level=float(r1), chat_id=chat_id, note="R1"))
            created.append(f"above {r1:g} (R1)")
        store.save(alerts)
        return f"✅ Auto alerts for *{sym}*: " + " & ".join(created) + "."

    return None


def check_alerts() -> list[tuple[str, str]]:
    """Evaluate all alerts against live prices. Returns [(chat_id, message)] to send.

    Fires one-shot per crossing; saves updated armed/cooldown state.
    """
    alerts = store.load()
    if not alerts:
        return []
    to_send: list[tuple[str, str]] = []
    price_cache: dict[str, tuple[float | None, str]] = {}
    changed = False

    for a in alerts:
        if a.symbol not in price_cache:
            price_cache[a.symbol] = live_price(a.symbol)
        price, src = price_cache[a.symbol]
        if price is None:
            continue
        before = (a.armed, a.last_fired)
        if store.evaluate(a, price):
            arrow = "🔺" if a.direction == "above" else "🔻"
            tag = f" ({a.note})" if a.note and a.note != "manual" else ""
            to_send.append((a.chat_id,
                            f"{arrow} *{a.symbol}* reached your level!\n"
                            f"Now *{price:,.2f}* {a.direction} *{a.level:g}*{tag}  _(via {src})_\n"
                            f"_Alert fired — cooling down; re-arms when price returns._"))
            changed = True
        elif (a.armed, a.last_fired) != before:
            changed = True

    if changed:
        store.save(alerts)
    return to_send
