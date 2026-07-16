"""办公助手 Windows 启动器。

启动本地 FastAPI 后端（端口 8017），然后用 Edge 应用模式打开独立窗口
（--app：无地址栏无标签页，观感与桌面应用一致，Win10/11 自带 Edge）。
关闭主窗口后保留系统托盘常驻：自动审批仍按账号开关和 10 分钟周期运行。
仅从托盘「退出办公助手」才停止本地后端。异常写入 logs/moshang_win.log。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

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

from app.local_server import is_expected_backend, port_in_use, wait_for_expected_backend

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


def run_server() -> None:
    try:
        import uvicorn

        uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
    except BaseException:
        # pythonw 无控制台，后端线程异常必须落日志，否则只见"启动超时"不见病因
        log("后端线程异常：\n" + traceback.format_exc())
        raise


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
    # 保留独立 WebView 资料目录，避免与日常浏览器资料混用。
    webview.start(private_mode=False, storage_path=str(PKG_ROOT / "webview-profile"))
    log("主窗口已关闭，转为托盘常驻")
    return True


def _open_in_edge(url: str) -> None:
    edge = find_edge()
    if edge is None:
        import webbrowser

        webbrowser.open(url)
        return
    profile = PKG_ROOT / "edge-profile"
    subprocess.Popen(
        [
            str(edge), f"--app={url}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "--window-size=1360,860",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_tray(url: str) -> threading.Thread | None:
    """Keep a visible, user-controllable process after the main window closes."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        log("系统托盘组件不可用，自动审批将在主窗口关闭后停止：\n" + traceback.format_exc())
        return None

    icon_path = _find_icon()
    if icon_path:
        image = Image.open(icon_path)
    else:
        image = Image.new("RGBA", (64, 64), (79, 70, 229, 255))
        ImageDraw.Draw(image).rectangle((18, 18, 46, 46), fill=(255, 255, 255, 255))

    def open_app(_icon, _item) -> None:
        _open_in_edge(url)

    def exit_app(icon, _item) -> None:
        log("用户从系统托盘退出办公助手")
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        "MoshangOA", image, APP_TITLE,
        menu=pystray.Menu(pystray.MenuItem("打开办公助手", open_app, default=True), pystray.MenuItem("退出办公助手", exit_app)),
    )
    thread = threading.Thread(target=icon.run, name="office-assistant-tray", daemon=False)
    thread.start()
    log("系统托盘已启动；关闭主窗口后自动审批继续运行")
    return thread


def main() -> None:
    log("启动器开始运行")
    if not port_in_use(HOST, PORT):
        threading.Thread(target=run_server, daemon=True).start()
        log("后端线程已拉起")
    elif not is_expected_backend(HOST, PORT):
        raise RuntimeError(f"端口 {PORT} 已被其他程序占用，请关闭占用程序后重试")
    else:
        log("已识别到同版本办公助手后端，直接复用")
    # Defender 首次扫描便携包可能很慢，Windows 冷启动最多等待 90 秒。
    wait_for_expected_backend(HOST, PORT, timeout=90.0)
    log("后端就绪")

    url = f"http://{HOST}:{PORT}/"
    tray = start_tray(url)
    if open_native_window(url):
        if tray is None:
            return
        # Keep FastAPI and its scheduler alive until the user explicitly exits from the tray.
        tray.join()
        return
    edge = find_edge()
    if edge is not None:
        # 独立 user-data-dir：①强制新开 Edge 进程，窗口关闭时本脚本才能感知退出；
        # ②独立资料目录，不与日常浏览混用
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
        log("窗口已关闭，托盘继续常驻")
        if tray is not None:
            tray.join()
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
