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
| Production read path 1 (`subscription_article_processor.py:59`) | Was: `SELECT decrypted_username, decrypted_password` | Now fixed — uses `credential_store` |
| Production read path 2 (`user_consolidation_service.py:38,67`) | Was: reads/matches plaintext columns | Now fixed — uses `credential_store` + blind index |
| `audio_tours` real count | **29** | `SELECT COUNT(*) FROM audio_tours WHERE is_test = false` |

---

## 2. Complete Enumeration of All Readers of Plaintext Columns

Searched via `grep -rn "decrypted_username\|decrypted_password" --include="*.py"` across all files.

### Live Service Read Paths (all fixed)

| File | Line(s) | What it did | Status |
|------|---------|-------------|--------|
| `subscription_article_processor.py` | 59 | `SELECT decrypted_username, decrypted_password` | **Fixed (prior commit)** — uses `credential_store` |
| `user_consolidation_service.py` | 38 | `SELECT domain, decrypted_username, decrypted_password, consolidated_user_id` | **Fixed (this commit)** — uses `credential_store` |
| `user_consolidation_service.py` | 67 | `WHERE domain = %s AND decrypted_username = %s AND decrypted_password = %s` | **Fixed (this commit)** — uses blind index HMAC |

### Live Write Path (NOT a read; gated behind disabled flag)

| File | Line(s) | What it does | Status |
|------|---------|-------------|--------|
| `newsletter_processor_service.py` | 2517-2523 | `INSERT INTO ... decrypted_username, decrypted_password` | **Not changed** — this is the write path, gated behind `CREDENTIAL_ENDPOINTS_ENABLED` (off). When KMS is provisioned, this must be modified to encrypt before writing. Documented as limitation. |

### Non-service files (not changed, not live read paths)

| Category | Files | Reason not changed |
|----------|-------|--------------------|
| Migration script | `migrate_credentials_encrypt.py` | Designed to read plaintext and encrypt it — that's its purpose. Only runs manually. |
| Decrypt utilities | `decrypt_*.py` (7 files) | Debug/diagnostic tools, not called by any service. |
| Test helper | `generate_test_credentials.py` | Test utility only. |
| DB seed job | `db-job/run.py:65` | Pre-existing test data INSERT. Explicitly excluded from this task. |
| Test files | `tests/test_phase2_*.py`, `tests/test_phase3_*.py` | Test harnesses that simulate the write path. |
| Docs/reviews | Various `.md` files | Documentation only. |

---

## 3. Design Proposal — Preventing Database-Only Decryption

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
- Add `credential_blind_index` BYTEA column (for consolidation matching)
- Populate blind index at write time using `CREDENTIAL_BLIND_INDEX_KEY` env var
- Flip `CREDENTIAL_ENCRYPTION_ENABLED=true` only after verification
- This gives: DB dump alone cannot reveal credentials

**Phase 2 (stronger, requires mobile release):**
- Implement split-key or client-seal-token protocol
- Device sends its share on each authenticated-article request
- Server cannot decrypt without device participation
- This gives: compromised server alone cannot reveal credentials

**What blocks Phase 1 right now:** KMS keyring provisioning. This is an infrastructure action that requires GCP console/CLI access with billing-owner permissions. Once `audiotours-migration:us-central1:audioura-keys:credential-encryption` exists, the code is ready.

---

## 4. The Consolidation Matching Problem (Line 67)

### Why it's worse than a simple plaintext read

The original `find_matching_credentials()` used:
```sql
WHERE domain = %s AND decrypted_username = %s AND decrypted_password = %s
```

This is defeated by encryption at rest because:
1. AES-GCM ciphertext is randomized — you cannot do equality matching on it
2. The plaintext secret appears in query parameters and statement logs
3. SQL equality is non-constant-time (timing side channel)

### Solution: Blind Index (keyed HMAC)

A blind index stores `HMAC-SHA256(key, domain||username||password)` alongside the encrypted credential. Properties:
- **Deterministic**: same inputs → same HMAC → SQL equality works
- **Non-reversible**: the HMAC cannot be inverted to recover the credential
- **Key-separated**: requires `CREDENTIAL_BLIND_INDEX_KEY` (held in environment, not DB)
- **Constant-time comparison available**: `hmac.compare_digest()` can be used app-side if needed

### Schema addition needed (Phase 1)

```sql
ALTER TABLE user_subscription_credentials
    ADD COLUMN credential_blind_index BYTEA;  -- HMAC-SHA256, 32 bytes

CREATE INDEX idx_cred_blind_domain ON user_subscription_credentials
    (domain, credential_blind_index);
```

### What's implemented now

`user_consolidation_service.py` already uses the blind index path:
- If `CREDENTIAL_BLIND_INDEX_KEY` is not set → returns `[]` (no matches, graceful degradation)
- If set → queries `credential_blind_index` column instead of plaintext

**Today with 0 rows and the flag off**, consolidation always returns "new_user" — which is correct and safe.

---

## 5. Changes Made (This Commit)

