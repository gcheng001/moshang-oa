#!/bin/bash
# 在 macOS 上组装 Windows 便携包：内嵌 Python + win_amd64 wheels + 后端 + 前端 dist
# 产出：windows/dist/MoshangOA-Win-<日期>.zip（并复制到 ~/Desktop）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$ROOT/windows/cache"
OUT="$ROOT/windows/dist"
PKG="$OUT/MoshangOA-Win"
PIP="$ROOT/backend/.venv/bin/pip"

PY_VER="3.12.10"
PY_TAG="312"
EMBED_ZIP="$CACHE/python-$PY_VER-embed-amd64.zip"
WHEELS="$CACHE/wheels"

echo "==> 1/6 前端打包"
(cd "$ROOT/frontend" && npm run build >/dev/null)

echo "==> 2/6 下载 Windows 内嵌版 Python ${PY_VER} (有缓存则跳过)"
mkdir -p "$CACHE" "$WHEELS" "$OUT"
if [ ! -f "$EMBED_ZIP" ]; then
  curl -fL --retry 3 -o "$EMBED_ZIP" \
    "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-embed-amd64.zip"
fi

echo "==> 3/6 解析并下载本次唯一的 win_amd64 依赖集"
# 不能把历次解析结果混在一起解压；旧缓存曾同时含 anyio 4.14.1/4.14.2，
# 会让最终运行环境取决于文件遍历顺序。pip 自身下载缓存仍会复用。
rm -rf "$WHEELS"
mkdir -p "$WHEELS"
"$PIP" download --quiet --dest "$WHEELS" \
  --platform win_amd64 --python-version "$PY_TAG" --implementation cp \
  --only-binary=:all: \
  "fastapi==0.139.0" "uvicorn==0.50.2" "requests==2.34.2" "colorama" "keyring>=25" \
  "pywin32-ctypes>=0.2"
# pip evaluates pystray's macOS-only optional dependency against this Mac host
# even when downloading Windows wheels, which makes its normal resolver fail.
# The Windows runtime needs exactly pystray + Pillow + six, so fetch those
# binary/pure wheels explicitly.
"$PIP" download --quiet --dest "$WHEELS" \
  --platform win_amd64 --python-version "$PY_TAG" --implementation cp \
  --only-binary=:all: --no-deps "pystray==0.19.5" "pillow>=10" "six>=1.16"
# pywebview 的发布元数据会按 Mac 主机错误解析 pyobjc；跨平台下载时
# 显式列出 Windows 依赖，proxy_tools 是纯 Python 源包，现场构建 wheel。
"$PIP" download --quiet --dest "$WHEELS" \
  --platform win_amd64 --python-version "$PY_TAG" --implementation cp \
  --only-binary=:all: --no-deps "pywebview==6.2.1"
"$PIP" download --quiet --dest "$WHEELS" \
  --platform win_amd64 --python-version "$PY_TAG" --implementation cp \
  --only-binary=:all: \
  "pythonnet==3.0.5" "bottle==0.13.4" "typing_extensions>=4.13"
"$PIP" wheel --quiet --no-deps --wheel-dir "$WHEELS" "proxy_tools==0.1.0"

echo "==> 4/6 组装包目录"
rm -rf "$PKG"
mkdir -p "$PKG/python" "$PKG/app/backend" "$PKG/app/frontend"
unzip -q "$EMBED_ZIP" -d "$PKG/python"
# 开启 site-packages（内嵌版默认 ._pth 不含）
printf 'python%s.zip\n.\nLib\\site-packages\n' "$PY_TAG" > "$PKG/python/python$PY_TAG._pth"
SITE="$PKG/python/Lib/site-packages"
mkdir -p "$SITE"
for whl in "$WHEELS"/*.whl; do
  unzip -qo "$whl" -d "$SITE"
done

cp -R "$ROOT/backend/app" "$PKG/app/backend/app"
find "$PKG/app/backend/app" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
cp "$ROOT/windows/serve_win.py" "$PKG/app/backend/serve_win.py"
cp -R "$ROOT/frontend/dist" "$PKG/app/frontend/dist"
cp "$ROOT/windows/start.bat" "$PKG/start.bat"
# 仓库历史中批处理行尾并不统一；交付包统一成 cmd 最稳妥的 CRLF。
perl -pi -e 's/\r?\n/\r\n/g' "$PKG/start.bat"
cp "$ROOT/docs/appicon/AppIcon.ico" "$PKG/AppIcon.ico"
# README 带 BOM，保证老版记事本正常显示中文
printf '\xef\xbb\xbf' > "$PKG/README.txt"
cat "$ROOT/windows/README.txt" >> "$PKG/README.txt"

echo "==> 5/6 自检"
test -f "$PKG/python/pythonw.exe" || { echo "缺 pythonw.exe"; exit 1; }
test -f "$SITE/fastapi/__init__.py" || { echo "缺 fastapi"; exit 1; }
test -f "$SITE/uvicorn/__init__.py" || { echo "缺 uvicorn"; exit 1; }
test -f "$SITE/requests/__init__.py" || { echo "缺 requests"; exit 1; }
test -f "$SITE/keyring/__init__.py" || { echo "缺 keyring"; exit 1; }
test -f "$SITE/pystray/__init__.py" || { echo "缺 pystray"; exit 1; }
test -f "$SITE/webview/__init__.py" || { echo "缺 pywebview"; exit 1; }
test -f "$SITE/pythonnet/__init__.py" || { echo "缺 pythonnet"; exit 1; }
ls "$SITE"/pydantic_core/_pydantic_core*.pyd >/dev/null || { echo "缺 pydantic_core 的 win pyd"; exit 1; }
test -f "$PKG/app/frontend/dist/index.html" || { echo "缺前端 dist"; exit 1; }
test -f "$PKG/app/backend/app/main.py" || { echo "缺后端代码"; exit 1; }
test -f "$PKG/AppIcon.ico" || { echo "缺应用图标"; exit 1; }
"$ROOT/backend/.venv/bin/python" - "$SITE" <<'PY'
import pathlib, re, sys

site = pathlib.Path(sys.argv[1])
seen = {}
duplicates = []
for item in site.glob("*.dist-info"):
    name = re.sub(r"[-_.]+", "-", item.name.rsplit("-", 1)[0]).lower()
    if name in seen:
        duplicates.append((name, seen[name].name, item.name))
    seen[name] = item
if duplicates:
    raise SystemExit(f"依赖包存在重复版本: {duplicates}")
PY

echo "==> 6/6 压缩"
STAMP="$(date +%Y%m%d)"
ZIP="$OUT/MoshangOA-Win-$STAMP.zip"
rm -f "$ZIP"
(cd "$OUT" && zip -qr "$(basename "$ZIP")" "MoshangOA-Win")
cp -f "$ZIP" "$HOME/Desktop/" 2>/dev/null || true
echo "完成：$ZIP"
du -sh "$ZIP" | awk '{print "包大小: " $1}'
