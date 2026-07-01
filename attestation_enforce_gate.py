"""
Attestation Enforce Gate — enforce mode stub (NOT activated for Aug 1).
========================================================================
DO NOT wire into gateway until after Aug 1 tester build is live and
log-only data has been reviewed.

Task [S58]: should_block_request(verdict_dict, platform) — returns True
if verdict indicates UNEVALUATED_INTEGRITY or FAILED_MEETS_DEVICE_INTEGRITY
AND ATTESTATION_MODE=enforce. Returns False in all other cases.
"""
import os


def should_block_request(verdict_dict: dict | None, platform: str) -> bool:
    """Determine whether a request should be blocked based on attestation verdict.

    This function is a STUB for post-Aug-1 enforcement. It is NOT imported by
    the gateway service in the Aug 1 release. It will be activated only after
    log-only mode data has been reviewed and the tester build is live.

    Args:
        verdict_dict: The attestation verdict dictionary from verify_play_integrity()
                      or verify_app_attest(). May be None if verification failed.
        platform: 'android' or 'ios'.

    Returns:
        True if the request should be blocked (enforce mode + bad verdict).
        False in all other cases (log_only mode, valid verdict, None verdict, etc.).
    """
    attestation_mode = os.getenv("ATTESTATION_MODE", "log_only")

    # Never block unless explicitly in enforce mode
    if attestation_mode != "enforce":
        return False

    # If no verdict available, do not block (fail open)
    if not verdict_dict:
        return False

    # Android: check deviceIntegrity verdict
    if platform.lower() == "android":
        device_integrity = verdict_dict.get("deviceIntegrity", {})
        recognition_verdicts = device_integrity.get("deviceRecognitionVerdict", [])

        # Block if explicitly unevaluated or failed
        blocked_verdicts = {"UNEVALUATED", "FAILED_MEETS_DEVICE_INTEGRITY"}
        if not recognition_verdicts:
            # Empty verdict list = unevaluated
            return True
        for v in recognition_verdicts:
            if v in blocked_verdicts:
                return True
        return False

    # iOS: check fmt_valid and auth_data_present from verify_app_attest
    if platform.lower() == "ios":
        fmt_valid = verdict_dict.get("fmt_valid", False)
        auth_data_present = verdict_dict.get("auth_data_present", False)
        # Block only if format is clearly invalid
        if not fmt_valid and not auth_data_present:
            return True
        return False

    # Unknown platform — do not block
    return False
