from __future__ import annotations

import json
import os
import socket
import threading
import urllib.error
import urllib.request
import webbrowser

import uvicorn


def _is_port_free(host: str, port: int) -> bool:
    """Check availability without terminating or taking over an existing process."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return True
    except OSError:
        return False


def _is_papermorrow(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/openapi.json", timeout=1.2) as response:
            payload = json.load(response)
        return payload.get("info", {}).get("title") == "PaperMorrow API"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _choose_port(host: str, preferred: int, attempts: int = 11) -> tuple[int, bool]:
    """Return (port, existing_papermorrow) while preserving unrelated services."""
    if not _is_port_free(host, preferred) and _is_papermorrow(host, preferred):
        return preferred, True
    for port in range(preferred, preferred + attempts):
        if _is_port_free(host, port):
            return port, False
    raise RuntimeError(f"端口 {preferred}–{preferred + attempts - 1} 均已被占用，请设置 APP_PORT 后重试。")


def run() -> None:
    host = os.getenv("APP_HOST", "127.0.0.1")
    preferred_port = int(os.getenv("APP_PORT", "8000"))
    port, existing = _choose_port(host, preferred_port)
    url = f"http://{host}:{port}"
    if existing:
        should_open = os.getenv("NO_BROWSER", "0") != "1"
        print(f"PaperMorrow 已在 {url} 运行" + ("，正在打开现有实例。" if should_open else "。"))
        if should_open:
            webbrowser.open(url)
        return
    if port != preferred_port:
        print(f"端口 {preferred_port} 已被其他程序占用，PaperMorrow 将改用 {port}。")
    if os.getenv("NO_BROWSER", "0") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
