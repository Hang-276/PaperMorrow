$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv-desktop"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Root ".pyinstaller-cache"

function Require-Command([string]$Name, [string]$Help) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name 未安装。$Help"
  }
}

Require-Command "py" "请安装 Python 3.11（含 Python Launcher）。"
Require-Command "npm" "请安装 Node.js 20 LTS。"
Require-Command "node" "请安装 Node.js 20 LTS。"

if (-not (Test-Path $Venv)) { py -3.11 -m venv $Venv }
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e $Root
& $Python -m pip install -r (Join-Path $Root "requirements-desktop.txt")

Push-Location (Join-Path $Root "frontend")
npm ci
npm run build
Pop-Location

Push-Location (Join-Path $Root "presentation-studio")
npm ci
npm run build
Pop-Location

& $Python (Join-Path $Root "desktop\make_icons.py")
& $Python -m PyInstaller --noconfirm --clean `
  --distpath (Join-Path $Root "desktop_dist") `
  --workpath (Join-Path $Root "desktop_build") `
  (Join-Path $Root "desktop\PaperMorrow.spec")

$AppDir = Join-Path $Root "desktop_dist\PaperMorrow"
$PortableZip = Join-Path $Root "desktop_dist\PaperMorrow-Windows-Portable.zip"
if (Test-Path $PortableZip) { Remove-Item $PortableZip -Force }
Compress-Archive -Path $AppDir -DestinationPath $PortableZip -CompressionLevel Optimal

$IsccCandidates = @(
  (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
  (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }
$Iscc = $IsccCandidates | Select-Object -First 1
if (-not $Iscc) {
  $IsccCommand = Get-Command "iscc" -ErrorAction SilentlyContinue
  if ($IsccCommand) { $Iscc = $IsccCommand.Source }
}
if (-not $Iscc) {
  throw "未找到 Inno Setup 6。请从 https://jrsoftware.org/isdl.php 安装后重试。"
}
& $Iscc "/DAppVersion=0.4.0" (Join-Path $Root "desktop\installer\PaperMorrow.iss")

Write-Host "安装器: $Root\desktop_dist\PaperMorrow-Windows-Setup.exe"
Write-Host "便携版: $PortableZip"
