"""Orchestrate the full single-stock analysis into one result dict + PDF."""

from __future__ import annotations

import pandas as pd

from analysis import data as datamod
from analysis import forensic, quant, technicals, valuation, verdict
from momentum import engine as momentum_engine
from report import pdf as pdfmod


def _financials_table(fin: pd.DataFrame | None, cf: pd.DataFrame | None) -> dict | None:
    if fin is None or fin.empty:
        return None
    years = [str(c)[:4] for c in fin.columns][:5]

    def row_of(df, label, *names, scale=1e7, d=0, suf=""):
        if df is None:
            return None
        idx = {str(i).lower(): i for i in df.index}
        for n in names:
            for lo, orig in idx.items():
                if n.lower() in lo:
                    vals = []
                    for col in df.columns[:5]:
                        try:
                            vals.append(f"{float(df.loc[orig, col])/scale:,.{d}f}{suf}")
                        except (TypeError, ValueError):
                            vals.append("n/a")
                    return [label] + vals
        return [label] + ["n/a"] * len(years)

    rows = [
        row_of(fin, "Revenue (Cr)", "total revenue", "revenue"),
        row_of(fin, "EBIT (Cr)", "ebit", "operating income"),
        row_of(fin, "Net profit (Cr)", "net income"),
        row_of(cf, "CFO (Cr)", "operating cash flow", "total cash from operating"),
    ]
    rows = [r for r in rows if r]
    return {"years": years, "rows": rows}


def analyze(symbol: str, out_pdf: str) -> dict:
    """Run everything. Returns a result dict incl. 'ok', 'error', and 'pdf'."""
    d = datamod.fetch(symbol)
    if not d.ok:
        return {"ok": False, "symbol": d.symbol, "error": d.error}

    snap = valuation.snapshot(d.info)
    an = valuation.analyst(d.info)
    tech = technicals.compute(d.price)
    fore = forensic.compute(d.financials, d.balance_sheet, d.cashflow)
    qt = quant.compute(d.price, d.nifty)
    vd = verdict.build(snap, tech, fore, qt)
    fin_tbl = _financials_table(d.financials, d.cashflow)

    # A-F momentum footprints (why the stock may be moving). Best-effort: on any
    # failure it returns {"ok": False} and the PDF renders the section as n/a.
    mom = momentum_engine.compute(d.symbol, d.price, d.info, d.nifty)

    result = {
        "ok": True,
        "symbol": d.symbol,
        "as_of": d.as_of,
        "price": d.price,
        "snapshot": snap,
        "analyst": an,
        "technicals": tech,
        "forensic": fore,
        "quant": qt,
        "verdict": vd,
        "financials_table": fin_tbl,
        "momentum": mom,
    }
    result["pdf"] = pdfmod.build(result, out_pdf)
    return result
