from __future__ import annotations

import json
import os
import platform
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen


def user_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        root = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        root = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        root = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return root / "PaperMorrow"


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.3):
                return
        except OSError:
            time.sleep(.1)
    raise RuntimeError("PaperMorrow 本地服务启动超时")


def wait_until_healthy(port: int, timeout: float = 30.0) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/system/health", timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload == {"status": "ok", "service": "PaperMorrow"}:
                return payload
            last_error = RuntimeError(f"健康检查返回异常: {payload!r}")
        except Exception as exc:
            last_error = exc
        time.sleep(.2)
    raise RuntimeError("PaperMorrow 健康检查超时") from last_error


def write_smoke_result(data_dir: Path, health: dict[str, str]) -> None:
    marker = os.getenv("PAPERMORROW_SMOKE_MARKER")
    if not marker:
        return
    result = {
        **health,
        "platform": platform.platform(),
        "python": sys.version,
        "data_dir": str(data_dir),
        "database_created": (data_dir / "paper_radar.db").is_file(),
    }
    marker_path = Path(marker)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PAPERMORROW_DATA_DIR", str(data_dir))
    os.environ.setdefault("NO_BROWSER", "1")

    import uvicorn
    import webview

    port = available_port()
    config = uvicorn.Config(
        "backend.app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, name="papermorrow-server", daemon=True)
    server_thread.start()
    try:
        wait_until_ready(port)
        if os.getenv("PAPERMORROW_SMOKE_TEST") == "1":
            health = wait_until_healthy(port)
            write_smoke_result(data_dir, health)
            return

        webview.create_window(
            "PaperMorrow",
            f"http://127.0.0.1:{port}",
            width=1440,
            height=900,
            min_size=(1050, 680),
            background_color="#101412",
            text_select=True,
        )
        webview.start(debug=False, private_mode=False)
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
