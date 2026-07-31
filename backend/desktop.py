"""摩尚OA desktop shell (macOS).

Starts the FastAPI backend on a local port, then opens a native window
(WKWebView). Closing the window quits the app: pywebview cannot tell a
red-button close from Cmd+Q/Dock quit, so a hide-to-tray design traps the
process alive with no way back. Long-running approval watching belongs to
the Windows host (windows/serve_win.py), which has its own tray loop.
"""

from __future__ import annotations

import threading

import uvicorn
import webview
from app.local_server import is_expected_backend, port_in_use, wait_for_expected_backend
from app.main import app

HOST = "127.0.0.1"
PORT = 8017


def run_server() -> None:
    # Pass the imported ASGI object rather than a string import path: packaged
    # macOS apps do not have the source-tree `app` package on sys.path.
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main() -> None:
    if not port_in_use(HOST, PORT):
        threading.Thread(target=run_server, daemon=True).start()
    elif not is_expected_backend(HOST, PORT):
        raise RuntimeError(f"端口 {PORT} 已被其他程序占用，请关闭占用程序后重试")
    wait_for_expected_backend(HOST, PORT, timeout=15.0)
    webview.create_window(
        "办公助手",
        f"http://{HOST}:{PORT}/",
        width=1360,
        height=860,
        min_size=(1024, 640),
    )
    # private_mode=False：WKWebView 用持久化数据仓，否则 localStorage 每次启动清空，
    # 使用独立 WebView 资料目录，不与日常浏览器资料混用
    webview.start(private_mode=False)


if __name__ == "__main__":
    main()
