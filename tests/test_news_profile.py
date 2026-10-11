"""Offline tests: headline sentiment, news parsing, the about-block, and the sector fix that mis-filed electrical manufacturers as utilities."""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import news, profile, scorecard

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
RSS = """<rss><channel>
<item><title>Vidya Wires bags Rs 200 crore order - Moneycontrol</title><pubDate>Fri, 09 Oct 2026 08:00:00 GMT</pubDate><link>http://a</link></item>
<item><title>Vidya Wires bags Rs 200 crore order - Economic Times</title><pubDate>Fri, 09 Oct 2026 09:00:00 GMT</pubDate><link>http://b</link></item>
<item><title>Vidya Wires profit falls as copper costs weigh - Mint</title><pubDate>Mon, 05 Oct 2026 08:00:00 GMT</pubDate><link>http://c</link></item>
<item><title>Sensex ends higher on banking rally - Reuters</title><pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate><link>http://d</link></item>
<item><title>Vidya Wires old story surges - Old</title><pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate><link>http://e</link></item>
</channel></rss>"""


def test_sentiment_words_negation_and_clamp():
    assert news.score("Company bags record order, profit jumps") == 2
    assert news.score("Company reports loss, shares plunge") == -2
    assert news.score("Profit not growing as expected") < news.score("Profit growing as expected")
    assert news.score("Board meeting on Friday") == 0 and news.label(0) == "Neutral"


def test_parse_dedupes_filters_to_the_company_and_the_last_30_days():
    items = news.parse(RSS, news.tokens("Vidya Wires Limited", "VIDYAWIRES"), NOW)
    assert [i["date"] for i in items] == ["2026-10-09", "2026-10-05"]        # duplicate, other-company and 4-month-old items are gone
    assert items[0]["source"] == "Moneycontrol" and items[0]["label"] == "Positive" and items[1]["label"] == "Negative"
    s = news.overall(items)
    assert s["label"] == "Mixed" and s["pos"] == 1 and s["neg"] == 1


def test_overall_tone_and_empty():
    assert news.overall([])["label"] == "No recent news"
    assert news.overall([dict(score=2), dict(score=1)])["label"] == "Positive"
    assert news.overall([dict(score=-1), dict(score=-2)])["label"] == "Negative"


def test_fetch_never_raises(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    r = news.fetch("AAA", "Aaa Limited")
    assert r["ok"] is False and r["items"] == [] and "offline" in r["error"]


def test_profile_trims_at_a_sentence_and_handles_missing():
    long = " ".join(f"Sentence number {i} says something useful about the business." for i in range(20))
    out = profile.trim(long)
    assert out.endswith(".") and len(out) <= 480 and "Sentence number 0" in out
    mix = "Acme makes wires. It offers a, b, c, " + "d, " * 80 + "and e. Its products are used in railways and motors. Acme is based in Anand, India."
    got = profile.trim(mix)
    assert "used in railways" in got and "based in Anand" in got and len(got) <= 420 and "d, d, d" not in got
    assert profile.build({}, None)["what"] == "" and profile.build({"sector": "Industrials"}, {"sector": "X", "lens": "P/E"})["lens"] == "P/E"


def test_electrical_equipment_is_industrial_not_utility_and_real_utilities_stay():
    f = lambda ind, sec, nm: scorecard._classify({"industry": ind, "sector": sec, "longName": nm}, "X", 30, 1, 1)[0]
    assert f("Electrical Equipment & Parts", "Industrials", "Vidya Wires Limited") == "industrial"
    assert f("Utilities - Regulated Electric", "Utilities", "Tata Power Company Limited") == "utility"
    assert f("Utilities - Independent Power Producers", "Utilities", "JSW Energy") == "utility"
    assert f("Specialty Industrial Machinery", "Industrials", "Some Engineering") == "industrial"
    assert f("Banks - Regional", "Financial Services", "HDFC Bank") == "bank"
