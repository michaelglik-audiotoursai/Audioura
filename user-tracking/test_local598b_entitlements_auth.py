"""
test_local598b_entitlements_auth.py — LOCAL-598B: tests for the entitlements
API auth gate and the local-only ALLOW_UNAUTHENTICATED_ENTITLEMENTS bypass.

The gate (`entitlements_api._require_api_key`) must behave exactly like the
ST-4 sharing precedent:

  • GATEWAY_API_KEY set            -> the X-API-Key header is REQUIRED
       - no/blank header           -> 401 unauthorized
       - correct header            -> allowed (passes the gate)
  • GATEWAY_API_KEY empty, flag off -> 503 service_misconfigured (fail CLOSED)
  • GATEWAY_API_KEY empty, flag on  -> allowed, AND a loud startup warning is
                                        logged.

These tests exercise ONLY the auth gate, not the DB-backed endpoint bodies, so
they need no Postgres: a tiny Flask app registers a single route guarded by the
real `_require_api_key`, and we drive it with Flask's test client. The module is
re-imported per case (the gate reads GATEWAY_API_KEY at import) with the chosen
environment so each case gets a cleanly-configured module.

Run:
    cd user-tracking && python3 -m pytest test_local598b_entitlements_auth.py -q
or (no pytest):
    cd user-tracking && python3 test_local598b_entitlements_auth.py
"""

import contextlib
import importlib
import logging
import os
import sys

from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@contextlib.contextmanager
def _module_env(env):
    """Context manager: set the chosen environment, (re-)import entitlements_api
    with it, and yield the freshly imported module. The environment stays LIVE
    for the whole `with` block (so request-time os.getenv reads see it) and is
    restored on exit. Log records emitted DURING import (when the startup
    warning fires) are attached to the module as `._import_logs`."""
    saved = {}
    keys = ('GATEWAY_API_KEY', 'ALLOW_UNAUTHENTICATED_ENTITLEMENTS')
    for k in keys:
        saved[k] = os.environ.get(k)
        if env.get(k) is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = env[k]

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger('entitlements_api')
    handler = _Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        sys.modules.pop('entitlements_api', None)
        mod = importlib.import_module('entitlements_api')
        mod._import_logs = records
        logger.removeHandler(handler)  # capture only import-time records
        yield mod
    finally:
        # Remove the handler if still attached, then restore the environment.
        if handler in logger.handlers:
            logger.removeHandler(handler)
        for k in keys:
            if saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]


def _app_with_gate(mod):
    """A minimal Flask app with one route guarded by the real gate."""
    app = Flask(__name__)

    @app.route('/guarded')
    def guarded():
        err = mod._require_api_key()
        if err:
            return err
        return jsonify({"ok": True}), 200

    return app


# ───────────────────────────────────────────────────────────────────────────
# Key SET -> header required
# ───────────────────────────────────────────────────────────────────────────
def test_key_set_requires_header():
    with _module_env({'GATEWAY_API_KEY': 'secret-key',
                      'ALLOW_UNAUTHENTICATED_ENTITLEMENTS': None}) as mod:
        client = _app_with_gate(mod).test_client()

        # No header -> 401.
        r = client.get('/guarded')
        assert r.status_code == 401, r.status_code
        assert r.get_json().get('error') == 'unauthorized'

        # Wrong header -> 401.
        r = client.get('/guarded', headers={'X-API-Key': 'nope'})
        assert r.status_code == 401, r.status_code

        # Correct header -> allowed.
        r = client.get('/guarded', headers={'X-API-Key': 'secret-key'})
        assert r.status_code == 200, r.status_code
        assert r.get_json().get('ok') is True


def test_key_set_flag_on_still_requires_header():
    # The flag must NOT weaken auth when a key is configured: it is honoured
    # ONLY when the key is empty.
    with _module_env({'GATEWAY_API_KEY': 'secret-key',
                      'ALLOW_UNAUTHENTICATED_ENTITLEMENTS': 'true'}) as mod:
        client = _app_with_gate(mod).test_client()
        r = client.get('/guarded')
        assert r.status_code == 401, r.status_code


# ───────────────────────────────────────────────────────────────────────────
# Key EMPTY, flag OFF -> 503 (fail closed)
# ───────────────────────────────────────────────────────────────────────────
def test_key_empty_flag_off_is_503():
    with _module_env({'GATEWAY_API_KEY': '',
                      'ALLOW_UNAUTHENTICATED_ENTITLEMENTS': None}) as mod:
        client = _app_with_gate(mod).test_client()
        r = client.get('/guarded')
        assert r.status_code == 503, r.status_code
        assert r.get_json().get('error') == 'service_misconfigured'
        # No startup warning in this configuration.
        assert not any('ALLOW_UNAUTHENTICATED_ENTITLEMENTS' in rec.getMessage()
                       for rec in mod._import_logs)


def test_key_empty_flag_explicit_false_is_503():
    with _module_env({'GATEWAY_API_KEY': '',
                      'ALLOW_UNAUTHENTICATED_ENTITLEMENTS': 'false'}) as mod:
        client = _app_with_gate(mod).test_client()
        r = client.get('/guarded')
        assert r.status_code == 503, r.status_code


# ───────────────────────────────────────────────────────────────────────────
# Key EMPTY, flag ON -> allowed + loud startup warning
# ───────────────────────────────────────────────────────────────────────────
def test_key_empty_flag_on_allows_and_warns():
    with _module_env({'GATEWAY_API_KEY': '',
                      'ALLOW_UNAUTHENTICATED_ENTITLEMENTS': 'true'}) as mod:
        client = _app_with_gate(mod).test_client()

        # Unauthenticated request is served.
        r = client.get('/guarded')
        assert r.status_code == 200, r.status_code
        assert r.get_json().get('ok') is True

        # A loud startup WARNING naming the flag was logged at import time.
        warnings = [rec for rec in mod._import_logs if rec.levelno >= logging.WARNING]
        assert any('ALLOW_UNAUTHENTICATED_ENTITLEMENTS' in rec.getMessage()
                   for rec in warnings), \
            f'expected a startup warning naming the flag; got {[r.getMessage() for r in warnings]}'


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f'ERROR {t.__name__}: {type(e).__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    sys.exit(1 if failed else 0)
