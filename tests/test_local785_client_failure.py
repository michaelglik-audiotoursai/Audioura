#!/usr/bin/env python3
"""[LOCAL-785] POST /client-failure on user-api — validate, rate-limit, store.

Drives the real Flask route with failure_log.record monkeypatched to CAPTURE
the stored event (so no DB is needed), proving:
  * a valid report is stored (service='app', platform from body) and returns 200
    with the computed signature,
  * an empty report is 400, a non-JSON body is 400, an > 8 KB body is 413,
  * the per-user rate limit allows 20/hour then returns 429 and stores nothing.

Run: python3 -m pytest tests/test_local785_client_failure.py -q
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "user-tracking"))

# The user-api app needs a DATABASE_URL present to import cleanly; it is never
# connected to in these tests (record is monkeypatched).
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/db")

import app as user_api  # user-tracking/app.py


def _client():
    user_api.app.config["TESTING"] = True
    return user_api.app.test_client()


def _patch_capture(monkeypatch):
    captured = []

    def fake_record(**kw):
        captured.append(kw)
        return "sig0123456789abc"[:16]

    # The route calls the module-level _failure_log.record.
    monkeypatch.setattr(user_api._failure_log, "record", fake_record)
    return captured


def _reset_rate_limit():
    with user_api._client_failure_lock:
        user_api._client_failure_hits.clear()


def test_valid_report_is_stored(monkeypatch):
    _reset_rate_limit()
    captured = _patch_capture(monkeypatch)
    c = _client()
    r = c.post("/client-failure", json={
        "surface": "download", "message": "save failed",
        "platform": "android", "user_id": "USER-A", "error_code": "x",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "success"
    assert body["signature"]
    assert len(captured) == 1
    assert captured[0]["service"] == "app"
    assert captured[0]["platform"] == "android"
    assert captured[0]["surface"] == "download"
    assert captured[0]["user_id"] == "USER-A"


def test_empty_report_is_400(monkeypatch):
    _reset_rate_limit()
    captured = _patch_capture(monkeypatch)
    c = _client()
    r = c.post("/client-failure", json={"platform": "ios", "user_id": "USER-B"})
    assert r.status_code == 400
    assert captured == []


def test_non_json_body_is_400(monkeypatch):
    _reset_rate_limit()
    captured = _patch_capture(monkeypatch)
    c = _client()
    r = c.post("/client-failure", data="not json",
               content_type="application/json")
    assert r.status_code == 400
    assert captured == []


def test_oversized_body_is_413(monkeypatch):
    _reset_rate_limit()
    captured = _patch_capture(monkeypatch)
    c = _client()
    big = {"surface": "play", "message": "x" * 9000}
    r = c.post("/client-failure", json=big)
    assert r.status_code == 413
    assert captured == []


def test_rate_limit_20_per_user_then_429(monkeypatch):
    _reset_rate_limit()
    captured = _patch_capture(monkeypatch)
    c = _client()
    codes = []
    for _ in range(22):
        r = c.post("/client-failure", json={
            "surface": "play", "message": "boom", "user_id": "USER-RL"})
        codes.append(r.status_code)
    assert codes[:20] == [200] * 20
    assert codes[20] == 429 and codes[21] == 429
    # Only the 20 allowed reports were stored.
    assert len(captured) == 20


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
