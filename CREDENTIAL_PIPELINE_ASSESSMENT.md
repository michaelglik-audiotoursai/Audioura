# Credential Pipeline Assessment

**Task:** LOCAL-148  
**Date:** 2026-08-02  
**Branch:** `kiro/local148-credential-pipeline-assessment`  
**Assessor:** Mac Mini Kiro

---

## ⚠️ SECURITY FINDING — PLAINTEXT CREDENTIAL STORAGE

**The `user_subscription_credentials` table stores newspaper usernames and
passwords in plaintext columns (`decrypted_username`, `decrypted_password`).**

The DH handshake encrypts credentials in transit (mobile → server), but the
server-side endpoint in `newsletter_processor_service.py` (line 2546)
immediately decrypts them and stores the plaintext:

```sql
INSERT INTO user_subscription_credentials
(device_id, article_id, domain, decrypted_username, decrypted_password, verified_at)
VALUES (%s, %s, %s, %s, %s, NOW())
```

A migration script exists (`migrate_credentials_encrypt.py`) that would add
KMS envelope encryption (`wrapped_dek`, `encrypted_username`, `encrypted_password`
as BYTEA), **but it has never run** — the table has no encrypted columns and
zero rows. The `credential_encryption.py` module references Google Cloud KMS
(`audiotours-migration` project, `audioura-keys` keyring) which may not be
provisioned.

This means: if the pipeline were activated today, any DB compromise would
expose every stored newspaper password in cleartext. Given that users reuse
passwords, this is a material risk.

---

## Verdict: UNFINISHED WORK — Complete, Do Not Delete

The credential pipeline is **actively wired** — not abandoned. The evidence:

1. The client-side code (Dart) is **live in the UI**. The credential dialog
   appears on real screens when `subscription_required == true` on an article.
2. The server-side endpoints (`/submit_credentials`, `/key_exchange`) are
   implemented in `newsletter_processor_service.py` (the active newsletter
   service).
3. Git history shows ongoing maintenance (endpoint audit, cloud-gate integration,
   error handling improvements) through at least 2026-06-23.
4. The DB tables exist with proper constraints.
5. `SUBSCRIBED_DESIGN.md` does NOT mention this pipeline — it's a pre-Subscribed
   feature for the Unlimited tier's "unrestricted content" value proposition.

**But it does not work today** because:
- The newsletter-processor (port 5017) is **not in `docker-compose-master.yml`**
  and **not currently running** as a container.
- Zero rows in all four pipeline tables (credentials, DH keys, AES keys,
  device encryption keys).
- The `subscription_article_processor.py` (Phase 2 — re-fetching paywalled
  content) requires `selenium` which is not installed.

---

## 1. What Exists — Module by Module

### A. `subscription_credentials_service.py` (port 5019)

**Purpose:** Standalone Flask service to receive/store encrypted credentials.  
**Status:** SUPERSEDED. This was an early standalone version. The same
functionality was later folded into `newsletter_processor_service.py` at its
`/submit_credentials` endpoint.  
**Import result:** ✅ Imports cleanly with no errors.  
**Would it run?** Yes, Flask would start. But the DB schema it expects
(`encrypted_username`, `encrypted_password` VARCHAR columns) does not match
the actual table (which has `decrypted_username`, `decrypted_password`).
It would INSERT and fail on column-not-found.  
**Importers:** Zero (confirmed via grep).

### B. `diffie_hellman_service.py`

**Purpose:** DH key exchange with PyCryptodome decryption. Creates DH tables.  
**Status:** SUPERSEDED by `dh_service_simple.py` (same logic, stdlib-only,
no PyCrypto dependency). The newsletter processor imports from `dh_service_simple`.  
**Import result:** ❌ `ModuleNotFoundError: No module named 'Crypto'`  
**Would it run?** No. PyCryptodome is not installed on the host.  
**Importers:** Only `tests/test_dh_integration.py` (test file).

### C. `subscription_article_processor.py`

**Purpose:** Phase 2 — after credentials are stored, re-fetch paywalled
articles using browser automation (Selenium + Boston Globe authenticator).  
**Status:** UNREACHED. The newsletter processor references credential
verification and user consolidation, but does NOT import this module. It
handles "reprocess" logic inline with a simpler count-and-flag approach.  
**Import result:** ❌ `ModuleNotFoundError: No module named 'selenium'`  
(transitive: `browser_automation.py` → `selenium`)  
**Would it run?** No. Missing selenium, and the module expects
`decrypted_username`/`decrypted_password` columns that DO exist in the DB
but would have no data.  
**Importers:** Only test files (`test_phase2_workflow.py`,
`test_boston_globe_auth_enhanced.py`).

### Summary: The Three Standalone Modules Are Dead

The *actual* running credential pipeline lives in:
- **`newsletter_processor_service.py`** — endpoints `/key_exchange` and
  `/submit_credentials`
