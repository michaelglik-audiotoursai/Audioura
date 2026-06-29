"""
Credential Encryption — KMS Envelope Encryption for subscription credentials
=============================================================================
Uses Google Cloud KMS to wrap/unwrap a data encryption key (DEK).
The DEK encrypts credentials with AES-256-GCM (authenticated encryption).

Envelope encryption flow:
  ENCRYPT: generate random DEK → encrypt credential with DEK (AES-256-GCM)
           → wrap DEK with KMS → store (ciphertext + wrapped_dek + nonce)
  DECRYPT: unwrap DEK with KMS → decrypt credential with DEK (AES-256-GCM)

Columns affected (user_subscription_credentials):
  encrypted_username  BYTEA  — AES-256-GCM ciphertext
  encrypted_password  BYTEA  — AES-256-GCM ciphertext
  wrapped_dek         BYTEA  — KMS-wrapped data encryption key
  encryption_nonce    BYTEA  — GCM nonce (unique per row)

Migration: reads BOTH plaintext (decrypted_*) and encrypted columns during transition.
"""
import os
import base64
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# KMS configuration
KMS_PROJECT = os.getenv('GCP_PROJECT', 'audiotours-migration')
KMS_LOCATION = os.getenv('KMS_LOCATION', 'us-central1')
KMS_KEYRING = os.getenv('KMS_KEYRING', 'audioura-keys')
KMS_KEY = os.getenv('KMS_KEY', 'credential-encryption')

KMS_KEY_PATH = f"projects/{KMS_PROJECT}/locations/{KMS_LOCATION}/keyRings/{KMS_KEYRING}/cryptoKeys/{KMS_KEY}"


def _get_kms_client():
    """Get a KMS client (lazy import for services that don't need it)."""
    from google.cloud import kms
    return kms.KeyManagementServiceClient()


def generate_and_wrap_dek():
    """Generate a random 256-bit DEK and wrap it with KMS.
    Returns (plaintext_dek_bytes, wrapped_dek_bytes)."""
    # Generate random 32-byte DEK
    dek = os.urandom(32)
    
    # Wrap the DEK with KMS
    client = _get_kms_client()
    response = client.encrypt(
        request={
            'name': KMS_KEY_PATH,
            'plaintext': dek,
        }
    )
    wrapped_dek = response.ciphertext
    
    return dek, wrapped_dek


def unwrap_dek(wrapped_dek):
    """Unwrap a DEK using KMS. Returns plaintext DEK bytes."""
    client = _get_kms_client()
    response = client.decrypt(
        request={
            'name': KMS_KEY_PATH,
            'ciphertext': wrapped_dek,
        }
    )
    return response.plaintext


def encrypt_credential(plaintext_value, dek, nonce):
    """Encrypt a credential value with AES-256-GCM.
    Args:
        plaintext_value: str — the credential to encrypt
        dek: bytes — 32-byte data encryption key
        nonce: bytes — 12-byte GCM nonce (must be unique per encryption)
    Returns: ciphertext bytes (includes GCM tag)
    """
    aesgcm = AESGCM(dek)
    plaintext_bytes = plaintext_value.encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
    return ciphertext


def decrypt_credential(ciphertext, dek, nonce):
    """Decrypt a credential value with AES-256-GCM.
    Args:
        ciphertext: bytes — encrypted credential (with GCM tag)
        dek: bytes — 32-byte data encryption key
        nonce: bytes — 12-byte GCM nonce used during encryption
    Returns: str — the decrypted credential
    """
    aesgcm = AESGCM(dek)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext_bytes.decode('utf-8')


def encrypt_credentials_for_storage(username, password):
    """Encrypt username + password for database storage.
    Generates a fresh DEK and nonce per credential pair.
    
    Returns dict with:
        encrypted_username: bytes
        encrypted_password: bytes
        wrapped_dek: bytes  (KMS-wrapped data key)
        encryption_nonce: bytes  (12-byte GCM nonce)
    """
    # Generate and wrap a fresh DEK
    dek, wrapped_dek = generate_and_wrap_dek()
    
    # Generate a unique nonce (12 bytes for GCM)
    nonce = os.urandom(12)
    
    # Encrypt both credentials with the same DEK+nonce (safe for GCM with different plaintexts)
    # Actually, GCM requires unique nonce per plaintext. Use nonce for username, nonce+1 for password.
    nonce_username = nonce
    nonce_password = (int.from_bytes(nonce, 'big') + 1).to_bytes(12, 'big')
    
    encrypted_username = encrypt_credential(username, dek, nonce_username)
    encrypted_password = encrypt_credential(password, dek, nonce_password)
    
    return {
        'encrypted_username': encrypted_username,
        'encrypted_password': encrypted_password,
        'wrapped_dek': wrapped_dek,
        'encryption_nonce': nonce,  # Store base nonce; password uses nonce+1
    }


def decrypt_credentials_from_storage(encrypted_username, encrypted_password, wrapped_dek, encryption_nonce):
    """Decrypt stored credentials using the wrapped DEK.
    
    Args:
        encrypted_username: bytes
        encrypted_password: bytes
        wrapped_dek: bytes (KMS-wrapped)
        encryption_nonce: bytes (12-byte base nonce)
    
    Returns: (username_str, password_str)
    """
    # Unwrap the DEK via KMS
    dek = unwrap_dek(wrapped_dek)
    
    # Reconstruct nonces
    nonce_username = encryption_nonce
    nonce_password = (int.from_bytes(encryption_nonce, 'big') + 1).to_bytes(12, 'big')
    
    # Decrypt
    username = decrypt_credential(encrypted_username, dek, nonce_username)
    password = decrypt_credential(encrypted_password, dek, nonce_password)
    
    return username, password


def read_credentials(row):
    """Read credentials from a DB row, handling both plaintext (legacy) and encrypted formats.
    
    Args:
        row: dict-like with keys: decrypted_username, decrypted_password,
             encrypted_username, encrypted_password, wrapped_dek, encryption_nonce
    
    Returns: (username_str, password_str) or (None, None) if no credentials
    """
    # Prefer encrypted columns (new format)
    if row.get('wrapped_dek') and row.get('encrypted_username'):
        try:
            return decrypt_credentials_from_storage(
                row['encrypted_username'],
                row['encrypted_password'],
                row['wrapped_dek'],
                row['encryption_nonce']
            )
        except Exception as e:
            logging.error(f"[CRED_ENCRYPT] Decryption failed, falling back to plaintext: {e}")
    
    # Fall back to plaintext columns (legacy, pre-migration)
    username = row.get('decrypted_username')
    password = row.get('decrypted_password')
    if username and password:
        return username, password
    
    return None, None
