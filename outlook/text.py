"""Plain-words lines for the prediction section (same wording and test evidence as the research repo's kronos-forecast)."""

from __future__ import annotations

from .core import Outlook, pct

TITLE = "12. Kronos price prediction (experimental)"
# Test evidence by horizon in trading sessions (random Nifty 500 stocks, Kronos-small, 400 bars of context):
#   n = forecasts scored; direction = % whose up/down call was right (50 = coin flip); held = % the stock's own normal range held (target 80).
EVIDENCE = {5: dict(n=813, direction=50, held=81), 21: dict(n=150, direction=50, held=79), 126: dict(n=38, direction=42, held=72)}


def rs(x: float) -> str:
    return f"Rs {x:,.2f}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def subtitle(o: Outlook) -> str:
    return f"{o.exchange}: {o.symbol}. Based on daily prices to {o.asof:%d-%b-%Y} close. Today's price: {rs(o.last_close)}."


def table_rows(o: Outlook) -> list[list[str]]:
    rows = [["Horizon", "By", "Kronos predicted price", "vs today's price", "Normal range (80%)"]]
    for s in o.steps:
        change = "n/a" if s.kronos is None else pct(s.kronos / o.last_close - 1)
        rows.append([s.label, ("about " if s.sessions > 60 else "") + f"{s.day:%d-%b-%Y}",
                     ("not run" if s.skipped else "not shown") if s.kronos is None else rs(s.kronos), change, f"{rs(s.low)} - {rs(s.high)}"])
    return rows


def evidence_line(o: Outlook) -> str:
    seen = [(s, EVIDENCE.get(s.sessions) or {}) for s in o.steps]
    tested = [f"{e['direction']}% at {s.label}" for s, e in seen if e.get("direction") is not None]
    sizes = [str(e["n"]) for _, e in seen if e.get("n")]
    held = [f"{e['held']}% at {s.label}" for s, e in seen if e.get("held") is not None]
    right = f"its up-or-down call was right {_join(tested)}" if tested else "its up-or-down call has not been tested"
    return ("Experimental. Kronos is a general AI model for price charts and knows nothing about this company's business. "
            f"In our tests on random Nifty 500 stocks {right}. 50% is a coin flip" + (f" ({_join(sizes)} test forecasts)" if sizes else "") + ". "
            + (f"The normal range held the real price {_join(held)} of the time (the target is 80%). " if held else "")
            + "Longer forecasts are less certain. Not a price target and not advice.")


def notes(o: Outlook) -> list[str]:
    """Only a one-line reason when a row is withheld or Kronos did not run; nothing else."""
    hidden = [s for s in o.steps if s.kronos is None and not s.skipped]
    if o.status == "ok" and hidden:
        return [f"Kronos not shown for {hidden[0].label}: {hidden[0].note}."]
    if o.status != "ok":
        return [f"Kronos prediction not available this run: {o.note}."]
    return []


def method_line(o: Outlook) -> str:
    kronos = (f"Kronos-{o.cfg.model}, {min(o.bars, o.cfg.lookback)} daily bars of context, {o.paths} imagined futures, seed {o.cfg.seed} "
              "(a re-run can move a figure by a few points); " if o.paths else "Kronos not shown; ")
    return (f"Method: {kronos}30 days = 21 and 6 months = 126 trading sessions (the normal range uses the same days). Normal range = today's price x (1 +/- 1.28 x daily move "
            "over the last 60 sessions x square root of the days). Yahoo prices, split and dividend adjusted; dates assume normal trading days.")
