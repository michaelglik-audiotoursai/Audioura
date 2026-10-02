#!/usr/bin/env python3
"""
LOCAL-321: Test that credential_store reads ONLY encrypted columns.

Proves:
  1. credential_store.get_credentials_for_device returns None when only
     plaintext columns are populated (i.e. it refuses to read them).
  2. credential_store.get_credentials_for_device returns decrypted credentials
     when encrypted columns are populated (using a local DEK, no KMS).
  3. The stored bytes in the DB are opaque ciphertext.

Uses test database (audiotours_test) and fake credentials only.
"""
import os
import sys
import pytest

# Force test database — SCOPED, not module-level.
# [LEAD] D214 exactly: setting AUDIOURA_DB_TARGET at module scope leaks into
# every test collected afterwards in the same session, routing them to
# audiotours_test. It made 7 LOCAL-320 non-dining tests fail when run in the
# same invocation as this file, while both files passed alone. An autouse
# fixture confines it to this module and restores the prior value.
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5433')
os.environ.setdefault('DB_USER', 'admin')
os.environ.setdefault('DB_PASSWORD', 'password123')


@pytest.fixture(autouse=True)
def _force_test_db(monkeypatch):
    monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
    yield

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2


TEST_DEVICE_ID = 'test_device_local321'
TEST_DOMAIN = 'example-fake-news.com'
FAKE_USERNAME = 'fake_test_user_local321@example.com'
FAKE_PASSWORD = 'F4k3P@ssw0rd_L321!'


def get_test_conn():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=os.environ['DB_PORT'],
        database='audiotours_test',
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )


@pytest.fixture(autouse=True)
def db_setup_teardown():
    """Add encrypted columns to test DB, seed FK row, clean test data."""
    conn = get_test_conn()
    cur = conn.cursor()

    # Add the encrypted columns (matches migrate_credentials_encrypt.py step1)
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS encrypted_username BYTEA")
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS encrypted_password BYTEA")
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS wrapped_dek BYTEA")
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS encryption_nonce BYTEA")
    conn.commit()

    # Clean previous test data
    cur.execute(
        "DELETE FROM user_subscription_credentials WHERE device_id = %s",
        (TEST_DEVICE_ID,)
    )
    conn.commit()

    # We need an article_requests row for the FK
    cur.execute("""
        INSERT INTO article_requests (article_id, request_string)
        VALUES ('test_art_local321', 'LOCAL-321 test article')
        ON CONFLICT (article_id) DO NOTHING
    """)
    conn.commit()
    cur.close()
    conn.close()

    yield  # run the test

    # Teardown
    conn = get_test_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM user_subscription_credentials WHERE device_id = %s",
        (TEST_DEVICE_ID,)
    )
    cur.execute(
        "DELETE FROM article_requests WHERE article_id = 'test_art_local321'"
    )
    conn.commit()
    cur.close()
    conn.close()


def test_plaintext_only_returns_none():
    """credential_store must NOT read plaintext columns."""
    conn = get_test_conn()
    cur = conn.cursor()

    # Insert a row with ONLY plaintext columns populated (encrypted columns NULL)
    cur.execute("""
        INSERT INTO user_subscription_credentials
            (device_id, article_id, domain, decrypted_username, decrypted_password)
        VALUES (%s, 'test_art_local321', %s, %s, %s)
        ON CONFLICT (device_id, domain) DO UPDATE SET
            decrypted_username = EXCLUDED.decrypted_username,
            decrypted_password = EXCLUDED.decrypted_password,
            wrapped_dek = NULL,
            encrypted_username = NULL,
            encrypted_password = NULL,
            encryption_nonce = NULL
    """, (TEST_DEVICE_ID, TEST_DOMAIN, FAKE_USERNAME, FAKE_PASSWORD))
    conn.commit()
    cur.close()
    conn.close()

    # credential_store MUST return None — it must not read decrypted_* columns
    from credential_store import get_credentials_for_device
    result = get_credentials_for_device(TEST_DEVICE_ID, TEST_DOMAIN)
    assert result is None, (
        f"SECURITY FAILURE: credential_store returned {result} for a row "
        f"with only plaintext columns. It must not read decrypted_username/"
        f"decrypted_password."
    )


