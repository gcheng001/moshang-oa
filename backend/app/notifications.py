"""Optional Feishu robot notifications.

The webhook is kept in the OS credential vault. Missing configuration is a
normal state and never blocks approval polling or OA writes.
"""

from __future__ import annotations

from urllib.parse import urlparse

import requests

from . import credentials


def send_feishu(text: str) -> bool:
    webhook = credentials.load_feishu_webhook()
    if not webhook:
        return False
    parsed = urlparse(webhook)
    if parsed.scheme != "https" or parsed.hostname not in {"open.feishu.cn", "open.larksuite.com"}:
        raise ValueError("飞书机器人地址必须是飞书官方 HTTPS Webhook")
    response = requests.post(
        webhook,
        json={"msg_type": "text", "content": {"text": text}},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("code") not in (None, 0):
        raise RuntimeError(str(payload.get("msg") or "飞书机器人通知失败"))
    return True
