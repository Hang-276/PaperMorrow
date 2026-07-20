from __future__ import annotations

import os
import platform
import socket
import threading
import time
from pathlib import Path


class DesktopBridge:
    """Minimal native picker bridge; it never reads selected content itself."""

    def choose_folder(self) -> str:
        import webview
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return str(result[0]) if result else ""

    def choose_files(self) -> list[str]:
        import webview
        result = webview.windows[0].create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True)
        return [str(item) for item in (result or [])]


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
    wait_until_ready(port)

    webview.create_window(
        "PaperMorrow",
        f"http://127.0.0.1:{port}",
        width=1440,
        height=900,
        min_size=(1050, 680),
        background_color="#101412",
        text_select=True,
        js_api=DesktopBridge(),
    )
    try:
        webview.start(debug=False, private_mode=False)
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
