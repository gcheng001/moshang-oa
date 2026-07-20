"""Identity checks for the localhost backend used by desktop launchers."""

from __future__ import annotations

import json
import socket
import time
from urllib.request import urlopen

APP_ID = "com.moshang.office-assistant"
APP_VERSION = "2.2.0"


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def is_expected_backend(host: str, port: int, *, timeout: float = 1.0) -> bool:
    """Return true only when the listener is this exact app version."""
    try:
        with urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as response:
            payload = json.load(response)
    except Exception:
        return False
    return payload == {"app": APP_ID, "version": APP_VERSION}


def wait_for_expected_backend(host: str, port: int, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_expected_backend(host, port):
            return
        time.sleep(0.3)
    raise RuntimeError(f"办公助手后端启动超时或端口 {port} 被其他程序占用")
