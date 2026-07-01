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
