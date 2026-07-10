"""办公助手 Windows 启动器。

启动本地 FastAPI 后端（端口 8017），然后用 Edge 应用模式打开独立窗口
（--app：无地址栏无标签页，观感与桌面应用一致，Win10/11 自带 Edge）。
窗口关闭后后端随之退出。异常写入 logs/moshang_win.log。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.request import urlopen

HOST = "127.0.0.1"
PORT = 8017

_HERE = Path(__file__).resolve().parent
if (_HERE / "app" / "main.py").is_file():
    # 便携包布局：<包根>/app/backend/serve_win.py
    BACKEND_DIR = _HERE
    PKG_ROOT = _HERE.parent.parent
else:
    # 仓库布局：<仓库>/windows/serve_win.py，后端在 ../backend（GitHub 检出后直接可跑）
    BACKEND_DIR = _HERE.parent / "backend"
    PKG_ROOT = _HERE
LOG_DIR = PKG_ROOT / "logs"
sys.path.insert(0, str(BACKEND_DIR))

# pythonw（双击、无控制台）下 sys.stdout/stderr 为 None，
# uvicorn 配置日志时调 sys.stdout.isatty() 会直接崩 —— 接到日志文件兜底
if sys.stdout is None or sys.stderr is None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _stdio = open(LOG_DIR / "moshang_stdio.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _stdio
    if sys.stderr is None:
        sys.stderr = _stdio


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "moshang_win.log").open("a", encoding="utf-8") as fp:
        fp.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) == 0


def run_server() -> None:
    try:
        import uvicorn

        uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
    except BaseException:
        # pythonw 无控制台，后端线程异常必须落日志，否则只见"启动超时"不见病因
        log("后端线程异常：\n" + traceback.format_exc())
        raise


# 首次运行时 Defender 实时扫描新解压的数百个 pyd/py 文件，导入可能远超 20 秒，
# 放宽到 90 秒避免冷启动误判超时（正常启动 1-3 秒，不受影响）
def wait_ready(timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(f"http://{HOST}:{PORT}/", timeout=1)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("后端启动超时，详见 logs/moshang_win.log")


def find_edge() -> Path | None:
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for path in candidates:
        if path.is_file():
            return path
    return None


APP_TITLE = "办公助手"


def _find_icon() -> Path | None:
    # 便携包布局：<包根>/AppIcon.ico；仓库布局：<仓库>/docs/appicon/AppIcon.ico
    for cand in (PKG_ROOT / "AppIcon.ico", PKG_ROOT.parent / "docs" / "appicon" / "AppIcon.ico"):
        if cand.is_file():
            return cand
    return None


def _apply_window_icon() -> None:
    """给原生窗口的标题栏/任务栏设置软件图标（pywebview 在 Windows 下不支持直接传 icon）。"""
    icon = _find_icon()
    if icon is None:
        return
    try:
        import ctypes

        WM_SETICON, IMAGE_ICON = 0x0080, 1
        LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x0010, 0x0040
        for _ in range(100):  # 最多等 20 秒窗口出现
            hwnd = ctypes.windll.user32.FindWindowW(None, APP_TITLE)
            if hwnd:
                hicon = ctypes.windll.user32.LoadImageW(
                    None, str(icon), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
                )
                if hicon:
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)
                return
            time.sleep(0.2)
    except Exception:
        log("设置窗口图标失败（不影响使用）：\n" + traceback.format_exc())


def open_native_window(url: str) -> bool:
    """首选：pywebview + WebView2 原生窗口——独立软件观感，无浏览器痕迹。"""
    try:
        import webview
    except Exception:
        log("pywebview 不可用，退回 Edge 应用模式：\n" + traceback.format_exc())
        return False
    try:
        import ctypes

        # 独立 AppUserModelID：任务栏不与其他 Python 程序混组
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MoshangOA.App")
    except Exception:
        pass
    webview.create_window(APP_TITLE, url, width=1360, height=860, min_size=(960, 640))
    threading.Thread(target=_apply_window_icon, daemon=True).start()
    log("用原生窗口（WebView2）打开")
    # private_mode=False + storage_path：localStorage 持久化（记住的 API Key 不丢）
    webview.start(private_mode=False, storage_path=str(PKG_ROOT / "webview-profile"))
    log("窗口已关闭，退出")
    return True


def main() -> None:
    log("启动器开始运行")
    if not port_in_use(PORT):
        threading.Thread(target=run_server, daemon=True).start()
        log("后端线程已拉起")
    else:
        log("端口 8017 已有后端在跑，直接复用")
    wait_ready()
    log("后端就绪")

    url = f"http://{HOST}:{PORT}/"
    if open_native_window(url):
        return
    edge = find_edge()
    if edge is not None:
        # 独立 user-data-dir：①强制新开 Edge 进程，窗口关闭时本脚本才能感知退出；
        # ②localStorage（记住的 API Key）独立持久化，不与日常浏览混用
        profile = PKG_ROOT / "edge-profile"
        log(f"用 Edge 应用模式打开窗口：{edge}")
        subprocess.run(
            [
                str(edge),
                f"--app={url}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1360,860",
            ],
            check=False,
        )
        log("窗口已关闭，退出")
    else:
        import webbrowser

        log("未找到 Edge，退回默认浏览器打开（后端将常驻，关浏览器不会退出）")
        webbrowser.open(url)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("启动失败：\n" + traceback.format_exc())
        raise
