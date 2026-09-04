"""Forensic / earnings-quality scores from yfinance statements (best-effort).

Piotroski F (partial where inputs exist), Altman Z, Sloan accruals, CFO/PAT.
yfinance statement row labels vary; we look up by fuzzy label and return None when
an input is missing rather than guessing. These are approximations from the
public statements and are labelled as such in the report.
"""

from __future__ import annotations

import pandas as pd


def _row(df: pd.DataFrame | None, *names) -> pd.Series | None:
    if df is None or df.empty:
        return None
    idx = {str(i).lower(): i for i in df.index}
    for n in names:
        key = n.lower()
        for lo, orig in idx.items():
            if key in lo:
                return df.loc[orig]
    return None


def _val(series: pd.Series | None, col=0):
    if series is None:
        return None
    try:
        v = float(series.iloc[col])
        return None if pd.isna(v) else v
    except (IndexError, ValueError, TypeError):
        return None


def compute(fin: pd.DataFrame | None, bs: pd.DataFrame | None, cf: pd.DataFrame | None) -> dict:
    out: dict = {}

    net_income = _val(_row(fin, "net income"))
    net_income_prev = _val(_row(fin, "net income"), 1)
    revenue = _val(_row(fin, "total revenue", "revenue"))
    cfo = _val(_row(cf, "operating cash flow", "cash flow from continuing operating", "total cash from operating"))
    total_assets = _val(_row(bs, "total assets"))
    total_assets_prev = _val(_row(bs, "total assets"), 1)
    total_liab = _val(_row(bs, "total liabilities net minority", "total liab"))
    cur_assets = _val(_row(bs, "current assets"))
    cur_liab = _val(_row(bs, "current liabilities"))
    retained = _val(_row(bs, "retained earnings"))
    ebit = _val(_row(fin, "ebit", "operating income"))
    equity = _val(_row(bs, "stockholders equity", "total equity gross minority", "common stock equity"))

    # CFO / PAT (cash conversion) — the #1 paper-profit check
    out["cfo_pat"] = round(cfo / net_income, 2) if cfo is not None and net_income else None

    # Sloan accruals = (NI - CFO) / avg total assets
    if net_income is not None and cfo is not None and total_assets:
        denom = ((total_assets + total_assets_prev) / 2) if total_assets_prev else total_assets
        out["sloan_accruals"] = round((net_income - cfo) / denom, 3) if denom else None
    else:
        out["sloan_accruals"] = None

    # Altman Z (manufacturing) approximation
    try:
        wc = (cur_assets - cur_liab) if (cur_assets is not None and cur_liab is not None) else None
        mcap = None  # filled by caller if available
        if all(x is not None for x in [wc, retained, ebit, total_assets, total_liab]) and total_assets and total_liab:
            z = (1.2 * wc / total_assets + 1.4 * retained / total_assets
                 + 3.3 * ebit / total_assets + 0.6 * (equity or 0) / total_liab
                 + 1.0 * (revenue or 0) / total_assets)
            out["altman_z"] = round(z, 2)
            out["altman_z_zone"] = ("safe" if z > 2.99 else "grey" if z >= 1.8 else "distress")
        else:
            out["altman_z"] = None
    except Exception:  # noqa: BLE001
        out["altman_z"] = None

    # Piotroski partial (profitability + leverage subset we can compute)
    f = 0
    checks = 0
    if net_income is not None:
        checks += 1; f += 1 if net_income > 0 else 0
    if cfo is not None:
        checks += 1; f += 1 if cfo > 0 else 0
    if net_income is not None and cfo is not None:
        checks += 1; f += 1 if cfo > net_income else 0            # accrual quality
    if net_income is not None and net_income_prev is not None:
        checks += 1; f += 1 if net_income > net_income_prev else 0  # profit growth
    out["piotroski_partial"] = f
    out["piotroski_checks"] = checks

    # Leverage / coverage
    interest = _val(_row(fin, "interest expense"))
    out["debt_to_equity"] = round(total_liab / equity, 2) if total_liab is not None and equity else None
    out["interest_coverage"] = round(ebit / abs(interest), 1) if ebit is not None and interest else None
    return out