### `user_consolidation_service.py` (MODIFIED)
- **`get_user_credentials_by_device()`**: Replaced `SELECT decrypted_username, decrypted_password` with a two-step approach: (1) SELECT non-secret columns (domain, consolidated_user_id) filtering for `wrapped_dek IS NOT NULL`, (2) decrypt via `credential_store.get_credentials_for_device()`.
- **`find_matching_credentials()`**: Replaced plaintext WHERE clause with blind index (HMAC-SHA256) comparison. Falls back to empty list if `CREDENTIAL_BLIND_INDEX_KEY` is not configured.
- **Added `_compute_credential_blind_index()`**: Module-level function computing `HMAC-SHA256(key, domain\x00username\x00password)`. Returns `None` if key env var is absent.
- **No `decrypted_username` or `decrypted_password` appears in any SQL query in this file.**

### `credential_store.py` (unchanged from prior commit)
Centralized credential-reading module. Reads ONLY encrypted columns.

### `subscription_article_processor.py` (unchanged from prior commit)
Delegates to `credential_store.get_credentials_for_device()`.

### `tests/test_consolidation_no_plaintext.py` (NEW)
8 tests verifying:
- Blind index is deterministic, domain-sensitive, password-sensitive
- Returns None without env var key
- Output is 32 bytes (SHA-256)
- `find_matching_credentials` returns [] without key
- SQL executed by `find_matching_credentials` uses `credential_blind_index`, not `decrypted_*`
- SQL executed by `get_user_credentials_by_device` does not reference `decrypted_*`

---

## 6. Verification Evidence

### Tests (all pass)
```
tests/test_consolidation_no_plaintext.py::TestBlindIndex::test_deterministic PASSED
tests/test_consolidation_no_plaintext.py::TestBlindIndex::test_different_domain_different_index PASSED
tests/test_consolidation_no_plaintext.py::TestBlindIndex::test_different_password_different_index PASSED
tests/test_consolidation_no_plaintext.py::TestBlindIndex::test_output_is_32_bytes PASSED
tests/test_consolidation_no_plaintext.py::TestBlindIndex::test_returns_none_without_key PASSED
tests/test_consolidation_no_plaintext.py::TestConsolidationNoPlaintext::test_find_matching_credentials_no_key_returns_empty PASSED
tests/test_consolidation_no_plaintext.py::TestConsolidationNoPlaintext::test_find_matching_uses_blind_index_column PASSED
tests/test_consolidation_no_plaintext.py::TestConsolidationNoPlaintext::test_get_user_credentials_no_plaintext_sql PASSED

tests/test_credential_store.py::test_plaintext_only_returns_none PASSED
tests/test_credential_store.py::test_encrypted_round_trip PASSED
tests/test_credential_store.py::test_credential_store_query_excludes_plaintext_columns PASSED

11 passed total
```

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
```
python3 -c "import py_compile; py_compile.compile('user_consolidation_service.py', doraise=True)"
# Success — no output
```

### No Remaining Live Reads of Plaintext Columns
```
grep -rn "decrypted_username\|decrypted_password" --include="*.py" | grep -v tests/ | grep -v decrypt_ | grep -v generate_test | grep -v migrate_credentials | grep -v db-job/
```
Results: only docstrings/comments in `credential_store.py` and `user_consolidation_service.py`, plus the disabled write path in `newsletter_processor_service.py:2517-2523`.

---

## 7. Plaintext Column Removal Plan (NOT EXECUTED)

Once encrypted storage is live and verified:
1. Confirm 0 rows have `wrapped_dek IS NULL` (all migrated)
2. `ALTER TABLE user_subscription_credentials DROP COLUMN decrypted_username;`
3. `ALTER TABLE user_subscription_credentials DROP COLUMN decrypted_password;`

**Not executed here** — column removal is destructive and is Michael's call per CLAUDE.md.

---

## 8. Limitations

1. **KMS is not provisioned.** The encrypted write path cannot be activated until the GCP KMS keyring is created. This is an infrastructure action outside this task's scope.
2. **Split-key requires mobile app changes.** The strongest design (device holds part of the key) cannot be implemented from the server alone. It requires a new mobile protocol endpoint and Dart-side changes.
3. **The plaintext columns still exist in the schema.** They are now unreachable from all read paths, but a direct SQL INSERT into `decrypted_password` would still succeed. Column removal (§7) is the only complete mitigation, and requires Michael's approval.
4. **No real credential was tested.** All test values are obviously fake (`fake_user@example.com`, `F4k3P@ss!`).
5. **The `submit_credentials` write path still writes plaintext** (newsletter_processor_service.py:2517) — but it's gated behind `CREDENTIAL_ENDPOINTS_ENABLED` which is off. When the flag is enabled (after KMS provisioning), the write path must be updated to: (a) encrypt before writing, and (b) compute and store the blind index.
6. **The `credential_blind_index` column does not yet exist in the database.** The consolidation service gracefully returns empty results until both the column is added and `CREDENTIAL_BLIND_INDEX_KEY` is configured. The schema migration for this column should be included in the Phase 1 KMS provisioning work.
7. **Consolidation matching is unavailable until Phase 1 is complete.** With the blind index key absent and 0 rows in the table, `handle_credential_submission_with_consolidation` always returns `{"action": "new_user"}`. This is correct behavior — there are no credentials to consolidate.
8. **`db-job/run.py:65` contains a literal test password.** Pre-existing, not introduced by this task, explicitly excluded from scope.
