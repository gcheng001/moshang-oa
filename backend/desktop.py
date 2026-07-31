"""摩尚OA desktop shell.

Starts the FastAPI backend on a local port, then opens a native window
(WKWebView on macOS). Closing the window hides it; the menu-bar icon keeps the
three-minute approval watcher alive until the user explicitly quits.
"""

from __future__ import annotations

import os
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
    window = webview.create_window(
        "办公助手",
        f"http://{HOST}:{PORT}/",
        width=1360,
        height=860,
        min_size=(1024, 640),
    )
    tray = None
    try:
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (79, 70, 229, 255))
        ImageDraw.Draw(image).rectangle((18, 16, 46, 48), fill=(255, 255, 255, 255))

        def open_app(_icon, _item) -> None:
            window.show()

        def exit_app(icon, _item) -> None:
            icon.stop()
            os._exit(0)

        tray = pystray.Icon(
            "MoshangOA",
            image,
            "办公助手",
            menu=pystray.Menu(
                pystray.MenuItem("打开办公助手", open_app, default=True),
                pystray.MenuItem("退出办公助手", exit_app),
            ),
        )
        tray.run_detached()

        def hide_instead_of_close() -> bool:
            window.hide()
            return False

        window.events.closing += hide_instead_of_close
    except Exception:
        tray = None
    # private_mode=False：WKWebView 用持久化数据仓，否则 localStorage 每次启动清空，
    # 使用独立 WebView 资料目录，不与日常浏览器资料混用
    webview.start(private_mode=False)
    if tray is not None:
        tray.stop()


if __name__ == "__main__":
    main()
