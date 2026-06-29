# REVIEW_FOR_KIRO — Encrypt-at-Rest for Subscription Credentials (2026-06-20)

**Task:** KMS envelope encryption for `user_subscription_credentials.decrypted_username` / `decrypted_password`.
**Status:** Code complete, KMS key created, migration script ready. **NOT deployed / NOT migrated** — awaiting Claude review per guardrail.

---

## What Was Built

### 1. KMS Infrastructure
- **Keyring:** `audioura-keys` (us-central1)
- **Key:** `credential-encryption` (symmetric, purpose=encryption)
- **Key path:** `projects/audiotours-migration/locations/us-central1/keyRings/audioura-keys/cryptoKeys/credential-encryption`

### 2. Encryption Module (`credential_encryption.py`)

**Envelope encryption flow:**
```
ENCRYPT: generate random DEK (32 bytes)
         → encrypt credential with DEK (AES-256-GCM)
         → wrap DEK with KMS
         → store (ciphertext + wrapped_dek + nonce)

DECRYPT: unwrap DEK with KMS
         → decrypt credential with DEK (AES-256-GCM)
```

**Key functions:**
- `encrypt_credentials_for_storage(username, password)` → dict with encrypted_username, encrypted_password, wrapped_dek, encryption_nonce
- `decrypt_credentials_from_storage(enc_username, enc_password, wrapped_dek, nonce)` → (username, password)
- `read_credentials(row)` → reads BOTH encrypted (preferred) and plaintext (fallback) — **migration-safe**

**Security properties:**
- AES-256-GCM (authenticated encryption — detects tampering)
- Per-row DEK (compromise of one row doesn't expose others)
- KMS-wrapped DEK (key never stored in plaintext; requires KMS access to decrypt)
- Unique nonce per row (username and password use adjacent nonces from same base)

### 3. Migration Script (`migrate_credentials_encrypt.py`)

Three steps (can be run independently):
1. `--add-columns` — adds `encrypted_username`, `encrypted_password`, `wrapped_dek`, `encryption_nonce` columns (non-destructive)
2. `--migrate` — encrypts existing plaintext rows into the new columns (plaintext preserved during transition)
3. `--verify` — decrypts migrated rows and compares against originals (round-trip test)

**Safety:** Plaintext columns are NEVER deleted or modified by this script. A separate `--clear-plaintext` step (not implemented) would only run after explicit approval.

### 4. Dependencies Added
`requirements.txt`: `google-cloud-kms==2.21.0`, `cryptography>=41.0.0`

---

## What's NOT Done (awaiting review)

- [ ] Column addition (Step 1) — not run against prod DB
- [ ] Live migration (Step 2) — not run against prod DB
- [ ] Integration into `newsletter_processor_service.py` credential read path — not wired yet
- [ ] Deployment of new image with encryption module — not built/deployed
- [ ] Clearing plaintext columns — explicitly deferred (separate approval)

---

## Files

| File | Purpose |
|------|---------|
| `development/credential_encryption.py` | Core encryption/decryption module |
| `development/migrate_credentials_encrypt.py` | DB migration script (add columns + encrypt + verify) |
| `development/requirements.txt` | Added google-cloud-kms + cryptography |

---

## How to Review / Approve

1. Review `credential_encryption.py` for crypto correctness (AES-256-GCM, nonce handling, KMS envelope)
2. Review migration script for safety (non-destructive, preserves plaintext during transition)
3. Approve → Kiro runs: add columns → migrate → verify → wire into credential read path → deploy
4. After verified working → separate approval to clear plaintext columns

---

## Risk

- **Low (crypto):** Using well-established `cryptography` library's AESGCM, not hand-rolled crypto.
- **Low (migration):** Plaintext preserved throughout — worst case, migration fails and we fall back to plaintext reads.
- **Medium (KMS dependency):** If KMS is unavailable, credential decryption fails. Mitigation: keep plaintext as fallback until confident, then clear.
- **IAM needed:** The compute service account (`60899077572-compute@developer.gserviceaccount.com`) needs `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the key to encrypt/decrypt DEKs.
