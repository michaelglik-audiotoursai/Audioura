"""
test_local734_per_store_verify.py — LOCAL-734: per-platform purchase
verification ("per_store") and the shared _verifier_for helper.

per_store lets ONE server verify real Apple sandbox purchases from the iPhone
AND accept a TEST PURCHASE (store='stub') from a sideloaded Android build at the
same time, choosing the backend by the request's `store`. The three original
modes ('stub' | 'apple' | 'google') must keep working EXACTLY as before.

These tests are PURE (no database): every purchase path's backend SELECTION is
decided by entitlements_api._verifier_for, and the stub/refusal branches of the
three verify functions (level, tour, pass) return without touching the DB. The
/purchases/mode endpoint reports IAP_VERIFY_MODE and the per-platform answer
with no DB access. The DB-backed full-route red test lives in
test_local734_per_store_route.py (audiotours_test).

Covers the ticket's test list:
  * per_store + store=apple  -> the Apple verifier is called (JWS check mocked);
  * per_store + store=stub WITH the flag -> granted; WITHOUT the flag -> refused;
  * per_store + store=google without a service account -> refused, unconfigured;
  * every purchase path (level, tour, pass) resolves its backend through the
    SAME _verifier_for helper (patching it flips all three);
  * /purchases/mode shape for stub / apple / google / per_store;
  * RED TEST: with IAP_ALLOW_STUB_STORE unset, a store=stub purchase is refused
    on every path — the assertion fails if any path grants.
"""

import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_UT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
if _UT_DIR not in sys.path:
    sys.path.insert(0, _UT_DIR)


def _load(mod_name, file_name):
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(_UT_DIR, file_name))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ea():
    """A fresh entitlements_api module per test, so flipping IAP_VERIFY_MODE /
    IAP_ALLOW_STUB_STORE never leaks between tests."""
    mod = _load("entitlements_api", "entitlements_api.py")
    mod.API_KEY = ""
    mod.IAP_VERIFY_MODE = "apple"
    mod.IAP_ALLOW_STUB_STORE = False
    # No Google service account unless a test injects one.
    mod._GOOGLE_API_CLIENT_OVERRIDE = None
    mod.GOOGLE_PLAY_SA_JSON = ""
    return mod


@pytest.fixture()
def ca(ea):
    """communities_api sharing the SAME entitlements_api instance (so its
    _resolve_verify_mode delegates to the helper this test configured)."""
    mod = _load("communities_api", "communities_api.py")
    mod.API_KEY = ""
    mod.IAP_VERIFY_MODE = "apple"
    return mod


# ───────────────────────────────────────────────────────────────────────────
# 1. _verifier_for — the single backend selector
# ───────────────────────────────────────────────────────────────────────────
def test_original_modes_pass_through_unchanged(ea):
    for mode in ("stub", "apple", "google"):
        ea.IAP_VERIFY_MODE = mode
        # Whatever the request store, the three original modes resolve to
        # themselves (the verify functions reject a mismatched store later).
        assert ea._verifier_for("apple") == mode
        assert ea._verifier_for("google") == mode
        assert ea._verifier_for("stub") == mode


def test_per_store_apple_resolves_to_apple(ea):
    ea.IAP_VERIFY_MODE = "per_store"
    assert ea._verifier_for("apple") == "apple"


def test_per_store_stub_requires_flag(ea):
    ea.IAP_VERIFY_MODE = "per_store"
    ea.IAP_ALLOW_STUB_STORE = False
    assert ea._verifier_for("stub") == ea._STUB_STORE_NOT_ALLOWED
    ea.IAP_ALLOW_STUB_STORE = True
    assert ea._verifier_for("stub") == "stub"


def test_per_store_google_needs_service_account(ea):
    ea.IAP_VERIFY_MODE = "per_store"
    # No SA configured -> refuse, never grant.
    assert ea._verifier_for("google") == ea._GOOGLE_NOT_CONFIGURED
    # A fake Google client makes it resolve to the google backend.
    ea._GOOGLE_API_CLIENT_OVERRIDE = object()
    assert ea._verifier_for("google") == "google"


