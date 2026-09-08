"""Shared NSE HTTP client: cookie-primed, browser headers, fast-fail on block.

Vendored from unusual-activity/sources/nse_client.py but tuned for the on-demand
PDF: 1 attempt and no long retry wait by default, so a blocked NSE (common from
datacenter/CI IPs) degrades to None in a couple of seconds instead of stalling
the report. Still env-overridable.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.request

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

RETRY_WAIT = float(os.environ.get("NSE_RETRY_WAIT_SECONDS", "0"))
MAX_ATTEMPTS = int(os.environ.get("NSE_MAX_ATTEMPTS", "1"))
TIMEOUT = float(os.environ.get("NSE_TIMEOUT_SECONDS", "8"))


def _opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def fetch_json(url: str, referer: str | None = None) -> dict | list | None:
    """GET a JSON NSE endpoint with cookie-prime. None on failure (best-effort)."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        op = _opener()
        headers = dict(_HEADERS)
        if referer:
            headers["Referer"] = referer
        try:
            try:
                op.open(urllib.request.Request("https://www.nseindia.com/", headers=headers), timeout=TIMEOUT).read(1)
            except Exception:  # noqa: BLE001
                pass
            raw = op.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT).read().decode("utf-8", "ignore")
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            if attempt < MAX_ATTEMPTS and RETRY_WAIT > 0:
                time.sleep(RETRY_WAIT)
    return None
