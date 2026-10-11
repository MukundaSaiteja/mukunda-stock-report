"""Child process: ``python -m outlook SYMBOL OUT.json [DEADLINE_EPOCH]``. Writes a range-only result first, then the Kronos one."""

from __future__ import annotations

import json
import sys
import time

from . import core
from .engine import KronosEngine


def fetch(symbol: str):
    import yfinance as yf

    suffixes = ("",) if symbol.endswith((".NS", ".BO")) else (".NS", ".BO")
    for suffix in suffixes:
        raw = yf.Ticker(symbol + suffix).history(period="4y", interval="1d", auto_adjust=True)
        if raw is not None and not raw.empty:
            return core.clean(raw), ("BSE" if (symbol + suffix).endswith(".BO") else "NSE")
    raise ValueError(f"no Yahoo data for {symbol}")


def main(argv: list[str]) -> int:
    symbol, path = argv[0].upper(), argv[1]
    deadline = float(argv[2]) if len(argv) > 2 else None

    def save(o: core.Outlook) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(core.to_json(o), fh)

    df, exchange = fetch(symbol)
    o = core.build(symbol.rsplit(".", 1)[0], df, KronosEngine(), exchange=exchange, checkpoint=save, deadline=deadline)
    save(o)
    print(f"outlook {symbol}: {o.status}, {o.paths} paths, {time.strftime('%H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
