#!/usr/bin/env python3
"""
Credential Encryption Migration Script
========================================
Adds encrypted columns to user_subscription_credentials and migrates existing
plaintext credentials to KMS envelope encryption.

SAFETY: This script is migration-safe — after migration, BOTH old plaintext
and new encrypted columns exist. The read path (credential_encryption.read_credentials)
prefers encrypted, falls back to plaintext.

Run order:
  1. Add columns (safe, non-destructive)
  2. Migrate existing rows (encrypts plaintext → encrypted columns)
  3. [AFTER VERIFICATION] Clear plaintext columns (separate script, after Claude review)

DO NOT run step 3 without explicit approval.
"""
import os
import sys
import psycopg2

# For Cloud Run job: use unix socket
DB_HOST = os.getenv('DB_HOST', '/cloudsql/audiotours-migration:us-central1:audioura-db')
DB_NAME = os.getenv('DB_NAME', 'audiotours')
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASSWORD')

def get_conn():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)


def step1_add_columns():
    """Add encrypted columns (non-destructive — existing data untouched)."""
    print("=== Step 1: Adding encrypted columns ===")
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS encrypted_username BYTEA")
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS encrypted_password BYTEA")
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS wrapped_dek BYTEA")
    cur.execute("ALTER TABLE user_subscription_credentials ADD COLUMN IF NOT EXISTS encryption_nonce BYTEA")
    
    conn.commit()
    cur.close()
    conn.close()
    print("  Columns added (or already exist)")


def step2_migrate_existing():
    """Encrypt existing plaintext credentials into the new columns."""
    print("\n=== Step 2: Migrating existing credentials ===")
    
    # Import encryption module
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from credential_encryption import encrypt_credentials_for_storage
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Find rows with plaintext but no encrypted data
    cur.execute("""
        SELECT id, decrypted_username, decrypted_password 
        FROM user_subscription_credentials 
        WHERE decrypted_username IS NOT NULL 
          AND decrypted_password IS NOT NULL
          AND wrapped_dek IS NULL
    """)
    rows = cur.fetchall()
    print(f"  Found {len(rows)} rows to migrate")
    
    migrated = 0
    for row_id, username, password in rows:
        try:
            encrypted = encrypt_credentials_for_storage(username, password)
            
            cur.execute("""
                UPDATE user_subscription_credentials 
                SET encrypted_username = %s,
                    encrypted_password = %s,
                    wrapped_dek = %s,
                    encryption_nonce = %s
                WHERE id = %s
            """, (
                psycopg2.Binary(encrypted['encrypted_username']),
                psycopg2.Binary(encrypted['encrypted_password']),
                psycopg2.Binary(encrypted['wrapped_dek']),
                psycopg2.Binary(encrypted['encryption_nonce']),
                row_id
            ))
            migrated += 1
        except Exception as e:
            print(f"  ERROR migrating row {row_id}: {e}")
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"  Migrated {migrated}/{len(rows)} rows")


def step3_verify():
    """Verify encrypted credentials can be decrypted correctly."""
    print("\n=== Step 3: Verification ===")
    
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from credential_encryption import decrypt_credentials_from_storage
    
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, decrypted_username, decrypted_password,
               encrypted_username, encrypted_password, wrapped_dek, encryption_nonce
        FROM user_subscription_credentials 
        WHERE wrapped_dek IS NOT NULL
        LIMIT 5
    """)
    rows = cur.fetchall()
    
    verified = 0
    for row in rows:
        row_id = row[0]
        original_username = row[1]
        original_password = row[2]
        
        try:
            decrypted_username, decrypted_password = decrypt_credentials_from_storage(
                bytes(row[3]), bytes(row[4]), bytes(row[5]), bytes(row[6])
            )
            
            if decrypted_username == original_username and decrypted_password == original_password:
                print(f"  ✅ Row {row_id}: encrypt → decrypt round-trip OK")
                verified += 1
            else:
                print(f"  ❌ Row {row_id}: MISMATCH after round-trip!")
        except Exception as e:
            print(f"  ❌ Row {row_id}: Decryption error: {e}")
    
    cur.close()
    conn.close()
    print(f"\n  Verified: {verified}/{len(rows)} rows")
    return verified == len(rows)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--add-columns', action='store_true', help='Step 1: add encrypted columns')
    ap.add_argument('--migrate', action='store_true', help='Step 2: encrypt existing credentials')
    ap.add_argument('--verify', action='store_true', help='Step 3: verify round-trip')
    ap.add_argument('--all', action='store_true', help='Run all steps')
    args = ap.parse_args()
    
    if args.all or args.add_columns:
        step1_add_columns()
    if args.all or args.migrate:
        step2_migrate_existing()
    if args.all or args.verify:
        success = step3_verify()
        if not success:
            sys.exit(1)
    
    if not any([args.all, args.add_columns, args.migrate, args.verify]):
        print("Usage: python migrate_credentials_encrypt.py --all | --add-columns | --migrate | --verify")
