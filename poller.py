#!/usr/bin/env python3
"""Poll Telegram for /stock <SYMBOL> commands and reply with a PDF.

Reads getUpdates, finds NEW messages/channel-posts matching '/stock <SYMBOL>',
runs the analyzer, and sends the PDF back to the SAME chat. Ignores the bot's own
posts (so the daily alerts / PDFs it sends never loop). Stateless dedupe: it
confirms the Telegram offset so processed updates are not returned again.

Env:
    TELEGRAM_BOT_TOKEN   the bot token (reused @Analysis_Stock_Alert_bot)
    STOCK_ALLOWED_CHAT   optional: only accept commands from this chat id
"""

from __future__ import annotations

import os
import re
import tempfile

from analysis import alerts as alertsmod
from analysis.analyzer import analyze
from notifications import telegram

_STOCK = re.compile(r"^/stock(?:@\w+)?\s+([A-Za-z0-9&\-\.]{1,20})", re.IGNORECASE)


def _message(update: dict):
    """Return (chat_id, text) for a user message/channel post, else None."""
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return None
    text = (msg.get("text") or "").strip()
    if not text:
        return None
    frm = msg.get("from") or {}
    if frm.get("is_bot"):          # ignore the bot's own posts (no loops)
        return None
    chat = msg.get("chat") or {}
    return str(chat.get("id")), text


def run_once() -> int:
    allowed = os.environ.get("STOCK_ALLOWED_CHAT", "").strip()
    # Short long-poll: wait up to ~20s for a message so a run triggered right
    # after a post still catches it (Telegram holds the connection open).
    resp = telegram.get_updates(timeout=20)
    if not resp.get("ok"):
        print("getUpdates failed:", resp.get("error") or resp)
        _check_price_alerts()
        return 0
    updates = resp.get("result", [])
    if not updates:
        print("No new updates.")
        _check_price_alerts()
        return 0

    # CLAIM the updates FIRST: confirm the offset before the slow analysis so any
    # other poll (GitHub cron + cron-job.org both firing) that starts meanwhile
    # sees an empty queue and skips. Whoever grabs it first owns it; the rest
    # ignore -> exactly one PDF per command, no duplicates.
    last_id = updates[-1].get("update_id")
    telegram.get_updates(offset=last_id + 1)

    processed = 0
    for up in updates:
        parsed = _message(up)
        if not parsed:
            continue
        chat_id, text = parsed
        if allowed and chat_id != allowed:
            print(f"Ignoring message from non-allowed chat {chat_id}")
            continue

        # Route: /alert* commands first (set/list/cancel price-level alerts).
        if text.lower().startswith(("/alert", "/alerts", "/cancelalert")):
            reply = alertsmod.handle_command(text, chat_id)
            if reply:
                print(f"Alert command: {text!r}")
                telegram.send_message(chat_id, reply)
                processed += 1
            continue

        # /stock <SYMBOL> -> research PDF.
        m = _STOCK.match(text)
        if not m:
            continue
        symbol = m.group(1).upper()
        print(f"Command: /stock {symbol} from chat {chat_id}")
        telegram.send_message(chat_id, f"📄 Analyzing *{symbol}* — PDF shortly...")
        out = os.path.join(tempfile.gettempdir(), f"{symbol}_report.pdf")
        try:
            result = analyze(symbol, out)
        except Exception as exc:  # noqa: BLE001
            telegram.send_message(chat_id, f"❌ Error analysing *{symbol}*: {exc}")
            continue
        if not result.get("ok"):
            telegram.send_message(chat_id, f"❌ Could not analyse *{symbol}*: {result.get('error')}\nUse the exact NSE symbol (e.g. RELIANCE).")
            continue
        name = result["snapshot"].get("name") or symbol
        cap = f"📄 {name} ({symbol}) — quant research snapshot\nLean: {result['verdict']['lean']}"
        r = telegram.send_document(chat_id, result["pdf"], cap)
        print("sent PDF:", "ok" if r.get("ok") else r)
        processed += 1

    print(f"Processed {processed} command(s).")
    _check_price_alerts()
    return processed


def _check_price_alerts() -> None:
    """Check active price-level alerts against live prices and notify on crossings."""
    try:
        fires = alertsmod.check_alerts()
    except Exception as exc:  # noqa: BLE001
        print("alert check failed:", exc)
        return
    for chat_id, message in fires:
        telegram.send_message(chat_id, message)
        print(f"alert fired -> {chat_id}")
    print(f"Price alerts fired: {len(fires)}.")


if __name__ == "__main__":
    run_once()