- **`dh_service_simple.py`** — DH math (imported by newsletter processor)
- **`credential_verification_service.py`** — validates credentials actually
  work before storing

The three files named in the audit are earlier iterations that were replaced
by simpler implementations folded into the newsletter processor.

---

## 2. Database Findings

**Queries executed (read-only):**

```sql
SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_subscription_credentials');
-- Result: true

SELECT COUNT(*) FROM user_subscription_credentials;
-- Result: 0

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'user_subscription_credentials' ORDER BY ordinal_position;
```

| Column | Type |
|--------|------|
| id | integer |
| device_id | character varying |
| article_id | character varying |
| domain | character varying |
| created_at | timestamp without time zone |
| decrypted_username | character varying |
| decrypted_password | character varying |
| consolidated_user_id | character varying |
| verified_at | timestamp without time zone |

**Constraints:**
- PK: `id`
- UNIQUE: `(device_id, domain)`
- FK: `article_id → article_requests(article_id) ON DELETE CASCADE`

**No encrypted columns exist** (`wrapped_dek`, `encrypted_username`,
`encrypted_password`, `encryption_nonce` from `migrate_credentials_encrypt.py`
have never been added).

**Supporting tables (all empty):**

| Table | Rows |
|-------|------|
| `dh_server_keys` | 0 |
| `dh_aes_keys` | 0 |
| `device_encryption_keys` | 0 |

**`article_requests` does have `subscription_required` and
`subscription_domain` columns** — the detection side works.

---

## 3. Client Reachability — LIVE, Not Orphaned

The Dart client code is **directly reachable from the main UI**:

