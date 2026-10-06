"""
apple_jws_verifier.py — LOCAL-598 D5: OFFLINE verification of a StoreKit 2
JWS signed transaction.

Apple's App Store Server API / StoreKit 2 hands the device a `signedTransaction`
in JWS compact form:

    base64url(header) . base64url(payload) . base64url(signature)

The JOSE header carries an `x5c` chain (leaf, intermediate, root) of DER certs,
base64 (standard, not url) encoded. Verifying the transaction needs NO network
and NO API key — everything is in the JWS plus the Apple Root CA G3 we bundle:

  1. Decode the header, read x5c (must be a 3-cert chain: leaf -> intermediate
     -> Apple Root CA G3).
  2. Pin the root: the last cert in x5c must be byte-identical to our bundled
     Apple Root CA G3. (We also independently verify the chain's signatures.)
  3. Verify the chain: root signs intermediate, intermediate signs leaf.
  4. Verify the JWS signature (ES256 / P-256) over
     `base64url(header).base64url(payload)` with the LEAF cert's public key.
  5. Read the payload and check: bundleId == expected, productId == expected,
     type == "Consumable".

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
from dataclasses import dataclass
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature


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


def _verify_chain(x5c_der: list[bytes], root_ca_pem: bytes) -> x509.Certificate:
    """Verify the x5c chain and pin the Apple root. Returns the LEAF cert.

    Expects [leaf, intermediate, root]. The provided root must be byte-identical
    to the bundled Apple Root CA G3 (pin), AND the chain's internal signatures
    must all verify (root->intermediate->leaf)."""
    if len(x5c_der) < 2:
        raise JwsVerificationError(
            'chain_too_short', 'x5c must contain the leaf and its issuer chain.')

    certs = []
    for der in x5c_der:
        try:
            certs.append(x509.load_der_x509_certificate(der))
        except Exception as e:
            raise JwsVerificationError('cert_parse_failed', f'Bad certificate in x5c: {e}')

    bundled_root = _load_root_ca(root_ca_pem)

    # Pin: the chain's final cert must be exactly our Apple Root CA G3. Compare
    # the DER bytes (fingerprint) so a look-alike root is rejected outright.
    presented_root = certs[-1]
    if presented_root.fingerprint(hashes.SHA256()) != bundled_root.fingerprint(hashes.SHA256()):
        raise JwsVerificationError(
            'root_not_apple',
            'The x5c root is not the pinned Apple Root CA G3.')

    # Verify each link: certs[i] is signed by certs[i+1], up to the root.
    for i in range(len(certs) - 1):
        _verify_cert_signed_by(certs[i], certs[i + 1])

    # The pinned root is self-signed; verify that too for completeness.
    _verify_cert_signed_by(presented_root, bundled_root)

    return certs[0]


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
def verify_signed_transaction(
    jws: str,
    root_ca_pem: bytes,
    expected_bundle_id: str,
    expected_product_id: Optional[str] = None,
    required_type: str = 'Consumable',
) -> VerifiedTransaction:
    """Verify a StoreKit 2 JWS signed transaction offline.

    Args:
        jws: the compact JWS string (header.payload.signature).
        root_ca_pem: PEM bytes of the pinned Apple Root CA G3.
        expected_bundle_id: the app's bundle id (e.g. com.audioura.audiotours).
        expected_product_id: if given, the payload productId must equal it.
        required_type: the payload `type` must equal this (default Consumable).

    Returns a VerifiedTransaction on success. Raises JwsVerificationError with a
    stable `.code` on any failure. Performs NO network and NO DB access.
    """
    if not jws or jws.count('.') != 2:
        raise JwsVerificationError('malformed_jws', 'Expected a compact JWS with 3 parts.')

    header_b64, payload_b64, signature_b64 = jws.split('.')

    # --- header + x5c ---
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
        # x5c entries are STANDARD base64 (with padding) of DER certs.
        x5c_der = [base64.b64decode(c) for c in x5c]
    except Exception as e:
        raise JwsVerificationError('bad_x5c', f'Could not base64-decode x5c: {e}')

    # --- chain + root pin ---
    leaf = _verify_chain(x5c_der, root_ca_pem)

    # --- signature over header.payload ---
    try:
        signature_raw = _b64url_decode(signature_b64)
    except Exception as e:
        raise JwsVerificationError('bad_signature', f'Could not decode signature: {e}')
    signing_input = f'{header_b64}.{payload_b64}'.encode('ascii')
    _verify_jws_signature(signing_input, signature_raw, leaf)

    # --- payload claims (only trusted AFTER the signature verified) ---
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        raise JwsVerificationError('bad_payload', f'Could not decode payload: {e}')

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

    transaction_id = payload.get('transactionId')
    if not transaction_id:
        raise JwsVerificationError('no_transaction_id', 'payload has no transactionId.')

    return VerifiedTransaction(
        transaction_id=str(transaction_id),
        product_id=str(product_id) if product_id is not None else '',
        bundle_id=str(bundle_id),
        type=str(tx_type),
        raw_payload=payload,
    )
