"""
test_local598_apple_jws.py — LOCAL-598 D8: tests for the offline StoreKit 2 JWS
verifier (apple_jws_verifier.verify_signed_transaction).

Builds a self-signed test chain (test root -> intermediate -> leaf) with the
`cryptography` library and signs JWS transactions with the leaf key, so the
whole positive + negative matrix runs with no Apple servers and no network:

  • happy path: a well-formed JWS verifies and returns the claims.
  • wrong root: a chain rooted at a DIFFERENT CA than the pinned one is rejected
    (root_not_apple) — this is what pinning the real Apple Root CA G3 buys us.
  • wrong bundle: bundleId mismatch is rejected (bundle_mismatch).
  • non-consumable: type != Consumable is rejected (type_not_consumable).
  • product mismatch: productId mismatch is rejected (product_mismatch).
  • tampered payload: a changed payload fails the signature (signature_invalid).

[LOCAL-598B] The hardening matrix — each pins the test root (so the root check
passes) and then breaks exactly one new requirement, proving the requirement is
load-bearing:

  • leaf missing the Apple IAP OID -> leaf_oid_missing;
  • intermediate missing the Apple WWDR OID -> intermediate_oid_missing;
  • an expired leaf (signedDate after it expired) -> cert_expired;
  • a chain of 2 (leaf, root) and of 4 -> chain_length_invalid;
  • environment != expected -> environment_mismatch;
  • a payload carrying revocationDate -> transaction_revoked;
  • a valid-at-signedDate leaf still verifies even though it is expired "now"
    (signedDate reference time works).

For the pin test we point the verifier at OUR test root as the "pinned" root,
then present a chain rooted at a different CA; that is the pin working. A second
assertion confirms the bundled real Apple Root CA G3 (apple_root_ca_g3.pem) is a
valid, self-consistent certificate.

Run:
    cd user-tracking && python3 -m pytest test_local598_apple_jws.py -q
or (no pytest):
    cd user-tracking && python3 test_local598_apple_jws.py
"""

import base64
import datetime
import json
import os
import sys

from cryptography import x509
from cryptography.x509.oid import NameOID, ObjectIdentifier
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apple_jws_verifier import (  # noqa: E402
    verify_signed_transaction, JwsVerificationError,
    APPLE_LEAF_OID, APPLE_INTERMEDIATE_OID,
)

BUNDLE_ID = 'com.audioura.audiotours'
PRODUCT_ID = 'audioura.pack.l3'

# [LOCAL-598B] A throwaway extension payload (DER NULL) to attach under the
# Apple purpose OIDs. The verifier only checks the OID is PRESENT, not its
# contents, so any well-formed extension value does.
_EXT_VALUE = x509.UnrecognizedExtension(ObjectIdentifier('1.2.840.113635.100.6.11.1'), b'\x05\x00')


# ───────────────────────────────────────────────────────────────────────────
# Test PKI helpers
# ───────────────────────────────────────────────────────────────────────────
def _key():
    return ec.generate_private_key(ec.SECP256R1())


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _self_signed(key, cn):
    now = datetime.datetime.utcnow()
    return (
        x509.CertificateBuilder()
        .subject_name(_name(cn))
        .issuer_name(_name(cn))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=3650))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )


def _child(subject_cn, subject_key, issuer_cert, issuer_key, is_ca,
           ext_oid=None, not_before=None, not_after=None):
    """Build a child cert. If `ext_oid` is given, attach an empty extension with
    that OID (used to stamp the Apple purpose OIDs on the leaf/intermediate).
    `not_before`/`not_after` override the default decade-wide validity window
    (used to forge an expired leaf)."""
    now = datetime.datetime.utcnow()
    nb = not_before if not_before is not None else now - datetime.timedelta(days=3650)
    na = not_after if not_after is not None else now + datetime.timedelta(days=3650)
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject_cn))
        .issuer_name(issuer_cert.subject)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nb)
        .not_valid_after(na)
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
    )
    if ext_oid is not None:
        # Apple's purpose OIDs are private extensions; the verifier checks only
        # their PRESENCE. A DER NULL (0x05 0x00) is a valid extension value.
        builder = builder.add_extension(
            x509.UnrecognizedExtension(ext_oid, b'\x05\x00'), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


def _der_b64(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode('ascii')


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _make_chain(leaf_oid=APPLE_LEAF_OID, inter_oid=APPLE_INTERMEDIATE_OID,
                leaf_not_before=None, leaf_not_after=None):
    """Return (root_key, root_cert, inter_cert, leaf_key, leaf_cert).

    By default the leaf carries the Apple IAP OID and the intermediate carries
    the Apple WWDR OID, so the chain passes the LOCAL-598B purpose-OID checks.
    Pass leaf_oid=None / inter_oid=None to forge a chain missing an OID, or
    leaf_not_before/leaf_not_after to forge an expired leaf."""
    root_key = _key()
    root_cert = _self_signed(root_key, 'Test Root CA')
    inter_key = _key()
    inter_cert = _child('Test Intermediate', inter_key, root_cert, root_key,
                        is_ca=True, ext_oid=inter_oid)
    leaf_key = _key()
    leaf_cert = _child('Test Leaf', leaf_key, inter_cert, inter_key, is_ca=False,
                       ext_oid=leaf_oid,
                       not_before=leaf_not_before, not_after=leaf_not_after)
    return root_key, root_cert, inter_cert, leaf_key, leaf_cert


def _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, payload: dict,
              tamper_payload: bool = False, x5c_certs=None) -> str:
    # x5c defaults to [leaf, intermediate, root]; pass x5c_certs to forge a
    # chain of a different length for the chain_length_invalid test.
    chain = x5c_certs if x5c_certs is not None else [leaf_cert, inter_cert, root_cert]
    header = {
        'alg': 'ES256',
        'x5c': [_der_b64(c) for c in chain],
    }
    header_b64 = _b64url(json.dumps(header).encode())
    payload_b64 = _b64url(json.dumps(payload).encode())
    signing_input = f'{header_b64}.{payload_b64}'.encode('ascii')

    der_sig = leaf_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    sig_b64 = _b64url(raw_sig)

    if tamper_payload:
        bad = dict(payload)
        bad['transactionId'] = 'tampered-99999'
        payload_b64 = _b64url(json.dumps(bad).encode())

    return f'{header_b64}.{payload_b64}.{sig_b64}'


def _root_pem(root_cert) -> bytes:
    return root_cert.public_bytes(serialization.Encoding.PEM)


def _payload(**over):
    base = {
        'transactionId': '2000000123456789',
        'productId': PRODUCT_ID,
        'bundleId': BUNDLE_ID,
        'type': 'Consumable',
    }
    base.update(over)
    return base


# ───────────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────────
def test_happy_path():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload())
    result = verify_signed_transaction(
        jws, root_ca_pem=_root_pem(root_cert),
        expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
    assert result.transaction_id == '2000000123456789'
    assert result.product_id == PRODUCT_ID
    assert result.type == 'Consumable'


def test_wrong_root_rejected():
    # Chain rooted at CA #1, but pin to a DIFFERENT CA #2 -> rejected.
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    other_root_key = _key()
    other_root_cert = _self_signed(other_root_key, 'Different Root CA')
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload())
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(other_root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'root_not_apple', e.code


def test_wrong_bundle_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(bundleId='com.evil.app'))
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'bundle_mismatch', e.code


