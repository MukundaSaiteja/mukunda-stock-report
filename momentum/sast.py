"""Group F: institutional/insider flows via NSE SAST disclosures (Reg 29).

Vendored from unusual-activity/sources/sast.py (import repointed).
"""

from __future__ import annotations

from momentum.nse_client import fetch_json


def sast_acquisitions() -> dict[str, str]:
    """Return {symbol: acquirer name} for recent substantial-stake acquisitions."""
    d = fetch_json("https://www.nseindia.com/api/corporate-sast-reg29?index=equities")
    out: dict[str, str] = {}
    rows = d.get("data", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue
        acq = r.get("acqName") or r.get("name") or ""
        mode = f"{r.get('pesPostToInter','')} {r.get('remarks','')}".lower()
        if "dispos" in mode or "sold" in mode or "sale" in mode:
            continue
        out[sym] = str(acq)[:40]
    return out
