"""Telegram delivery: sendMessage + sendDocument (file upload) via requests."""

from __future__ import annotations

import os

import requests

_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def send_message(chat_id: str, text: str) -> dict:
    token = _token()
    if not token:
        return {"ok": False, "error": "no TELEGRAM_BOT_TOKEN"}
    try:
        r = requests.post(
            _API.format(token=token, method="sendMessage"),
            data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=30,
        )
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def send_document(chat_id: str, file_path: str, caption: str = "") -> dict:
    token = _token()
    if not token:
        return {"ok": False, "error": "no TELEGRAM_BOT_TOKEN"}
    try:
        with open(file_path, "rb") as fh:
            r = requests.post(
                _API.format(token=token, method="sendDocument"),
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"document": fh},
                timeout=120,
            )
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def get_updates(offset: int | None = None, timeout: int = 0) -> dict:
    token = _token()
    if not token:
        return {"ok": False, "error": "no TELEGRAM_BOT_TOKEN"}
    params = {"timeout": timeout, "allowed_updates": '["message","channel_post"]'}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(_API.format(token=token, method="getUpdates"), params=params, timeout=timeout + 30)
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