def test_non_consumable_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(type='Auto-Renewable Subscription'))
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'type_not_consumable', e.code


def test_product_mismatch_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(productId='audioura.round.l4'))
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'product_mismatch', e.code


def test_tampered_payload_fails_signature():
    # Re-sign with the signature over the ORIGINAL payload, then swap in a
    # different payload: the signature no longer matches -> signature_invalid.
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload(),
                    tamper_payload=True)
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'signature_invalid', e.code


def test_malformed_jws_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    try:
        verify_signed_transaction(
            'not-a-jws', root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'malformed_jws', e.code


# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-598B] Hardening matrix
# ───────────────────────────────────────────────────────────────────────────
def test_leaf_missing_oid_rejected():
    # Chain rooted/pinned correctly, but the LEAF lacks the Apple IAP OID: this
    # is exactly the Apple-Pay-merchant-cert class of attack the OID pin blocks.
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain(leaf_oid=None)
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload())
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'leaf_oid_missing', e.code


def test_intermediate_missing_oid_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain(inter_oid=None)
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload())
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'intermediate_oid_missing', e.code


def test_expired_leaf_rejected():
    # Leaf expired a year ago; signedDate is NOW, so it was not valid when the
    # transaction was signed -> cert_expired.
    now = datetime.datetime.utcnow()
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain(
        leaf_not_before=now - datetime.timedelta(days=730),
        leaf_not_after=now - datetime.timedelta(days=365))
    signed_ms = int(now.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(signedDate=signed_ms))
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'cert_expired', e.code


def test_leaf_valid_at_signeddate_accepted():
    # Leaf expired "now" but was valid at signedDate (one month into its
    # window): using the signing time as the reference, it still verifies. This
    # proves the signedDate reference is honoured, not just "now".
    now = datetime.datetime.utcnow()
    nb = now - datetime.timedelta(days=400)
    na = now - datetime.timedelta(days=10)   # expired 10 days ago
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain(
        leaf_not_before=nb, leaf_not_after=na)
    signed_at = now - datetime.timedelta(days=200)  # inside [nb, na]
    signed_ms = int(signed_at.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(signedDate=signed_ms))
    result = verify_signed_transaction(
        jws, root_ca_pem=_root_pem(root_cert),
        expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
    assert result.transaction_id == '2000000123456789'


def test_chain_length_two_rejected():
    # Present only [leaf, root] (2 certs): rejected before any signature work.
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload(),
                    x5c_certs=[leaf_cert, root_cert])
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'chain_length_invalid', e.code


def test_chain_length_four_rejected():
    # Present 4 certs [leaf, intermediate, intermediate, root]: also rejected.
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, _payload(),
                    x5c_certs=[leaf_cert, inter_cert, inter_cert, root_cert])
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'chain_length_invalid', e.code


def test_wrong_environment_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(environment='Production'))
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID,
            expected_environment='Sandbox')
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'environment_mismatch', e.code


def test_matching_environment_accepted():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(environment='Sandbox'))
    result = verify_signed_transaction(
        jws, root_ca_pem=_root_pem(root_cert),
        expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID,
        expected_environment='Sandbox')
    assert result.environment == 'Sandbox'


def test_revoked_transaction_rejected():
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = _make_chain()
    jws = _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert,
                    _payload(revocationDate=1700000000000))
    try:
        verify_signed_transaction(
            jws, root_ca_pem=_root_pem(root_cert),
            expected_bundle_id=BUNDLE_ID, expected_product_id=PRODUCT_ID)
        assert False, 'expected JwsVerificationError'
    except JwsVerificationError as e:
        assert e.code == 'transaction_revoked', e.code


def test_bundled_apple_root_is_valid():
    # The bundled real Apple Root CA G3 parses and is self-signed.
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'apple_root_ca_g3.pem'), 'rb') as f:
        pem = f.read()
    cert = x509.load_pem_x509_certificate(pem)
    assert 'Apple Root CA' in cert.subject.rfc4514_string()
    assert cert.subject == cert.issuer  # self-signed root


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
