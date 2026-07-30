from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import desktop_app


def test_windows_user_data_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop_app.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert desktop_app.user_data_dir() == tmp_path / "PaperMorrow"


def test_wait_until_healthy_checks_expected_payload():
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/api/system/health"
            body = json.dumps({"status": "ok", "service": "PaperMorrow"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert desktop_app.wait_until_healthy(server.server_port, timeout=2) == {
            "status": "ok",
            "service": "PaperMorrow",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
