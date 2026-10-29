"""
test_local807_subscription_routes.py — LOCAL-807: the Flask routes for the
subscription endpoints, exercised WITHOUT a database (only the pre-DB branches:
the Google gate, malformed bodies, the unauthorized/auth gate). The DB-backed
apply path is covered by the FakeCursor tests in test_local807_subscriptions.py.

Loads a FRESH entitlements_api module per test (same importlib pattern as
test_local734_per_store_verify) so toggling GOOGLE_SUBS_ENABLED never leaks.

Run:
    cd user-tracking && python3 -m pytest test_local807_subscription_routes.py -q
"""

import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load(mod_name, file_name):
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ea():
    mod = _load('entitlements_api', 'entitlements_api.py')
    mod.API_KEY = ''
    mod.GOOGLE_SUBS_ENABLED = False
    mod._GOOGLE_API_CLIENT_OVERRIDE = None
    mod.GOOGLE_PLAY_SA_JSON = ''
    return mod


@pytest.fixture()
def client(ea):
    os.environ['ALLOW_UNAUTHENTICATED_ENTITLEMENTS'] = 'true'
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    return app.test_client()


# ───────────────────────────────────────────────────────────────────────────
# Google RTDN gate — disabled by default (503), never calls Play.
# ───────────────────────────────────────────────────────────────────────────
def test_google_rtdn_disabled_returns_503(ea, client):
    ea.GOOGLE_SUBS_ENABLED = False
    r = client.post('/iap/google/rtdn', json={'message': {'data': 'x', 'messageId': 'm'}})
    assert r.status_code == 503
    assert r.get_json()['error'] == 'google_subs_disabled'


def test_google_rtdn_enabled_but_unconfigured_returns_503(ea, client):
    ea.GOOGLE_SUBS_ENABLED = True
    ea._GOOGLE_API_CLIENT_OVERRIDE = None
    ea.GOOGLE_PLAY_SA_JSON = ''
    r = client.post('/iap/google/rtdn', json={'message': {'data': 'x', 'messageId': 'm'}})
    assert r.status_code == 503
    assert r.get_json()['error'] == 'google_verify_unconfigured'


# ───────────────────────────────────────────────────────────────────────────
# Apple notifications — a body with no signedPayload is a 400 ignore (never 5xx),
# and never touches the DB.
# ───────────────────────────────────────────────────────────────────────────
def test_apple_notifications_no_signed_payload(ea, client):
    r = client.post('/iap/apple/notifications', json={})
    assert r.status_code == 400
    assert r.get_json()['reason'] == 'apple_no_signed_payload'


# ───────────────────────────────────────────────────────────────────────────
# subscriptions/verify — missing fields (400), unsupported store (400),
# google gated (503). None of these reach the DB.
# ───────────────────────────────────────────────────────────────────────────
def test_subscriptions_verify_missing_fields(ea, client):
    r = client.post('/subscriptions/verify', json={'store': 'apple'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'missing_fields'


def test_subscriptions_verify_unsupported_store(ea, client):
    r = client.post('/subscriptions/verify',
                    json={'store': 'paypal', 'user_id': 'u', 'product_id': 'p'})
    assert r.status_code == 400
    assert r.get_json()['error'].startswith('unsupported_store')


def test_subscriptions_verify_google_gated(ea, client):
    ea.GOOGLE_SUBS_ENABLED = False
    r = client.post('/subscriptions/verify',
                    json={'store': 'google', 'user_id': 'u',
                          'product_id': 'audioura.sub.monthly',
                          'purchase_token': 't'})
    assert r.status_code == 503
    assert r.get_json()['error'] == 'google_subs_disabled'


def test_subscriptions_verify_apple_missing_jws(ea, client):
    r = client.post('/subscriptions/verify',
                    json={'store': 'apple', 'user_id': 'u',
                          'product_id': 'audioura.sub.monthly'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'apple_missing_signed_transaction'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