1. **`home_screen.dart`** (the app's primary screen) imports both
   `subscription_service.dart` and `subscription_encryption_service.dart`.

2. When a newsletter is processed and articles are displayed, articles with
   `subscription_required == true` render a red "SUBSCRIPTION REQUIRED"
   banner with a button.

3. Pressing that button opens `SubscriptionCredentialDialog` — a full
   username/password entry form that encrypts via DH and POSTs to
   `/submit_credentials` on `Service.newsletter` (port 5017).

4. The DH key exchange happens automatically during newsletter processing
   (`_processNewsletterWithUrl` calls `SubscriptionService.handleKeyExchange`).

5. The `SubscriptionManagementScreen` exists but is **orphaned** — no
   navigation route references it. It also imports disabled services
   (`credential_storage_service.dart`, `subscription_article_storage.dart`)
   that are commented out in `subscription_service.dart`.

**Bottom line:** A user who subscribes to a newsletter with paywalled articles
(e.g., Boston Globe) will SEE the credential dialog. When they submit,
the request goes to port 5017 (local) or `https://api.audioura.com/newsletter`
(cloud) — **but nothing is listening on either path today**.

---

## 4. What It Would Take

### Option A: Make It Work (Deployment + Code)

**Server side:**
1. Fix `Dockerfile.newsletter-processor` to COPY all dependencies:
   `dh_service_simple.py`, `credential_verification_service.py`,
   `user_consolidation_service.py`, `subscription_detector.py`. Currently
   the container would crash on startup with ImportError.
2. Add `newsletter-processor` to `docker-compose-master.yml` (port 5017).
   *Complexity: trivial — it's already in `docker-compose.yml`.*
3. Run `migrate_credentials_encrypt.py --add-columns` to add encrypted
   storage columns. Then fix the `submit_credentials` endpoint to store
   encrypted (currently stores plaintext).
4. Provision Google Cloud KMS keyring or switch to a simpler at-rest
   encryption (e.g., AWS KMS or even Fernet with a secret from env).
5. Install `selenium` + Chrome/Chromium if Phase 2 (re-fetching paywalled
   articles) is wanted. This is the heavy part — headless browser in Docker.

**Client side:**
- No changes needed. The app is ready.

**Rough sizing:**
- Deployment only (make the existing code work, plaintext storage): **2–4 hours**
- Deployment + at-rest encryption fix: **1–2 days**
- Deployment + encryption + browser automation (Phase 2): **1 week+**

**Riskiest part:** Browser automation for Boston Globe. Sites change selectors,
detect bots, add CAPTCHAs. This is perpetual maintenance. The credential
*storage* part without the *re-fetch* part still has value — it proves the
user has a subscription, even if the content must be extracted via
alternative means (RSS, API partners, etc.).

### Option B: Delete It

Remove from the codebase:
- 3 standalone Python files (already dead): `subscription_credentials_service.py`,
  `diffie_hellman_service.py`, `subscription_article_processor.py`
- ~250 lines from `newsletter_processor_service.py` (the live endpoints)
- `dh_service_simple.py`, `credential_encryption.py`,
  `migrate_credentials_encrypt.py`, `credential_verification_service.py`
- Dart files: `subscription_service.dart`, `subscription_encryption_service.dart`,
  `subscription_credential_dialog.dart`, `subscription_management_screen.dart`
- Remove credential-related code from `home_screen.dart`
- Drop 4 DB tables

**Rough sizing:** 1–2 days (careful extraction, testing that nothing breaks).

**Cost of deletion:** The Unlimited tier's $50/month value proposition includes
"unrestricted content." Without credential storage, paywalled articles cannot
be fetched. The app will detect subscription-required articles (that part works)
but can only show partial/teaser content.

---

## 5. Security Posture

### What's good:
- **DH key exchange is correctly implemented.** RFC 3526 Group 14 (2048-bit),
  SHA-256 key derivation, AES-128-CBC. Client and server use the same
  parameters. Verified via matching implementations in Dart and Python.
- **Transport encryption works.** Credentials are encrypted before leaving
  the device. The app uses `FlutterSecureStorage` (Keychain on iOS,
  EncryptedSharedPreferences on Android) for the local DH private key.
- **Credential verification before storage.** The server validates credentials
  actually work (via `credential_verification_service`) before persisting —
  prevents storing garbage.

### What's wrong:

1. **⚠️ CRITICAL: Plaintext storage at rest.** After DH decryption on the
   server, credentials are stored as cleartext VARCHAR. The migration to
   KMS envelope encryption exists as code but has never run. Any
   database dump, backup, or SQL injection would expose all stored passwords.

2. **No credential rotation or expiry.** Once stored, credentials live
   forever. No mechanism to detect revoked passwords or force re-entry.

3. **Server private keys stored as TEXT.** The `dh_server_keys` table stores
   DH private keys as plaintext strings. These should be ephemeral (use once
   during key exchange, then discard) or encrypted at rest.

4. **AES keys stored as plaintext hex.** The `dh_aes_keys` table stores
   derived AES session keys in cleartext. If an attacker has DB access,
   they can decrypt any in-transit capture.

5. **Debug logging in Dart prints credentials.** `subscription_service.dart`
   line 59 logs: `'SUBSCRIPTION: Calling SubscriptionEncryptionService.encryptCredentials with username="$username", password="$password"'`. These debug
   logs may persist on-device.

6. **The three standalone modules hardcode `password123` as DB password.**
   This is the actual development password. Not a security hole per se
   (it's local Docker), but it means these files cannot be deployed
   to production without env var changes.

### If this were to ship:

The minimum security bar before allowing real user credentials:
1. Run the encryption migration (or rewrite to never store plaintext)
2. Remove all debug prints that log plaintext credentials
3. Ensure DH private keys and session AES keys are ephemeral or encrypted
4. Add credential rotation (re-prompt after 90 days or on auth failure)

---

## Recommendation

**Complete, don't delete.** Reasons:

1. The client is live and user-visible. Deleting would require modifying
   `home_screen.dart` — the app's most complex file. Risk of regression.
2. The server-side code (in newsletter processor) is the bulk of the work
   already done. It needs deployment, not development.
3. The Unlimited tier's value proposition depends on it.
4. The security issues are fixable before any real user data flows
   (zero rows today means zero exposure so far).

**Suggested sequencing:**
1. Fix the security issues FIRST (at-rest encryption, remove debug logging)
2. Add newsletter-processor to docker-compose-master.yml
3. Test end-to-end with a real Boston Globe subscription
4. Only THEN decide if browser automation (Phase 2) is worth the maintenance

**The three standalone files** (`subscription_credentials_service.py`,
`diffie_hellman_service.py`, `subscription_article_processor.py`) can be
deleted immediately — they are superseded dead code that adds confusion.
The live implementation is in `newsletter_processor_service.py` +
`dh_service_simple.py`.

---

## Limitations

- **Cannot verify cloud deployment.** The cloud gateway path
  (`https://api.audioura.com/newsletter/submit_credentials`) was not tested.
  Assessment is based on local Docker infrastructure only.
- **Cannot test the Flutter app on device.** The client assessment is based
  on code reading and grep, not a running app. The credential dialog's
  actual user-reachability was inferred from code structure, not observed.
- **No APK build performed.** Docker builder is reported hung
  (per SUBSCRIBED_STATUS.md §4).
- **Newsletter processor's Dockerfile is BROKEN for credentials.**
  `Dockerfile.newsletter-processor` only COPYs `newsletter_processor_service.py`.
  It does NOT copy `dh_service_simple.py`, `credential_verification_service.py`,
  `user_consolidation_service.py`, or `subscription_detector.py` — all of
  which are imported at module level. **The container would crash on startup
  with ImportError.** This is a deployment blocker, not just a missing service
  in compose.
- **$0.00 API spend confirmed.** No external services called, no credentials
  created/stored/transmitted.
