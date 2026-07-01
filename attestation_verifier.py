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
