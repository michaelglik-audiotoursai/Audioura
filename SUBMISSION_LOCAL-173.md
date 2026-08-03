##### READY FOR REVIEW

## LOCAL-173 — Phone-Present Credential Crypto Design

**Commit:** `960ec15`  
**Branch:** `kiro/local173-credential-crypto-design`  
**Base:** `subscribed`  
**Commits ahead:** 1

---

### Per-File Changes

| File | Action | Lines |
|------|--------|-------|
| `CREDENTIAL_CRYPTO_DESIGN.md` | Created | +275 |

No other files modified. No code written. No schema applied. No containers
touched. `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md` untouched.

---

### Evidence — Sources Read

1. **`CREDENTIAL_PIPELINE_ASSESSMENT.md`** — LOCAL-148 assessment confirming:
   - `user_subscription_credentials` has plaintext columns, 0 rows
   - `dh_server_keys`, `dh_aes_keys`, `device_encryption_keys` all exist, all empty
   - The client (Dart) is live and user-reachable
   - The server endpoints exist but nothing is listening (no container)

2. **`credential_encryption.py`** — KMS envelope encryption using Google Cloud
   KMS (`audiotours-migration` project, `audioura-keys` keyring). This is the
   approach Michael rejected.

3. **`migrate_credentials_encrypt.py`** — Migration script to add KMS columns
   (`wrapped_dek`, `encrypted_username` BYTEA, etc.). Never run. Also rejected.

4. **`dh_service_simple.py`** — DH math (RFC 3526 Group 14, 2048-bit). Correct
   cryptography but **stores server private keys to DB** (`newsletter_server_keys`
   table) and **stores derived AES keys to DB** (`dh_aes_keys` table). Both
   defeat phone-present security.

5. **`newsletter_processor_service.py`** lines 2370–2560 — `/key_exchange` and
   `/submit_credentials` endpoints. Key exchange persists server private key.
   Submit decrypts then stores **plaintext** (`decrypted_username`,
   `decrypted_password`).

6. **`audio_tour_app/lib/services/subscription_encryption_service.dart`** —
   Client-side DH implementation. RFC 3526 Group 14, SHA-256 key derivation,
   AES-128-CBC with PKCS7 padding, `FlutterSecureStorage` for key persistence.
   Correct implementation; excessive debug logging of plaintext credentials.

7. **Database query (read-only)** — Confirmed schema:
   ```
   user_subscription_credentials: 9 columns, 0 rows
     id, device_id, article_id, domain, created_at,
     decrypted_username (VARCHAR 255), decrypted_password (VARCHAR 255),
     consolidated_user_id, verified_at
   dh_server_keys: 0 rows
   dh_aes_keys: 0 rows
   device_encryption_keys: 0 rows
   newsletter_server_keys: 0 rows
   ```

---

### Key Findings

1. **`credential_encryption.py` and `migrate_credentials_encrypt.py` implement
   the wrong design.** They use server-side KMS envelope encryption — the server
   can decrypt on its own. Michael chose Option 1 (phone-present only) and
   explicitly rejected this. Both files should be deleted.

2. **`dh_service_simple.py` persists keys that must be ephemeral.** The DH math
   is correct; the database storage functions defeat the security model. The
   math survives; the persistence is removed.

3. **The current `/submit_credentials` stores plaintext.** Line 2546 does
   `INSERT ... decrypted_username, decrypted_password`. This is the exact
   vulnerability Michael wants eliminated.

4. **This is greenfield.** Zero rows in all four tables. No migration needed.
   No data to protect, convert, or lose. Clean slate.

5. **Phone-present is usable but constrains the product.** No background
   fetching of paywalled articles. Michael already accepted this ("Fetching
   happens while the user is in the app. No background processing.").

---

### Limitations

- **D46 not found in `DECISIONS.md`.** The file currently contains D1–D31.
  Michael's decision and choice were taken directly from the task description.
  If D46 exists elsewhere (e.g., a newer version of DECISIONS.md on another
  branch), the design should be cross-checked against the exact wording.

- **No cryptographic library audit performed.** The design assumes
  `pointycastle` (Dart) and `cryptography` (Python) implement AES-128-CBC
  correctly. No independent verification of their implementations was done.

- **Active-session memory exposure acknowledged but not mitigated.** During
  the seconds when the server holds the derived AES key in memory, a
  sufficiently privileged attacker with live process access could extract it.
  No design can eliminate this while the server does the fetching. The
  alternative (phone fetches directly) has its own problems (IP fingerprinting,
  CORS, cookies).

- **No database writes performed.** Schema verified read-only. The SQL in
  section 7 of the design is proposed, not applied.

- **`DECISIONS.md` not edited.** D46 recording is a separate action for when
  Michael approves this design.
