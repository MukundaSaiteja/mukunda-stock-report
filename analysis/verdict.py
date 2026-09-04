"""Rule-based verdict + entry/exit zones from the computed layers.

This is a transparent QUANT synthesis, not deep research or advice. It scores a
handful of objective signals and maps to a lean + level zones anchored to real
support/resistance.
"""

from __future__ import annotations


def build(snap: dict, tech: dict, forensic: dict, quant: dict) -> dict:
    score = 0
    reasons = []

    # Trend / momentum
    if tech.get("px_vs_200dma_pct") is not None:
        if tech["px_vs_200dma_pct"] > 0:
            score += 1; reasons.append("above 200-DMA")
        else:
            score -= 1; reasons.append("below 200-DMA")
    if (quant.get("rs_vs_nifty_pct") or 0) > 0:
        score += 1; reasons.append("outperforming Nifty")
    elif quant.get("rs_vs_nifty_pct") is not None:
        score -= 1; reasons.append("lagging Nifty")
    if (quant.get("mom_12_1_pct") or 0) > 0:
        score += 1; reasons.append("positive 12-1 momentum")

    # Quality
    if (forensic.get("cfo_pat") or 0) >= 0.8:
        score += 1; reasons.append("healthy cash conversion")
    elif forensic.get("cfo_pat") is not None and forensic["cfo_pat"] < 0.5:
        score -= 1; reasons.append("weak cash conversion")
    if forensic.get("altman_z_zone") == "safe":
        score += 1; reasons.append("Altman Z safe")
    elif forensic.get("altman_z_zone") == "distress":
        score -= 1; reasons.append("Altman Z distress")

    # Overbought/oversold context
    rsi = tech.get("rsi14")
    if rsi is not None:
        if rsi > 70:
            reasons.append("RSI overbought")
        elif rsi < 30:
            reasons.append("RSI oversold")

    if score >= 3:
        lean = "Constructive (quant)"
    elif score <= -2:
        lean = "Cautious (quant)"
    else:
        lean = "Neutral / mixed (quant)"

    sr = tech.get("support_resistance", {})
    zones = {
        "buy_zone": f"{sr.get('S1')} - {sr.get('S2')}" if sr.get("S1") else "n/a",
        "cmp": tech.get("last_close"),
        "upside_zone": f"{sr.get('R1')} - {sr.get('R2')}" if sr.get("R1") else "n/a",
        "invalidation": f"below {sr.get('S3') or sr.get('low_52w')}" if sr else "n/a",
    }
    return {"score": score, "lean": lean, "reasons": reasons, "zones": zones}
