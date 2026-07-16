#!/bin/bash
# Build a self-contained macOS application from the current source tree.
# The result is intentionally not signed/notarized: local test distribution
# only.  It never replaces /Applications automatically.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
VERSION="$(PYTHONPATH="$ROOT/backend" "$PY" -c 'from app.local_server import APP_VERSION; print(APP_VERSION)')"
DIST="$ROOT/macos/dist"
WORK="$ROOT/macos/.build"

echo "==> 1/4 Build frontend"
(cd "$ROOT/frontend" && npm run build >/dev/null)

echo "==> 2/4 Check packaging dependencies"
"$PY" -c 'import PyInstaller, webview, keyring' 2>/dev/null || {
  echo "Missing PyInstaller/webview/keyring in backend/.venv" >&2
  exit 1
}

echo "==> 3/4 Build universal local app"
rm -rf "$DIST" "$WORK"
mkdir -p "$DIST" "$WORK"
cd "$ROOT/backend"
"$PY" -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name "办公助手" \
  --icon "$ROOT/docs/appicon/AppIcon.icns" \
  --paths "$ROOT/backend" \
  --add-data "$ROOT/frontend/dist:frontend/dist" \
  --collect-all webview \
  --collect-all keyring \
  --osx-bundle-identifier "com.moshang.oa" \
  --distpath "$DIST" --workpath "$WORK/work" --specpath "$WORK/spec" \
  "$ROOT/backend/desktop.py"

echo "==> 4/4 Verify app"
APP="$DIST/办公助手.app"
test -x "$APP/Contents/MacOS/办公助手"
test -f "$APP/Contents/Resources/frontend/dist/index.html"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist"
if /usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$APP/Contents/Info.plist" >/dev/null 2>&1; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP/Contents/Info.plist"
else
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$APP/Contents/Info.plist"
fi
# This is a local test build, so use an ad-hoc signature after modifying the
# bundle metadata. Distribution outside this Mac will later need Developer ID
# signing and notarization.
codesign --force --deep --sign - "$APP" >/dev/null
plutil -lint "$APP/Contents/Info.plist" >/dev/null
echo "Done: $APP"
