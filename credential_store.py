"""
Credential Store — the ONLY module that reads credentials from the database.
=============================================================================
Centralizes all credential access so the plaintext columns can be retired.

This module reads ONLY the encrypted columns (encrypted_username,
encrypted_password, wrapped_dek, encryption_nonce). It does NOT read
decrypted_username or decrypted_password.

If the encrypted columns do not yet exist, or are NULL for a given row,
this module returns None — it will not fall back to plaintext.

Rationale (LOCAL-321):
  A stored credential must not be readable by anyone holding only the
  database. The plaintext columns are a design defect. Even though the
  table is currently empty and the credential endpoints are disabled,
  the read path must not reference the plaintext columns so that no
  future code path can accidentally populate and serve them.

  When encryption is provisioned (KMS or equivalent), the write path
  in submit_credentials will write to the encrypted columns, and this
  module will decrypt them via credential_encryption.decrypt_credentials_from_storage().

Usage:
  from credential_store import get_credentials_for_device
  result = get_credentials_for_device(device_id, domain)
  # result is {'username': ..., 'password': ...} or None
"""
import logging
import os

logger = logging.getLogger(__name__)


def _get_db_connection():
    """Get a database connection using the shared db_connection module.

    Uses tests/db_connection.py routing when available (respects
    AUDIOURA_DB_TARGET, pytest detection, etc.). Falls back to direct
    psycopg2 connection with env vars.
    """
    try:
        from tests.db_connection import get_connection
        return get_connection()
    except (ImportError, SystemExit):
        pass

    # Fallback: direct connection with env vars
    import psycopg2
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT', '5433')
    )


def get_credentials_for_device(device_id, domain):
    """Retrieve decrypted credentials for a device+domain pair.

    Returns:
        dict with 'username' and 'password' keys, or None if no
        encrypted credentials are stored for this device+domain.

    This function reads ONLY encrypted columns. If the row has no
    wrapped_dek (i.e. was never encrypted), it returns None.
    """
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT encrypted_username, encrypted_password,
                   wrapped_dek, encryption_nonce
            FROM user_subscription_credentials
            WHERE device_id = %s AND domain = %s
              AND wrapped_dek IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """, (device_id, domain))

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return None

        encrypted_username, encrypted_password, wrapped_dek, encryption_nonce = row

        # Decrypt using the KMS-backed envelope encryption
        from credential_encryption import decrypt_credentials_from_storage
        username, password = decrypt_credentials_from_storage(
            bytes(encrypted_username),
            bytes(encrypted_password),
            bytes(wrapped_dek),
            bytes(encryption_nonce)
        )

        return {'username': username, 'password': password}

    except Exception as e:
        logger.error(f"[CREDENTIAL_STORE] Error reading credentials for "
                     f"device={device_id} domain={domain}: {e}")
        return None
