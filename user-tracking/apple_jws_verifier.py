"""
apple_jws_verifier.py — LOCAL-598 D5: OFFLINE verification of a StoreKit 2
JWS signed transaction.

Apple's App Store Server API / StoreKit 2 hands the device a `signedTransaction`
in JWS compact form:

    base64url(header) . base64url(payload) . base64url(signature)

The JOSE header carries an `x5c` chain (leaf, intermediate, root) of DER certs,
base64 (standard, not url) encoded. Verifying the transaction needs NO network
and NO API key — everything is in the JWS plus the Apple Root CA G3 we bundle:

  1. Decode the header, read x5c (must be EXACTLY a 3-cert chain:
     leaf -> intermediate -> Apple Root CA G3).
  2. Pin the root: the last cert in x5c must be byte-identical to our bundled
     Apple Root CA G3. (We also independently verify the chain's signatures.)
  3. Verify the chain: root signs intermediate, intermediate signs leaf.
  4. Verify the JWS signature (ES256 / P-256) over
     `base64url(header).base64url(payload)` with the LEAF cert's public key.
  5. Read the payload and check: bundleId == expected, productId == expected,
     type == "Consumable".

[LOCAL-598B] Hardening — pinning Root CA G3 alone is NOT enough. Apple issues
many certificate kinds that all chain to Root CA G3 (Apple Pay merchant certs,
for example, held by any developer); a JWS signed with such a cert would have
verified. Apple's own App Store Server Library additionally requires, and we now
enforce:

  • the LEAF carries Apple's IAP receipt-signing purpose OID
    `1.2.840.113635.100.6.11.1`;
  • the INTERMEDIATE (WWDR) carries OID `1.2.840.113635.100.6.2.1`;
  • the chain is EXACTLY three certs (leaf, intermediate, root) — not merely
    "at least two";
  • every cert is temporally valid at the payload's `signedDate` (or, absent
    one, at verification time);
  • the payload `environment` matches the expected value
    (`Sandbox` locally, `Production` in prod) when an expectation is supplied;
  • the payload carries NO `revocationDate` (a revoked transaction never grants).

transactionId uniqueness is enforced by the caller against the `purchases`
table (UNIQUE transaction_id) — the same id can never grant twice.

This module is PURE and dependency-light: `cryptography` only, no Flask, no DB.
It raises `JwsVerificationError` with a stable `.code` for every failure so the
HTTP layer and the tests can branch on the exact reason.
"""

from __future__ import annotations

import base64
import json
import hashlib
import datetime
from dataclasses import dataclass
from typing import Optional

from cryptography import x509
from cryptography.x509.oid import ObjectIdentifier
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature


# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-598B] Apple IAP certificate purpose OIDs (App Store Server Library).
# The leaf (receipt/transaction signing) and the WWDR intermediate each carry a
# distinct Apple-private extension OID. Pinning the Root CA G3 alone is not
# enough: other Apple certs chain to the same root, so we additionally require
# these purpose OIDs to be present on the right cert in the chain.
# ───────────────────────────────────────────────────────────────────────────
APPLE_LEAF_OID = ObjectIdentifier('1.2.840.113635.100.6.11.1')
APPLE_INTERMEDIATE_OID = ObjectIdentifier('1.2.840.113635.100.6.2.1')

# A StoreKit 2 x5c is EXACTLY leaf, intermediate, root.
APPLE_CHAIN_LENGTH = 3