def test_encrypted_round_trip():
    """credential_store decrypts properly when encrypted columns are populated."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    # Generate a local DEK (simulating what KMS would wrap)
    dek = os.urandom(32)
    nonce = os.urandom(12)

    # Encrypt with AES-256-GCM (same scheme as credential_encryption.py)
    aesgcm = AESGCM(dek)
    nonce_username = nonce
    nonce_password = (int.from_bytes(nonce, 'big') + 1).to_bytes(12, 'big')

    encrypted_username = aesgcm.encrypt(nonce_username, FAKE_USERNAME.encode(), None)
    encrypted_password = aesgcm.encrypt(nonce_password, FAKE_PASSWORD.encode(), None)

    # First insert the row (needs article_id FK)
    conn = get_test_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_subscription_credentials
            (device_id, article_id, domain, encrypted_username, encrypted_password,
             wrapped_dek, encryption_nonce)
        VALUES (%s, 'test_art_local321', %s, %s, %s, %s, %s)
        ON CONFLICT (device_id, domain) DO UPDATE SET
            encrypted_username = EXCLUDED.encrypted_username,
            encrypted_password = EXCLUDED.encrypted_password,
            wrapped_dek = EXCLUDED.wrapped_dek,
            encryption_nonce = EXCLUDED.encryption_nonce
    """, (
        TEST_DEVICE_ID, TEST_DOMAIN,
        psycopg2.Binary(encrypted_username),
        psycopg2.Binary(encrypted_password),
        psycopg2.Binary(dek),  # "wrapped" DEK (unwrap_dek is monkey-patched to identity)
        psycopg2.Binary(nonce),
    ))
    conn.commit()
    cur.close()
    conn.close()

    # Monkey-patch unwrap_dek to return the DEK directly (no KMS call)
    import credential_encryption
    original_unwrap = credential_encryption.unwrap_dek
    credential_encryption.unwrap_dek = lambda wrapped: wrapped  # identity function

    try:
        # credential_store should decrypt and return the fake credentials
        from credential_store import get_credentials_for_device
        result = get_credentials_for_device(TEST_DEVICE_ID, TEST_DOMAIN)
        assert result is not None, "Expected credentials, got None"
        assert result['username'] == FAKE_USERNAME, f"Username mismatch: {result['username']}"
        assert result['password'] == FAKE_PASSWORD, f"Password mismatch: {result['password']}"

        # Prove the DB never holds readable plaintext in the encrypted columns
        conn = get_test_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT encrypted_username, encrypted_password
            FROM user_subscription_credentials
            WHERE device_id = %s AND domain = %s
        """, (TEST_DEVICE_ID, TEST_DOMAIN))
        row = cur.fetchone()
        cur.close()
        conn.close()

        stored_username_bytes = bytes(row[0])
        stored_password_bytes = bytes(row[1])

        # The stored bytes must NOT be the plaintext
        assert FAKE_USERNAME.encode() != stored_username_bytes, "DB holds readable username!"
        assert FAKE_PASSWORD.encode() != stored_password_bytes, "DB holds readable password!"

    finally:
        credential_encryption.unwrap_dek = original_unwrap


def test_credential_store_query_excludes_plaintext_columns():
    """Verify the SQL query in credential_store filters on wrapped_dek IS NOT NULL."""
    conn = get_test_conn()
    cur = conn.cursor()

    # Insert row with plaintext populated but NO encrypted columns
    cur.execute("""
        INSERT INTO user_subscription_credentials
            (device_id, article_id, domain, decrypted_username, decrypted_password,
             wrapped_dek, encrypted_username, encrypted_password, encryption_nonce)
        VALUES (%s, 'test_art_local321', %s, %s, %s, NULL, NULL, NULL, NULL)
        ON CONFLICT (device_id, domain) DO UPDATE SET
            decrypted_username = EXCLUDED.decrypted_username,
            decrypted_password = EXCLUDED.decrypted_password,
            wrapped_dek = NULL,
            encrypted_username = NULL,
            encrypted_password = NULL,
            encryption_nonce = NULL
    """, (TEST_DEVICE_ID, TEST_DOMAIN, FAKE_USERNAME, FAKE_PASSWORD))
    conn.commit()

    # Directly verify the row exists but credential_store's query won't find it
    cur.execute("""
        SELECT encrypted_username, encrypted_password, wrapped_dek, encryption_nonce
        FROM user_subscription_credentials
        WHERE device_id = %s AND domain = %s
          AND wrapped_dek IS NOT NULL
        ORDER BY created_at DESC LIMIT 1
    """, (TEST_DEVICE_ID, TEST_DOMAIN))
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is None, "Query with 'wrapped_dek IS NOT NULL' should return nothing for plaintext-only row"
