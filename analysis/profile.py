"""'About the company' block: what it does (Yahoo business summary, trimmed), its sector/industry, and how the scorecard classified it."""

from __future__ import annotations

import re


_USEFUL = ("used in", "applications", "export", "serves", "customers", "operates", "segments", "incorporated", "based in", "founded")


def trim(text: str | None, limit: int = 420) -> str:
    """The first sentence, then the next sentences that say who uses it / where it sells (skipping long product lists), under ``limit``."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    out = sentences[0]
    if len(out) > limit:
        return out[:limit].rsplit(" ", 1)[0] + "..."
    for sent in sentences[1:]:
        if any(k in sent.lower() for k in _USEFUL) and len(out) + 1 + len(sent) <= limit:
            out = f"{out} {sent}"
        elif any(k in sent.lower() for k in _USEFUL) and len(out) < limit * 0.5:
            out = f"{out} {sent[:limit - len(out) - 4].rsplit(' ', 1)[0]}..."
            break
    return out


def build(info: dict, scorecard: dict | None) -> dict:
    sc = scorecard or {}
    return dict(
        what=trim((info or {}).get("longBusinessSummary")),
        sector=(info or {}).get("sector"),
        industry=(info or {}).get("industry"),
        lens_sector=sc.get("sector"),
        lens=sc.get("lens"),
        website=(info or {}).get("website"),
        employees=(info or {}).get("fullTimeEmployees"),
    )
