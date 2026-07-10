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

echo "==> 3/6 下载 win_amd64 依赖 wheels（有缓存则增量）"
"$PIP" download --quiet --dest "$WHEELS" \
  --platform win_amd64 --python-version "$PY_TAG" --implementation cp \
  --only-binary=:all: \
  "fastapi==0.139.0" "uvicorn==0.50.2" "requests==2.34.2" "colorama"

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
# README 带 BOM，保证老版记事本正常显示中文
printf '\xef\xbb\xbf' > "$PKG/README.txt"
cat "$ROOT/windows/README.txt" >> "$PKG/README.txt"

echo "==> 5/6 自检"
test -f "$PKG/python/pythonw.exe" || { echo "缺 pythonw.exe"; exit 1; }
test -f "$SITE/fastapi/__init__.py" || { echo "缺 fastapi"; exit 1; }
test -f "$SITE/uvicorn/__init__.py" || { echo "缺 uvicorn"; exit 1; }
test -f "$SITE/requests/__init__.py" || { echo "缺 requests"; exit 1; }
ls "$SITE"/pydantic_core/_pydantic_core*.pyd >/dev/null || { echo "缺 pydantic_core 的 win pyd"; exit 1; }
test -f "$PKG/app/frontend/dist/index.html" || { echo "缺前端 dist"; exit 1; }
test -f "$PKG/app/backend/app/main.py" || { echo "缺后端代码"; exit 1; }

echo "==> 6/6 压缩"
STAMP="$(date +%Y%m%d)"
ZIP="$OUT/MoshangOA-Win-$STAMP.zip"
rm -f "$ZIP"
(cd "$OUT" && zip -qr "$(basename "$ZIP")" "MoshangOA-Win")
cp -f "$ZIP" "$HOME/Desktop/" 2>/dev/null || true
echo "完成：$ZIP"
du -sh "$ZIP" | awk '{print "包大小: " $1}'
