##### READY FOR REVIEW

## LOCAL-321: Credential Encryption — Plaintext Read Path Removal & Design Proposal

**Branch:** `kiro/local321-credential-encryption`  
**Date:** 2026-08-06  
**Author:** Mac Mini Kiro

---

## 1. Current State (confirmed independently)

| Property | Value | Evidence |
|----------|-------|----------|
| `user_subscription_credentials` columns | `decrypted_username VARCHAR`, `decrypted_password VARCHAR` — **plaintext** | `\d user_subscription_credentials` — no encrypted/bytea columns in production |
| Encrypted columns in production DB | **DO NOT EXIST** | `SELECT column_name ... LIKE 'encrypted%'` → 0 rows |
| Rows stored | **0** | `SELECT COUNT(*) FROM user_subscription_credentials` → 0 |
| `CREDENTIAL_ENCRYPTION_ENABLED` | **off** (empty string default) | `newsletter_processor_service.py:43` |
| `migrate_credentials_encrypt.py` | Written, **never run** | Columns it would create don't exist |
| Production read path (`subscription_article_processor.py:59`) | Was: `SELECT decrypted_username, decrypted_password` | Now fixed (see §3) |
| `audio_tours` real count | **29** | `SELECT COUNT(*) FROM audio_tours WHERE is_test = false` |

---

## 2. Design Proposal — Preventing Database-Only Decryption

### The Threat

Anyone who obtains a database dump (backup leak, insider, compromised host) can read credentials directly from `decrypted_username` / `decrypted_password`. No additional secret is needed.

### Target Security Property

**A stored credential must not be readable by anyone holding only the database.**

### Assessment of Available Options

#### Option A: KMS Envelope Encryption (credential_encryption.py)

The existing design in `credential_encryption.py` uses Google Cloud KMS to wrap/unwrap a per-row DEK (data encryption key), then AES-256-GCM for the credential. The ciphertext + wrapped DEK go into BYTEA columns.

| Aspect | Assessment |
|--------|-----------|
| Feasibility on this deployment | **Not yet available.** `gcloud` CLI is not present on the Mac Mini. No KMS keyring has been provisioned. The migration script has never run. |
| What it solves | DB dump is useless without KMS `decrypt` permission (IAM-controlled). Key rotation is supported. Audit log on every unwrap. |
| What it doesn't solve | A fully-compromised Cloud Run instance with KMS access can still decrypt in memory. The server alone is sufficient — the device holds nothing. |
| Implementation cost | Low once KMS is provisioned: run `migrate_credentials_encrypt.py --add-columns`, modify write path in `submit_credentials`, flip the flag. |
| **Verdict** | **Workable. Blocks the immediate threat (DB dump). Requires GCP KMS provisioning, which is Michael's infrastructure decision.** |

#### Option B: Split-Key / Device-Derived Key (Michael's Instinct)

Michael's idea: the device holds part of the secret, so the server alone cannot decrypt.

The mobile app already performs a Diffie-Hellman key exchange (`subscription_encryption_service.dart`). The derived AES key is stored in `flutter_secure_storage` (Android Keystore / iOS Keychain). The server stores its DH private key in `newsletter_server_keys`.

A split-key scheme would work as follows:
1. Device generates a random per-credential "client key share" (e.g., 16 bytes) and stores it in `flutter_secure_storage`.
2. Server generates its own "server key share" (16 bytes).
3. The credential DEK is `HKDF(client_share || server_share)`.
4. Server encrypts the credential with this DEK and stores the ciphertext + server share.
5. To decrypt, the device must send its share with each request; neither party alone has the DEK.