class JwsVerificationError(Exception):
    """A verification failure with a stable machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class VerifiedTransaction:
    transaction_id: str
    product_id: str
    bundle_id: str
    type: str
    raw_payload: dict
    environment: Optional[str] = None


# ───────────────────────────────────────────────────────────────────────────
# base64url helpers (JWS uses URL-safe base64 WITHOUT padding)
# ───────────────────────────────────────────────────────────────────────────
def _b64url_decode(data: str) -> bytes:
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _load_root_ca(root_ca_pem: bytes) -> x509.Certificate:
    return x509.load_pem_x509_certificate(root_ca_pem)


# ───────────────────────────────────────────────────────────────────────────
# Certificate chain verification
# ───────────────────────────────────────────────────────────────────────────
def _verify_cert_signed_by(child: x509.Certificate, parent: x509.Certificate):
    """Raise JwsVerificationError('chain_invalid') if `parent` did not sign
    `child`. Supports the ECDSA (P-256/P-384) certs Apple uses."""
    parent_key = parent.public_key()
    try:
        if isinstance(parent_key, ec.EllipticCurvePublicKey):
            parent_key.verify(
                child.signature,
                child.tbs_certificate_bytes,
                ec.ECDSA(child.signature_hash_algorithm),
            )
        else:
            raise JwsVerificationError(
                'chain_invalid', 'Unexpected issuer key type in chain.')
    except InvalidSignature:
        raise JwsVerificationError(
            'chain_invalid', 'A certificate in the x5c chain is not signed by its issuer.')


def _has_extension_oid(cert: x509.Certificate, oid: ObjectIdentifier) -> bool:
    """True iff `cert` carries an extension with exactly this OID. Apple's IAP
    purpose OIDs are private (unrecognized by `cryptography`), so a plain
    `extensions.get_extension_for_oid` lookup is the right primitive — it finds
    the extension whether or not the library has a typed parser for it."""
    try:
        cert.extensions.get_extension_for_oid(oid)
        return True
    except x509.ExtensionNotFound:
        return False


def _cert_valid_at(cert: x509.Certificate, when: datetime.datetime) -> bool:
    """True iff `when` is within the cert's validity window. Uses the tz-aware
    accessors when available (cryptography >= 42) and falls back to the naive
    UTC ones otherwise, so the check is correct across library versions."""
    try:
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
    except AttributeError:  # pragma: no cover - older cryptography
        not_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
        not_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return not_before <= when <= not_after


def _verify_chain(x5c_der: list[bytes], root_ca_pem: bytes,
                  valid_at: Optional[datetime.datetime] = None) -> x509.Certificate:
    """Verify the x5c chain and pin the Apple root. Returns the LEAF cert.

    Expects EXACTLY [leaf, intermediate, root]. Enforces, in addition to the
    signature links:
      • chain length == 3 (chain_length_invalid);
      • the final cert is byte-identical to the bundled Apple Root CA G3
        (root_not_apple);
      • the leaf carries Apple's IAP receipt-signing OID (leaf_oid_missing);
      • the intermediate carries Apple's WWDR OID (intermediate_oid_missing);
      • every cert is temporally valid at `valid_at` (or now) (cert_expired).

    `valid_at` is the payload's signedDate when the caller has it, so a cert
    that was valid when Apple signed the transaction is accepted even if it has
    since expired; absent a signedDate we fall back to the current time."""
    if len(x5c_der) != APPLE_CHAIN_LENGTH:
        raise JwsVerificationError(
            'chain_length_invalid',
            f'x5c must be exactly {APPLE_CHAIN_LENGTH} certs '
            f'(leaf, intermediate, root); got {len(x5c_der)}.')

    certs = []
    for der in x5c_der:
        try:
            certs.append(x509.load_der_x509_certificate(der))
        except Exception as e:
            raise JwsVerificationError('cert_parse_failed', f'Bad certificate in x5c: {e}')

    leaf, intermediate, presented_root = certs[0], certs[1], certs[2]

    bundled_root = _load_root_ca(root_ca_pem)

    # Pin: the chain's final cert must be exactly our Apple Root CA G3. Compare
    # the DER bytes (fingerprint) so a look-alike root is rejected outright.
    if presented_root.fingerprint(hashes.SHA256()) != bundled_root.fingerprint(hashes.SHA256()):
        raise JwsVerificationError(
            'root_not_apple',
            'The x5c root is not the pinned Apple Root CA G3.')

    # [LOCAL-598B] Purpose OIDs. Pinning the root is necessary but not
    # sufficient — require the Apple-private purpose OIDs on the leaf and the
    # intermediate so an Apple-issued cert for some OTHER purpose (which also
    # chains to Root CA G3) cannot be used to sign a transaction.
    if not _has_extension_oid(leaf, APPLE_LEAF_OID):
        raise JwsVerificationError(
            'leaf_oid_missing',
            f'Leaf cert lacks the Apple IAP OID {APPLE_LEAF_OID.dotted_string}.')
    if not _has_extension_oid(intermediate, APPLE_INTERMEDIATE_OID):
        raise JwsVerificationError(
            'intermediate_oid_missing',
            f'Intermediate cert lacks the Apple WWDR OID '
            f'{APPLE_INTERMEDIATE_OID.dotted_string}.')

    # [LOCAL-598B] Temporal validity at the signing time (or now). An expired
    # or not-yet-valid cert anywhere in the chain is rejected.
    reference = valid_at or datetime.datetime.now(datetime.timezone.utc)
    for cert in certs:
        if not _cert_valid_at(cert, reference):
            raise JwsVerificationError(
                'cert_expired',
                'A certificate in the x5c chain is not valid at the signing time.')

    # Verify each link: certs[i] is signed by certs[i+1], up to the root.
    for i in range(len(certs) - 1):
        _verify_cert_signed_by(certs[i], certs[i + 1])

    # The pinned root is self-signed; verify that too for completeness.
    _verify_cert_signed_by(presented_root, bundled_root)

    return leaf


# ───────────────────────────────────────────────────────────────────────────
# JWS signature verification (ES256)
# ───────────────────────────────────────────────────────────────────────────
def _verify_jws_signature(signing_input: bytes, signature_raw: bytes,
                          leaf: x509.Certificate):
    """Verify an ES256 JWS signature. JWS carries the ECDSA signature as the
    raw r||s concatenation (64 bytes for P-256); convert to DER for
    `cryptography`."""
    pubkey = leaf.public_key()
    if not isinstance(pubkey, ec.EllipticCurvePublicKey):
        raise JwsVerificationError('bad_leaf_key', 'Leaf key is not EC.')

    if len(signature_raw) % 2 != 0 or len(signature_raw) == 0:
        raise JwsVerificationError('bad_signature', 'Malformed JWS signature length.')
    half = len(signature_raw) // 2
    r = int.from_bytes(signature_raw[:half], 'big')
    s = int.from_bytes(signature_raw[half:], 'big')
    der_sig = encode_dss_signature(r, s)

    try:
        pubkey.verify(der_sig, signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise JwsVerificationError(
            'signature_invalid', 'The JWS signature did not verify against the leaf certificate.')


# ───────────────────────────────────────────────────────────────────────────
# Public entry point
# ───────────────────────────────────────────────────────────────────────────
def _parse_signed_date(payload: dict) -> Optional[datetime.datetime]:
    """Apple's `signedDate` is epoch MILLISECONDS. Return it as a tz-aware UTC
    datetime, or None if absent/unparseable (the caller then falls back to the
    current time for the validity check)."""
    raw = payload.get('signedDate')
    if raw is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(
            float(raw) / 1000.0, tz=datetime.timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def verify_and_decode_jws(jws: str, root_ca_pem: bytes) -> dict:
    """[LOCAL-807] Verify ANY Apple-signed JWS offline and return its decoded
    payload dict. This is the chain-pin + ES256-signature core shared by
    verify_signed_transaction and the App Store Server Notifications v2 path:

      * the x5c chain is pinned to the bundled Apple Root CA G3 and checked for
        the leaf/intermediate purpose OIDs, exact length, and temporal validity
        at signedDate (exactly as verify_signed_transaction);
      * the ES256 signature is verified over header.payload with the leaf key;
      * the decoded payload is returned WITHOUT any transaction-specific claim
        checks (bundleId / productId / type / environment / revocation), so the
        caller applies whatever claim rules fit the payload kind.

    An ASSN v2 notification is a `signedPayload` JWS whose payload carries nested
    `signedTransactionInfo` and `signedRenewalInfo` JWS strings; each is verified
    with THIS function (same Apple chain), then its claims are read. A signed
    transaction's own claim checks still live in verify_signed_transaction, which
    now delegates its crypto here so the two can never diverge.

    Raises JwsVerificationError with a stable `.code` on any failure. Performs
    NO network and NO DB access.
    """
    if not jws or jws.count('.') != 2:
        raise JwsVerificationError('malformed_jws', 'Expected a compact JWS with 3 parts.')

    header_b64, payload_b64, signature_b64 = jws.split('.')

    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception as e:
        raise JwsVerificationError('bad_header', f'Could not decode JWS header: {e}')

    alg = header.get('alg')
    if alg != 'ES256':
        raise JwsVerificationError('bad_alg', f"Unexpected alg '{alg}', expected ES256.")

    x5c = header.get('x5c')
    if not isinstance(x5c, list) or not x5c:
        raise JwsVerificationError('no_x5c', 'JWS header has no x5c certificate chain.')

    try:
        x5c_der = [base64.b64decode(c) for c in x5c]
    except Exception as e:
        raise JwsVerificationError('bad_x5c', f'Could not base64-decode x5c: {e}')

    # Peek at signedDate for the cert-validity reference time ONLY (untrusted
    # until the signature verifies — tampering with it fails the check below).
    try:
        _early_payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        _early_payload = {}
    valid_at = _parse_signed_date(_early_payload) if isinstance(_early_payload, dict) else None

    # Chain + root pin + OIDs + chain-length + validity.
    leaf = _verify_chain(x5c_der, root_ca_pem, valid_at=valid_at)

    # Signature over header.payload.
    try:
        signature_raw = _b64url_decode(signature_b64)
    except Exception as e:
        raise JwsVerificationError('bad_signature', f'Could not decode signature: {e}')
    signing_input = f'{header_b64}.{payload_b64}'.encode('ascii')
    _verify_jws_signature(signing_input, signature_raw, leaf)

    # Payload (only trusted AFTER the signature verified).
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        raise JwsVerificationError('bad_payload', f'Could not decode payload: {e}')
    if not isinstance(payload, dict):
        raise JwsVerificationError('bad_payload', 'JWS payload is not a JSON object.')
    return payload


def verify_signed_transaction(
    jws: str,
    root_ca_pem: bytes,
    expected_bundle_id: str,
    expected_product_id: Optional[str] = None,
    required_type: str = 'Consumable',
    expected_environment=None,
) -> VerifiedTransaction:
    """Verify a StoreKit 2 JWS signed transaction offline.

    Args:
        jws: the compact JWS string (header.payload.signature).
        root_ca_pem: PEM bytes of the pinned Apple Root CA G3.
        expected_bundle_id: the app's bundle id (e.g. com.audioura.audiotours).
        expected_product_id: if given, the payload productId must equal it.
        required_type: the payload `type` must equal this (default Consumable).
        expected_environment: if given, the payload `environment` must be one of
            the accepted environments (environment_mismatch otherwise). Accepts
            either a single string (a strict pin, e.g. 'Sandbox' locally) OR an
            iterable of strings for a Production-with-Sandbox fallback
            (e.g. ('Production', 'Sandbox')): TestFlight purchases are signed as
            'Sandbox' even against the Production App Store Server environment,
            so a Production deployment that also tests via TestFlight must accept
            both (LOCAL-764). None disables the check.

    Returns a VerifiedTransaction on success. Raises JwsVerificationError with a
    stable `.code` on any failure. Performs NO network and NO DB access.
    """
    # [LOCAL-807] Crypto (chain pin + ES256 signature + decode) is shared with
    # the notifications path via verify_and_decode_jws, so the two can never
    # diverge. The transaction-specific claim checks stay here.
    payload = verify_and_decode_jws(jws, root_ca_pem)

    bundle_id = payload.get('bundleId')
    if bundle_id != expected_bundle_id:
        raise JwsVerificationError(
            'bundle_mismatch',
            f"bundleId '{bundle_id}' does not match expected '{expected_bundle_id}'.")

    product_id = payload.get('productId')
    if expected_product_id is not None and product_id != expected_product_id:
        raise JwsVerificationError(
            'product_mismatch',
            f"productId '{product_id}' does not match expected '{expected_product_id}'.")

    tx_type = payload.get('type')
    if required_type is not None and tx_type != required_type:
        raise JwsVerificationError(
            'type_not_consumable',
            f"type '{tx_type}' is not '{required_type}'.")

    # [LOCAL-598B / LOCAL-764] Environment pin. A Sandbox transaction must never
    # grant on a Production-only server and vice-versa. `expected_environment`
    # is either a single string (strict pin) or an iterable of accepted values
    # (Production-with-Sandbox fallback for TestFlight). Only enforced when the
    # caller supplies an expectation (env APPLE_IAP_ENVIRONMENT at the HTTP
    # layer, which may be a comma-separated list).
    environment = payload.get('environment')
    if expected_environment is not None:
        if isinstance(expected_environment, str):
            accepted = {expected_environment}
        else:
            accepted = {e for e in expected_environment if e}
        if accepted and environment not in accepted:
            raise JwsVerificationError(
                'environment_mismatch',
                f"environment '{environment}' does not match expected "
                f"{sorted(accepted)}.")

    # [LOCAL-598B] Revocation. A refunded/revoked transaction carries a
    # revocationDate; it must never grant.
    if payload.get('revocationDate') is not None:
        raise JwsVerificationError(
            'transaction_revoked',
            'payload carries a revocationDate; the transaction is revoked.')

    transaction_id = payload.get('transactionId')
    if not transaction_id:
        raise JwsVerificationError('no_transaction_id', 'payload has no transactionId.')

    return VerifiedTransaction(
        transaction_id=str(transaction_id),
        product_id=str(product_id) if product_id is not None else '',
        bundle_id=str(bundle_id),
        type=str(tx_type),
        raw_payload=payload,
        environment=str(environment) if environment is not None else None,
    )