def test_per_store_unknown_store_refused(ea):
    ea.IAP_VERIFY_MODE = "per_store"
    assert ea._verifier_for("paypal") == ea._STUB_STORE_NOT_ALLOWED


# ───────────────────────────────────────────────────────────────────────────
# 2. per_store + store=apple calls the Apple verifier (JWS check mocked)
# ───────────────────────────────────────────────────────────────────────────
def test_per_store_apple_invokes_apple_verifier(ea, monkeypatch):
    ea.IAP_VERIFY_MODE = "per_store"

    called = {}

    class _Verified:
        transaction_id = "apple-txn-xyz"

    def _fake_verify_signed_transaction(signed, **kwargs):
        called["args"] = kwargs
        called["signed"] = signed
        return _Verified()

    # The verify functions import apple_jws_verifier lazily; inject a fake.
    import types
    fake_mod = types.ModuleType("apple_jws_verifier")
    fake_mod.verify_signed_transaction = _fake_verify_signed_transaction
    fake_mod.JwsVerificationError = type("JwsVerificationError", (Exception,), {"code": ""})
    monkeypatch.setitem(sys.modules, "apple_jws_verifier", fake_mod)
    monkeypatch.setattr(ea, "_load_apple_root_ca", lambda: b"ROOT")

    res = ea.verify_purchase("apple", "client-txn", "l3_pack_10",
                             signed_transaction="JWS")
    assert res.ok is True
    assert res.raw_status == "apple_verified:apple-txn-xyz"
    # The Apple verifier really was called with the Apple expectations.
    assert called["signed"] == "JWS"
    assert called["args"]["required_type"] == "Consumable"


# ───────────────────────────────────────────────────────────────────────────
# 3. Every path routes its backend through the SAME _verifier_for helper
# ───────────────────────────────────────────────────────────────────────────
def test_all_paths_consult_the_shared_helper(ea, ca, monkeypatch):
    """Patch _verifier_for to a sentinel and prove each verify function asked
    it (so there is no copy-pasted mode branching left in any path)."""
    ea.IAP_VERIFY_MODE = "per_store"
    seen = []

    def _spy(store):
        seen.append(store)
        return "stub"  # make each path take the no-DB stub branch

    monkeypatch.setattr(ea, "_verifier_for", _spy)

    # Level + tour live in entitlements_api and call _verifier_for directly.
    assert ea.verify_purchase("stub", "t1", "l3_pack_10").ok is True
    assert ea._verify_tour_signed("stub", "t2", "audioura.tour.usd5", None).ok is True
    # Pass lives in communities_api and delegates to the SAME helper via
    # _resolve_verify_mode -> entitlements_api._verifier_for.
    ok, raw = ca._verify_pass_signed("stub", "t3", "audioura.pass.usd5", None)
    assert ok is True and raw == "stub_verified"

    # All three paths consulted the shared helper.
    assert seen == ["stub", "stub", "stub"]


# ───────────────────────────────────────────────────────────────────────────
# 4. per_store + store=stub WITH / WITHOUT the flag, across every path
# ───────────────────────────────────────────────────────────────────────────
def _stub_results(ea, ca):
    """(level, tour, pass) VerificationResult/ok for a store=stub purchase."""
    level = ea.verify_purchase("stub", "txn", "l3_pack_10")
    tour = ea._verify_tour_signed("stub", "txn", "audioura.tour.usd5", None)
    pass_ok, pass_raw = ca._verify_pass_signed("stub", "txn", "audioura.pass.usd5", None)
    return level, tour, (pass_ok, pass_raw)


def test_per_store_stub_granted_with_flag(ea, ca):
    ea.IAP_VERIFY_MODE = "per_store"
    ca.IAP_VERIFY_MODE = "per_store"
    ea.IAP_ALLOW_STUB_STORE = True
    level, tour, (pass_ok, pass_raw) = _stub_results(ea, ca)
    assert level.ok is True and level.raw_status == "stub_verified"
    assert tour.ok is True and tour.raw_status == "stub_verified"
    assert pass_ok is True and pass_raw == "stub_verified"