| Aspect | Assessment |
|--------|-----------|
| Feasibility today | **Requires app changes.** The current mobile protocol submits credentials, and the server decrypts and stores them server-side. To do split-key, the app needs a new flow: (a) negotiate the split, (b) store its share, (c) present its share on every authenticated-article request. The `subscription_encryption_service.dart` already has secure storage infrastructure — it's architecturally ready, but requires a new endpoint and Dart-side logic. **This cannot be done from the server alone.** |
| What it solves | Even a compromised server + DB cannot decrypt without the device's share. Strongest possible guarantee. |
| What it doesn't solve | If the device is lost, credentials are irrecoverable (acceptable for third-party passwords). Each device must re-submit credentials individually (no credential sharing across devices without a re-key flow). |
| Implementation cost | Medium-high: new mobile endpoint, Dart secure-storage changes, server split-key derivation, migration of existing protocol. |
| **Verdict** | **Preferred end-state. Not implementable from this task (requires mobile app changes and Michael's protocol decision). Can be layered on top of Option A.** |

#### Option C: KMS + Client-Side Seal (Hybrid)

Combine Options A and B: use KMS envelope encryption at rest, AND require the device to present a "seal token" (HMAC of its DH-derived key + credential ID) that the server verifies before unwrapping. This gives:
- DB dump alone is useless (KMS protects at rest)
- Compromised server alone is useless (device seal required to trigger KMS unwrap)

| Aspect | Assessment |
|--------|-----------|
| Feasibility | Same as Option B — requires app changes to send a seal token. |
| **Verdict** | Best security, but same blocker as B. Worth targeting after KMS is provisioned and app protocol is updated. |

---

### Recommendation

**Phase 1 (unblocks Boston Globe rotation, no app changes needed):**
- Provision KMS keyring on GCP (Michael's action)
- Run `migrate_credentials_encrypt.py --add-columns` (non-destructive)
- Modify `submit_credentials` write path to encrypt before storage
- Flip `CREDENTIAL_ENCRYPTION_ENABLED=true` only after verification
- This gives: DB dump alone cannot reveal credentials

**Phase 2 (stronger, requires mobile release):**
- Implement split-key or client-seal-token protocol
- Device sends its share on each authenticated-article request
- Server cannot decrypt without device participation
- This gives: compromised server alone cannot reveal credentials

**What blocks Phase 1 right now:** KMS keyring provisioning. This is an infrastructure action that requires GCP console/CLI access with billing-owner permissions. Once `audiotours-migration:us-central1:audioura-keys:credential-encryption` exists, the code is ready.

---

## 3. Changes Made (This Commit)

### `credential_store.py` (NEW)
Centralized credential-reading module. Reads ONLY the encrypted columns (`encrypted_username`, `encrypted_password`, `wrapped_dek`, `encryption_nonce`). Returns `None` if no encrypted data exists. **Never reads `decrypted_username` or `decrypted_password`.**

### `subscription_article_processor.py`
- **Removed:** Direct SQL query reading `decrypted_username, decrypted_password`
- **Replaced with:** `from credential_store import get_credentials_for_device`
- Line 48–55: new 8-line method that delegates to credential_store

### `newsletter_processor_service.py`
- **Line ~1930:** Replaced inline SQL reading plaintext with `get_credentials_for_device()`
- **Line ~2065:** Same replacement at second read site
- Both sites wrapped in `try/except` to maintain existing error handling

### `credential_encryption.py`
- **Removed:** Plaintext fallback from `read_credentials()`. It no longer reads `decrypted_username`/`decrypted_password` and no longer logs "falling back to plaintext."
- Now returns `(None, None)` if encrypted columns are absent.

### `tests/test_credential_store.py` (NEW)
Three tests:
1. `test_plaintext_only_returns_none` — proves credential_store refuses to read plaintext columns
2. `test_encrypted_round_trip` — proves encrypt/decrypt works with AES-256-GCM (local DEK, mocked KMS)
3. `test_credential_store_query_excludes_plaintext_columns` — proves the SQL WHERE clause filters properly

---

## 4. Verification Evidence

### Tests
```
tests/test_credential_store.py::test_plaintext_only_returns_none PASSED
tests/test_credential_store.py::test_encrypted_round_trip PASSED
tests/test_credential_store.py::test_credential_store_query_excludes_plaintext_columns PASSED
3 passed in 0.14s
```

### Encrypted Round-Trip Proof
The test inserts a row with encrypted columns, then reads back via `credential_store`. The stored bytes are AES-256-GCM ciphertext (not plaintext):
- `encrypted_username`: opaque BYTEA (46 bytes including GCM tag)
- `encrypted_password`: opaque BYTEA (34 bytes including GCM tag)
- The DB never holds a readable secret.

### Production Safety
```sql
SELECT COUNT(*) FROM audio_tours WHERE is_test = false;
-- 29 (unchanged)

SELECT COUNT(*) FROM user_subscription_credentials;
-- 0 (no data at risk)
```

### Flag Status
`CREDENTIAL_ENCRYPTION_ENABLED` remains off (line 43, empty-string default). Credential endpoints remain disabled.

### Syntax Validation
All 4 modified/new Python files pass `py_compile`.

---

## 5. Plaintext Column Removal Plan (NOT EXECUTED)

Once encrypted storage is live and verified:
1. Confirm 0 rows have `wrapped_dek IS NULL` (all migrated)
2. `ALTER TABLE user_subscription_credentials DROP COLUMN decrypted_username;`
3. `ALTER TABLE user_subscription_credentials DROP COLUMN decrypted_password;`

**Not executed here** — column removal is destructive and is Michael's call per CLAUDE.md.

---

## 6. Limitations

1. **KMS is not provisioned.** The encrypted write path cannot be activated until the GCP KMS keyring is created. This is an infrastructure action outside this task's scope.
2. **Split-key requires mobile app changes.** The strongest design (device holds part of the key) cannot be implemented from the server alone. It requires a new mobile protocol endpoint and Dart-side changes.
3. **The plaintext columns still exist in the schema.** They are now unreachable from the read path, but a direct SQL INSERT into `decrypted_password` would still succeed. Column removal (§5) is the only complete mitigation, and requires Michael's approval.
4. **No real credential was tested.** All test values are obviously fake (`fake_test_user_local321@example.com`, `F4k3P@ssw0rd_L321!`).
5. **The `submit_credentials` write path still writes plaintext** — but it's gated behind `CREDENTIAL_ENDPOINTS_ENABLED` which is off. When the flag is enabled (after KMS provisioning), the write path in `submit_credentials` must also be updated to encrypt before writing.
