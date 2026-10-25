"""
test_local764_apple_env_fallback.py — LOCAL-764 C: Apple IAP verification must
accept Production WITH a Sandbox fallback.

Why this exists
---------------
The Subscribed track launches to testers through TestFlight. TestFlight
purchases are signed by Apple with `environment: "Sandbox"`, even when the app
is distributed from App Store Connect / against the Production App Store Server
environment. The StoreKit 2 JWS verifier pins the payload `environment` against
an expected value (LOCAL-598B). If the Subscribed GCloud deployment pins ONLY
`Production` (the natural prod setting), every TestFlight purchase is rejected
with `environment_mismatch` — the exact "Production with Sandbox fallback"
requirement Apple documents (legacy verifyReceipt returned 21007 for a sandbox
receipt sent to production; the server was expected to retry against sandbox).

Fix under test
--------------
`verify_signed_transaction(expected_environment=...)` accepts not just a single
string but an iterable of acceptable environments, so a deployment can pass
{'Production', 'Sandbox'} (Production primary, Sandbox fallback) and a TestFlight
(Sandbox) transaction verifies while an unrelated environment is still rejected.
A single string keeps its exact old meaning (strict pin).

Reuses the LOCAL-598 test-PKI helpers (self-signed test chain; no Apple servers,
no network).

Run:
    cd user-tracking && python3 -m pytest test_local764_apple_env_fallback.py -q
or:
    cd user-tracking && python3 test_local764_apple_env_fallback.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apple_jws_verifier import verify_signed_transaction, JwsVerificationError  # noqa: E402
# Reuse the LOCAL-598 test-PKI + JWS builders.
from test_local598_apple_jws import (  # noqa: E402
    _make_chain, _sign_jws, _root_pem, _payload, BUNDLE_ID, PRODUCT_ID,
)


def _jws_for(environment):
    root_key, root, inter, leaf_key, leaf = _make_chain()
    jws = _sign_jws(leaf_key, leaf, inter, root,
                    _payload(environment=environment))
    return jws, _root_pem(root)


def _verify(jws, root_pem, expected_environment):
    return verify_signed_transaction(
        jws,
        root_ca_pem=root_pem,
        expected_bundle_id=BUNDLE_ID,
        expected_product_id=PRODUCT_ID,
        required_type='Consumable',
        expected_environment=expected_environment,
    )


def test_sandbox_accepted_when_fallback_configured():
    """A TestFlight (Sandbox) transaction verifies when the deployment accepts
    {'Production','Sandbox'} — the Production-with-Sandbox-fallback setting."""
    jws, root_pem = _jws_for('Sandbox')
    result = _verify(jws, root_pem, ['Production', 'Sandbox'])
    assert result.environment == 'Sandbox', result.environment


def test_production_accepted_when_fallback_configured():
    """A real Production transaction still verifies under the same setting."""
    jws, root_pem = _jws_for('Production')
    result = _verify(jws, root_pem, ['Production', 'Sandbox'])
    assert result.environment == 'Production', result.environment


def test_unrelated_environment_still_rejected_under_fallback():
    """An environment outside the accepted set is still rejected — the fallback
    widens the pin to exactly {Production, Sandbox}, not to 'anything'."""
    jws, root_pem = _jws_for('Xcode')  # local StoreKit testing environment
    try:
        _verify(jws, root_pem, ['Production', 'Sandbox'])
        assert False, 'expected environment_mismatch'
    except JwsVerificationError as e:
        assert e.code == 'environment_mismatch', e.code


def test_single_string_still_strict():
    """A single-string expectation keeps its exact old meaning: a Sandbox
    transaction is rejected when only 'Production' is accepted."""
    jws, root_pem = _jws_for('Sandbox')
    try:
        _verify(jws, root_pem, 'Production')
        assert False, 'expected environment_mismatch'
    except JwsVerificationError as e:
        assert e.code == 'environment_mismatch', e.code


def test_single_string_match_still_accepted():
    jws, root_pem = _jws_for('Production')
    result = _verify(jws, root_pem, 'Production')
    assert result.environment == 'Production'


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa
            failures += 1
            print(f"ERROR {t.__name__}: {e}")
    print("=" * 50)
    print(f"{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
