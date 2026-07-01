"""
Attestation Verifier — log-only mode (Storied release).
=========================================================
Validates attestation token structure and logs the result.
NEVER blocks a request — always returns verified=True in log-only mode.
Actual Google Play Integrity / Apple App Attest verification is [S54].
"""
import logging

logger = logging.getLogger(__name__)


def verify_attestation_token(token: str | None, platform: str, request_id: str) -> dict:
    """Verify an attestation token (log-only mode — never blocks).

    Args:
        token: The attestation token from X-App-Attestation header (may be None).
        platform: 'android' or 'ios' (from X-App-Platform header).
        request_id: A request identifier for correlation in logs.

    Returns:
        dict with keys:
            verified: bool — always True in log-only mode
            log_only: bool — always True (enforcement is [S58])
            token_present: bool — whether a non-empty token was provided
            token_length: int — length of the token (0 if absent)
            platform: str — the platform value received
    """
    token_present = bool(token and str(token).strip())
    token_length = len(str(token)) if token else 0

    result = {
        "verified": True,
        "log_only": True,
        "token_present": token_present,
        "token_length": token_length,
        "platform": platform or "unknown",
    }

    logger.info(
        f"ATTESTATION LOG: platform={result['platform']} "
        f"request_id={request_id} "
        f"token_present={token_present} "
        f"token_length={token_length} "
        f"verdict=log_only"
    )

    return result


def verify_play_integrity(token: str | None, package_name: str, api_key: str) -> dict:
    """Verify a Google Play Integrity token (log-only — NEVER blocks).

    Calls the Play Integrity API to decode the token and extract device/app
    integrity verdicts. Logs the result but never denies a request.

    Args:
        token: The integrity token from the Android app.
        package_name: The app's package name (e.g. 'com.audioura.app').
        api_key: Google Cloud API key with Play Integrity API enabled.

    Returns:
        dict with keys:
            verified: True (always — log-only mode)
            log_only: True (always)
            verdict: dict with deviceIntegrity/appIntegrity or None on error
    """
    import requests as _requests

    result = {
        "verified": True,
        "log_only": True,
        "verdict": None,
    }

    if not token or not str(token).strip():
        logger.info("PLAY_INTEGRITY_VERDICT: token_absent=True verdict=None (no token provided)")
        return result

    url = f"https://playintegrity.googleapis.com/v1/{package_name}:decodeIntegrityToken"

    try:
        response = _requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}" if api_key else "",
            },
            json={"integrity_token": str(token)},
            timeout=10,
        )

        if response.status_code != 200:
            logger.warning(
                f"PLAY_INTEGRITY_VERDICT: api_error={response.status_code} "
                f"body={response.text[:200]} verdict=None"
            )
            return result

        data = response.json()
        token_payload = data.get("tokenPayloadExternal", {})
        device_integrity = token_payload.get("deviceIntegrity", {})
        app_integrity = token_payload.get("appIntegrity", {})

        verdict = {
            "deviceIntegrity": device_integrity,
            "appIntegrity": app_integrity,
            "requestDetails": token_payload.get("requestDetails", {}),
        }
        result["verdict"] = verdict

        logger.info(f"PLAY_INTEGRITY_VERDICT: {verdict}")

    except _requests.Timeout:
        logger.warning("PLAY_INTEGRITY_VERDICT: timeout verdict=None")
    except Exception as e:
        logger.error(f"PLAY_INTEGRITY_VERDICT: error={e} verdict=None")

    return result


def verify_app_attest(
    attestation_object: bytes | str | None,
    key_id: str = "",
    app_id: str = "",
) -> dict:
    """Verify an Apple App Attest attestation object (log-only — NEVER blocks).

    Format check only (no Apple server call in log-only mode):
    - Attempts CBOR decode
    - Checks fmt == "apple-appattest"
    - Checks authData present

    Args:
        attestation_object: Raw CBOR bytes or base64 string from the iOS app.
        key_id: The key identifier associated with the attestation.
        app_id: The app's bundle ID (e.g. 'com.audioura.app').

    Returns:
        dict with verified=True, log_only=True (always — never blocks).
    """
    result = {
        "verified": True,
        "log_only": True,
        "fmt_valid": False,
        "auth_data_present": False,
        "key_id": key_id or "unknown",
    }

    if not attestation_object:
        logger.info(
            f"APP_ATTEST_VERDICT: key_id={key_id} fmt_valid=False "
            f"auth_data_present=False reason=no_attestation_object"
        )
        return result

    try:
        import base64

        # Convert base64 string to bytes if needed
        if isinstance(attestation_object, str):
            try:
                raw_bytes = base64.b64decode(attestation_object)
            except Exception:
                raw_bytes = attestation_object.encode("utf-8")
        else:
            raw_bytes = bytes(attestation_object) if not isinstance(attestation_object, bytes) else attestation_object

        # Attempt CBOR-like structure validation
        # Full CBOR parsing requires cbor2 library; for log-only we do basic format check
        # Apple App Attest CBOR starts with a map containing 'fmt' and 'attStmt'
        # We check for known byte patterns without requiring cbor2 dependency

        # Check if it looks like CBOR (starts with map marker 0xa or contains 'apple-appattest')
        fmt_marker = b"apple-appattest"
        auth_data_marker = b"authData"

        fmt_valid = fmt_marker in raw_bytes
        auth_data_present = auth_data_marker in raw_bytes

        result["fmt_valid"] = fmt_valid
        result["auth_data_present"] = auth_data_present

        logger.info(
            f"APP_ATTEST_VERDICT: key_id={key_id} fmt_valid={fmt_valid} "
            f"auth_data_present={auth_data_present} size={len(raw_bytes)}"
        )

    except Exception as e:
        logger.error(f"APP_ATTEST_VERDICT: key_id={key_id} error={e} (malformed input)")

    return result