def test_red_per_store_stub_refused_without_flag(ea, ca):
    """RED TEST: with IAP_ALLOW_STUB_STORE unset (default), a store=stub purchase
    must be REFUSED on every path. The test fails if any path grants."""
    ea.IAP_VERIFY_MODE = "per_store"
    ca.IAP_VERIFY_MODE = "per_store"
    ea.IAP_ALLOW_STUB_STORE = False  # the default
    level, tour, (pass_ok, pass_raw) = _stub_results(ea, ca)
    # Refused, never granted.
    assert level.ok is False, "LEVEL granted a stub purchase without the flag!"
    assert level.raw_status == ea._STUB_STORE_NOT_ALLOWED
    assert tour.ok is False, "TOUR granted a stub purchase without the flag!"
    assert tour.raw_status == ea._STUB_STORE_NOT_ALLOWED
    assert pass_ok is False, "PASS granted a stub purchase without the flag!"
    assert pass_raw == "stub_store_not_allowed"


# ───────────────────────────────────────────────────────────────────────────
# 5. per_store + store=google without a service account -> refused, nothing granted
# ───────────────────────────────────────────────────────────────────────────
def test_per_store_google_unconfigured_refused(ea, ca):
    ea.IAP_VERIFY_MODE = "per_store"
    ca.IAP_VERIFY_MODE = "per_store"
    # No SA override and no SA path -> _google_api_client() is None.
    level = ea.verify_purchase("google", "txn", "l3_pack_10",
                               signed_transaction="token")
    tour = ea._verify_tour_signed("google", "txn", "audioura.tour.usd5", "token")
    pass_ok, pass_raw = ca._verify_pass_signed("google", "txn",
                                               "audioura.pass.usd5", "token")
    assert level.ok is False and level.unconfigured is True
    assert level.raw_status == ea._GOOGLE_NOT_CONFIGURED
    assert tour.ok is False and tour.unconfigured is True
    assert pass_ok is False and pass_raw == "google_verify_unconfigured"


# ───────────────────────────────────────────────────────────────────────────
# 6. /purchases/mode shape for each mode
# ───────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(ea):
    # The route's auth gate fails CLOSED (503) when GATEWAY_API_KEY is empty
    # unless the local-only bypass is on — the same env the 699 suite uses.
    os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    return app.test_client()


def _mode(client):
    r = client.get("/purchases/mode")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_mode_shape_stub(ea, client):
    ea.IAP_VERIFY_MODE = "stub"
    j = _mode(client)
    assert j["mode"] == "stub"
    assert j["stub"] is True and j["verifies_real"] is False
    assert j["platforms"] == {"ios": "stub", "android": "stub"}


def test_mode_shape_apple(ea, client):
    ea.IAP_VERIFY_MODE = "apple"
    j = _mode(client)
    assert j["mode"] == "apple"
    assert j["stub"] is False and j["verifies_real"] is True
    assert j["platforms"] == {"ios": "apple", "android": "apple"}


def test_mode_shape_google(ea, client):
    ea.IAP_VERIFY_MODE = "google"
    j = _mode(client)
    assert j["mode"] == "google"
    assert j["platforms"] == {"ios": "google", "android": "google"}


def test_mode_shape_per_store_stub_android(ea, client):
    """The Mac Mini local stack: per_store, stub allowed, no Play SA ->
    ios drives Apple, android runs the TEST PURCHASE (stub). Legacy stub field
    stays FALSE so old apps don't treat it as a global TEST PURCHASE server."""
    ea.IAP_VERIFY_MODE = "per_store"
    ea.IAP_ALLOW_STUB_STORE = True
    ea._GOOGLE_API_CLIENT_OVERRIDE = None
    ea.GOOGLE_PLAY_SA_JSON = ""
    j = _mode(client)
    assert j["mode"] == "per_store"
    assert j["stub"] is False and j["verifies_real"] is True
    assert j["platforms"] == {"ios": "apple", "android": "stub"}


def test_mode_shape_per_store_google_android_when_sa_present(ea, client):
    """per_store with a Play service account -> android drives real Play billing."""
    ea.IAP_VERIFY_MODE = "per_store"
    ea.IAP_ALLOW_STUB_STORE = True  # SA wins over the stub flag on Android.
    ea._GOOGLE_API_CLIENT_OVERRIDE = object()
    j = _mode(client)
    assert j["platforms"] == {"ios": "apple", "android": "google"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
