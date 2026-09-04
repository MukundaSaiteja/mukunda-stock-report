#!/usr/bin/env python3
"""CLI: analyse one NSE stock -> PDF, optionally send to Telegram.

Usage:
    python main.py --symbol RELIANCE                       # build PDF only
    python main.py --symbol RELIANCE --send --chat <id>    # build + send to Telegram
"""

from __future__ import annotations

import argparse
import os
import tempfile

from analysis.analyzer import analyze
from notifications import telegram


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="main.py")
    p.add_argument("--symbol", required=True, help="Exact NSE symbol, e.g. RELIANCE")
    p.add_argument("--send", action="store_true", help="Send the PDF to Telegram")
    p.add_argument("--chat", default=os.environ.get("TELEGRAM_CHAT_ID", ""), help="Telegram chat/channel id")
    p.add_argument("--out", default="", help="PDF output path (default: temp)")
    args = p.parse_args(argv)

    sym = args.symbol.strip().upper()
    out = args.out or os.path.join(tempfile.gettempdir(), f"{sym}_report.pdf")

    print(f"Analyzing {sym} ...")
    result = analyze(sym, out)
    if not result["ok"]:
        print(f"FAILED: {result['error']}")
        if args.send and args.chat:
            telegram.send_message(args.chat, f"❌ Could not analyse *{sym}*: {result['error']}\nUse the exact NSE symbol (e.g. RELIANCE).")
        return

    print(f"PDF built: {result['pdf']}")
    print(f"Lean: {result['verdict']['lean']} (score {result['verdict']['score']})")

    if args.send:
        if not args.chat:
            print("No --chat / TELEGRAM_CHAT_ID; not sending.")
            return
        name = result["snapshot"].get("name") or sym
        cap = f"📄 {name} ({sym}) — quant research snapshot\nLean: {result['verdict']['lean']}"
        resp = telegram.send_document(args.chat, result["pdf"], cap)
        print("Telegram:", "SENT" if resp.get("ok") else resp)


if __name__ == "__main__":
    main()
