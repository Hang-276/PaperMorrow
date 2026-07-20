from __future__ import annotations

from scripts import launcher


def test_existing_papermorrow_is_reused(monkeypatch):
    monkeypatch.setattr(launcher, "_is_port_free", lambda host, port: False)
    monkeypatch.setattr(launcher, "_is_papermorrow", lambda host, port: True)

    assert launcher._choose_port("127.0.0.1", 8000) == (8000, True)


def test_unrelated_port_conflict_uses_next_free_port(monkeypatch):
    monkeypatch.setattr(launcher, "_is_port_free", lambda host, port: port == 8001)
    monkeypatch.setattr(launcher, "_is_papermorrow", lambda host, port: False)

    assert launcher._choose_port("127.0.0.1", 8000) == (8001, False)


def test_port_range_exhaustion_is_clear(monkeypatch):
    monkeypatch.setattr(launcher, "_is_port_free", lambda host, port: False)
    monkeypatch.setattr(launcher, "_is_papermorrow", lambda host, port: False)

    try:
        launcher._choose_port("127.0.0.1", 8000, attempts=2)
    except RuntimeError as exc:
        assert "8000–8001" in str(exc)
    else:
        raise AssertionError("expected a clear port exhaustion error")
