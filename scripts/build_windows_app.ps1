$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv-desktop"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Root ".pyinstaller-cache"

if (-not (Test-Path $Venv)) { py -3.11 -m venv $Venv }
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e $Root
& $Python -m pip install -r (Join-Path $Root "requirements-desktop.txt")

Push-Location (Join-Path $Root "frontend")
npm install
npm run build
Pop-Location

& $Python (Join-Path $Root "desktop\make_icons.py")
& $Python -m PyInstaller --noconfirm --clean `
  --distpath (Join-Path $Root "desktop_dist") `
  --workpath (Join-Path $Root "desktop_build") `
  (Join-Path $Root "desktop\PaperMorrow.spec")

Write-Host "Windows app: $Root\desktop_dist\PaperMorrow\PaperMorrow.exe"
