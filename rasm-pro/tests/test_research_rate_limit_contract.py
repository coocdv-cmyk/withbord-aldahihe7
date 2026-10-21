"""Regression: when the source says «slow down», the engine says so.

Wikimedia answers **429** when the research asks faster than the etiquette
allows.  The old client retried three times in under two seconds and then
swallowed the error — so a whole entity came back with *no assets* and the
report looked like a complete search.  That is the worst kind of failure: a
silently incomplete result.

Now: the client paces its calls, waits 2 s → 8 s → 20 s on a 429, raises
``RateLimited``, and the research records the entity as **rate-limited**
instead of pretending nothing was found.
"""
from __future__ import annotations

from engine.research.http import HttpClient, RateLimited


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_a_429_is_raised_as_rate_limited(monkeypatch):
    client = HttpClient("rasm-pro/test", min_interval=0.0)
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return _Response(429)

    monkeypatch.setattr(client.session, "request", fake_request)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    try:
        client.get_json("https://example.invalid/api")
    except RateLimited:
        pass
    else:  # pragma: no cover - the guard is the point
        raise AssertionError("a 429 must raise RateLimited")
    # three patient tries, then the failure is declared
    assert calls["n"] == 3


def test_the_client_paces_the_calls_to_one_host(monkeypatch):
    client = HttpClient("rasm-pro/test", min_interval=0.05)
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: slept.append(seconds))
    client._pace("https://a.example/x")
    client._pace("https://a.example/y")
    client._pace("https://b.example/z")
    # the second call to the same host waits; a different host does not
    assert len(slept) == 1, slept


def test_a_cached_answer_is_used_without_a_request(monkeypatch):
    client = HttpClient("rasm-pro/test", min_interval=0.0, cache=True)
    key = client._key("https://example.invalid/api", {"a": 1})
    client._write_cache(key, {"ok": True}, binary=False)
    called = {"n": 0}

    def fake_request(*args, **kwargs):
        called["n"] += 1
        return _Response(200, {"fresh": True})

    monkeypatch.setattr(client.session, "request", fake_request)
    data = client.get_json("https://example.invalid/api", {"a": 1})
    assert data == {"ok": True}
    assert called["n"] == 0
