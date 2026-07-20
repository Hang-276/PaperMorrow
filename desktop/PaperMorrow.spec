# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import platform
import shutil

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SYSTEM = platform.system()
APP_VERSION = os.getenv("PAPERMORROW_BUILD_VERSION", "0.5.4")
ICON = ROOT / "desktop" / "icons" / ("PaperMorrow.icns" if SYSTEM == "Darwin" else "PaperMorrow.ico")
NODE = Path(shutil.which("node") or "")
if not NODE.is_file():
    raise SystemExit("Node.js 18+ is required to build the desktop package")

hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("webview")
    + [
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ]
)

a = Analysis(
    [str(ROOT / "desktop" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[(str(NODE), "runtime")],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
        (str(ROOT / "backend" / "prompts"), "backend/prompts"),
        (str(ROOT / "backend" / "cowork_skills"), "backend/cowork_skills"),
        (str(ROOT / "presentation-studio" / "dist"), "presentation-studio/dist"),
        (str(ROOT / "presentation-studio" / "node_modules"), "presentation-studio/node_modules"),
        (str(ROOT / "presentation-studio" / "package.json"), "presentation-studio"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook", "IPython"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PaperMorrow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PaperMorrow",
)

if SYSTEM == "Darwin":
    app = BUNDLE(
        coll,
        name="PaperMorrow.app",
        icon=str(ICON),
        bundle_identifier="io.papermorrow.desktop",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
        },
    )
