#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv-paper/bin/python}"
export PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller-cache"

cd "$ROOT/frontend"
npm run build
cd "$ROOT"
"$PYTHON" desktop/make_icons.py
"$PYTHON" -m PyInstaller --noconfirm --clean \
  --distpath "$ROOT/desktop_dist" \
  --workpath "$ROOT/desktop_build" \
  "$ROOT/desktop/PaperMorrow.spec"

echo "macOS app: $ROOT/desktop_dist/PaperMorrow.app"
