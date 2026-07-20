#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venv-paper/bin/python" ]; then
  python3 -m venv .venv-paper
fi

if ! .venv-paper/bin/python -c "import fastapi, sqlalchemy, httpx, apscheduler" >/dev/null 2>&1; then
  .venv-paper/bin/python -m pip install -e .
fi

if [ ! -d "frontend/node_modules" ]; then
  npm --prefix frontend install
fi

if [ ! -f "frontend/dist/index.html" ]; then
  npm --prefix frontend run build
fi

if [ ! -d "presentation-studio/node_modules" ]; then
  npm --prefix presentation-studio install
fi

if [ ! -f "presentation-studio/dist/src/cli.js" ]; then
  npm --prefix presentation-studio run build
fi

exec .venv-paper/bin/python scripts/launcher.py
