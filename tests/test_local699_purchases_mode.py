"""
test_local699_purchases_mode.py — LOCAL-699: the GET /purchases/mode endpoint
that tells the app how this server verifies purchases, so Buy buttons on BOTH
platforms pick the right path (TEST PURCHASE on a stub server, real StoreKit/
Play billing on an apple/google server).

No database is needed: the endpoint only reports IAP_VERIFY_MODE. The harness is
the lightweight half of the LOCAL-696 pattern — load entitlements_api.py via
importlib, register its blueprint on a Flask test client, and flip
IAP_VERIFY_MODE on the loaded module.

Covers:
  * stub mode   -> {"stub": true,  "verifies_real": false, "mode": "stub"}
  * apple mode  -> {"stub": false, "verifies_real": true,  "mode": "apple"}
  * google mode -> {"stub": false, "verifies_real": true,  "mode": "google"}
  * auth: with a real GATEWAY_API_KEY and no header -> 401; wrong key -> 401;
    correct key -> 200.
"""

import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
    """Own and restore the entitlements env this module mutates."""
    keys = ("GATEWAY_API_KEY", "IAP_VERIFY_MODE", "ALLOW_UNAUTHENTICATED_ENTITLEMENTS")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["GATEWAY_API_KEY"] = ""
    os.environ["IAP_VERIFY_MODE"] = "stub"
    os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture(scope="module")
def ea():
    """Load entitlements_api as its own module (no DB access on this path)."""
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    if ut_dir not in sys.path:
        sys.path.insert(0, ut_dir)
    spec = importlib.util.spec_from_file_location(
        "entitlements_api_699", os.path.join(ut_dir, "entitlements_api.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["entitlements_api_699"] = mod
    spec.loader.exec_module(mod)
    mod.API_KEY = ""
    return mod


@pytest.fixture(scope="module")
def client(ea):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    return app.test_client()


def test_stub_mode_reports_stub_true(ea, client):
    ea.IAP_VERIFY_MODE = "stub"
    ea.API_KEY = ""
    r = client.get("/purchases/mode")
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j["mode"] == "stub"
    assert j["stub"] is True
    assert j["verifies_real"] is False


def test_apple_mode_reports_stub_false(ea, client):
    ea.IAP_VERIFY_MODE = "apple"
    ea.API_KEY = ""
    r = client.get("/purchases/mode")
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j["mode"] == "apple"
    assert j["stub"] is False
    assert j["verifies_real"] is True


def test_google_mode_reports_stub_false(ea, client):
    ea.IAP_VERIFY_MODE = "google"
    ea.API_KEY = ""
    r = client.get("/purchases/mode")
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j["mode"] == "google"
    assert j["stub"] is False
    assert j["verifies_real"] is True


def test_auth_enforced_when_key_configured(ea, client):
    """With a real key and no/ wrong X-API-Key header -> 401; correct key -> 200."""
    ea.IAP_VERIFY_MODE = "stub"
    ea.API_KEY = "secret-699"
    try:
        # No header.
        assert client.get("/purchases/mode").status_code == 401
        # Wrong header.
        assert client.get(
            "/purchases/mode", headers={"X-API-Key": "nope"}).status_code == 401
        # Correct header.
        r = client.get("/purchases/mode", headers={"X-API-Key": "secret-699"})
        assert r.status_code == 200
        assert r.get_json()["stub"] is True
    finally:
        ea.API_KEY = ""
