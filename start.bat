@echo off
setlocal
cd /d %~dp0

if not exist .venv-paper\Scripts\python.exe python -m venv .venv-paper
.venv-paper\Scripts\python.exe -c "import fastapi, sqlalchemy, httpx, apscheduler" 2>nul
if errorlevel 1 .venv-paper\Scripts\python.exe -m pip install -r requirements.txt
if not exist frontend\node_modules call npm --prefix frontend install
if not exist frontend\dist\index.html call npm --prefix frontend run build
if not exist presentation-studio\node_modules call npm --prefix presentation-studio install
if not exist presentation-studio\dist\src\cli.js call npm --prefix presentation-studio run build
.venv-paper\Scripts\python.exe main.py
