"""Latest news for a stock with a plain-words sentiment read (Google News RSS + a small finance lexicon).

Best-effort and offline-testable: ``fetch`` never raises; ``score`` is pure. This is headline tone only - it is not a forecast and
it does not read the articles.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

POS = {"profit", "profits", "growth", "surge", "surges", "jump", "jumps", "rally", "rallies", "gain", "gains", "record", "wins", "win", "bags",
       "secures", "secured", "order", "orders", "upgrade", "upgraded", "beat", "beats", "expands", "expansion", "strong", "rise", "rises", "hike",
       "dividend", "bonus", "approval", "approved", "outperform", "soars", "climbs", "high", "buy", "bullish", "boost", "robust", "rating",
       "growing", "doubles", "triples", "turnaround", "capex", "commissioning", "launch", "launches"}
NEG = {"loss", "losses", "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "decline", "declines", "cut", "cuts", "downgrade", "downgraded",
       "sell", "miss", "misses", "probe", "fraud", "penalty", "fine", "fined", "default", "resigns", "resignation", "weak", "slashes", "concern",
       "concerns", "risk", "warning", "lawsuit", "raid", "delay", "delays", "lower", "tumbles", "crash", "pledge", "bearish", "shortfall", "notice",
       "scam", "investigation", "sebi", "debt", "stake sale", "offloads", "dumps"}
NEGATORS = {"not", "no", "without", "denies", "fails", "unlikely"}
GOOD_NOUNS = {"profit", "profits", "growth", "gain", "gains", "order", "orders", "rating"}  # "profit falls": the noun must not cancel the verb


def _words(title: str) -> list[str]:
    return re.findall(r"[a-z]+", title.lower())


def score(title: str) -> int:
    """+ per positive word, - per negative word; a negator in the two words before flips that word. Clamped to -2..+2."""
    w = _words(title)
    total = 0
    for i, word in enumerate(w):
        sign = 1 if word in POS else -1 if word in NEG else 0
        if sign > 0 and word in GOOD_NOUNS and i + 1 < len(w) and w[i + 1] in NEG:
            sign = 0
        if sign and any(x in NEGATORS for x in w[max(0, i - 2):i]):
            sign = -sign
        total += sign
    return max(-2, min(2, total))


def label(sc: float) -> str:
    return "Positive" if sc >= 1 else "Negative" if sc <= -1 else "Neutral"


def overall(items: list[dict]) -> dict:
    if not items:
        return dict(label="No recent news", mean=0.0, pos=0, neg=0, neu=0)
    pos = sum(i["score"] > 0 for i in items)
    neg = sum(i["score"] < 0 for i in items)
    mean = sum(i["score"] for i in items) / len(items)
    if pos and neg and abs(mean) < 0.75:
        tone = "Mixed"                      # good and bad headlines both present and no clear lean
    else:
        tone = "Positive" if mean >= 0.25 else "Negative" if mean <= -0.25 else "Neutral"
    return dict(label=tone, mean=round(mean, 2), pos=pos, neg=neg, neu=len(items) - pos - neg)


STOCK_WORDS = {"share", "shares", "stock", "stocks", "nse", "bse", "results", "result", "profit", "sales", "revenue", "rally", "order", "orders",
               "dividend", "target", "quarter", "q1", "q2", "q3", "q4", "ipo", "bonus", "multibagger", "agm", "stake", "rating", "earnings",
               "expansion", "capacity", "investors", "market", "brokerage", "buy", "sell"}


def _is_stock_news(low: str) -> bool:
    """A headline that only shares a first word with another company (e.g. a brewery) has no stock-market word in it."""
    return bool(STOCK_WORDS & set(_words(low)))


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()[:70]


def parse(xml_text: str, name_tokens: list[str], now: datetime, days: int = 30, limit: int = 8) -> list[dict]:
    root = ET.fromstring(xml_text)
    cutoff, seen, out = now - timedelta(days=days), set(), []
    for it in root.iter("item"):
        raw = (it.findtext("title") or "").strip()
        head, _, src = raw.rpartition(" - ")
        head, src = (head, src) if head else (raw, (it.findtext("source") or "").strip())
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = _norm(head)
        if when < cutoff or key in seen or not head:
            continue
        low = head.lower()
        if name_tokens and not any(t in low for t in name_tokens):
            continue                                    # keep only headlines that actually name the company
        if not _is_stock_news(low):
            continue
        seen.add(key)
        sc = score(head)
        out.append(dict(title=head, source=src, date=when.date().isoformat(), url=(it.findtext("link") or ""), score=sc, label=label(sc)))
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:limit]


def tokens(name: str | None, symbol: str) -> list[str]:
    stop = {"limited", "ltd", "india", "indian", "company", "corporation", "industries", "the", "and", "of"}
    first = [w for w in _words(name or "") if w not in stop and len(w) >= 4][:1]
    return list(dict.fromkeys(first + [symbol.lower().split(".")[0]]))


def fetch(symbol: str, name: str | None = None, now: datetime | None = None) -> dict:
    """Never raises. Returns {ok, items, summary, error}."""
    now = now or datetime.now(timezone.utc)
    try:
        import requests

        base = re.sub(r"\b(limited|ltd\.?)\b", "", name or symbol, flags=re.I).strip()
        q = quote(f'"{base}" stock when:30d')
        r = requests.get(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en", timeout=12,
                         headers={"User-Agent": "Mozilla/5.0 (educational stock research)"})
        if r.status_code != 200:
            return dict(ok=False, items=[], summary=overall([]), error=f"news feed HTTP {r.status_code}")
        items = parse(r.text, tokens(name, symbol), now)
        return dict(ok=True, items=items, summary=overall(items), error="")
    except Exception as exc:  # noqa: BLE001 - news must never break the report
        return dict(ok=False, items=[], summary=overall([]), error=str(exc)[:120])
