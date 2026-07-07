"""摩尚OA desktop shell.

Starts the FastAPI backend on a local port, then opens a native window
(WKWebView on macOS) pointing at it. Close the window to quit.
"""

from __future__ import annotations

import socket
import threading
import time
from urllib.request import urlopen

import uvicorn
import webview

HOST = "127.0.0.1"
PORT = 8017


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) == 0


def run_server() -> None:
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")


def wait_ready(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(f"http://{HOST}:{PORT}/", timeout=1)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("后端启动超时")


def main() -> None:
    if not port_in_use(PORT):
        threading.Thread(target=run_server, daemon=True).start()
    wait_ready()
    webview.create_window(
        "摩尚OA",
        f"http://{HOST}:{PORT}/",
        width=1360,
        height=860,
        min_size=(1024, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
