#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv-paper/bin/python}"
export PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller-cache"

cd "$ROOT/frontend"
npm run build
cd "$ROOT/presentation-studio"
if [ ! -d "node_modules" ]; then
  npm ci
fi
npm run build
cd "$ROOT"
"$PYTHON" desktop/make_icons.py
"$PYTHON" -m PyInstaller --noconfirm --clean \
  --distpath "$ROOT/desktop_dist" \
  --workpath "$ROOT/desktop_build" \
  "$ROOT/desktop/PaperMorrow.spec"

codesign --force --deep --sign - "$ROOT/desktop_dist/PaperMorrow.app"

DMG_ROOT="$ROOT/desktop_build/dmg"
DMG_PATH="$ROOT/desktop_dist/PaperMorrow-macOS.dmg"
rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
cp -R "$ROOT/desktop_dist/PaperMorrow.app" "$DMG_ROOT/PaperMorrow.app"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$DMG_PATH"
hdiutil create -volname "PaperMorrow" -srcfolder "$DMG_ROOT" -ov -format UDZO "$DMG_PATH"

echo "macOS app: $ROOT/desktop_dist/PaperMorrow.app"
echo "macOS installer: $DMG_PATH"
