# Credential Crypto Design — Phone-Present Only

**Summary for Michael:** Your newspaper credentials (e.g., Boston Globe
username and password) will be stored on our server encrypted with a key
that only exists on your phone. If hackers steal our entire database and
all our server code, they get useless ciphertext — they cannot decrypt
without your phone. The cost: article fetching only works while you have
the app open, and if you lose the phone or reinstall, you re-enter your
passwords (which is the security feature working as intended).

---

## 1. Where Each Key Lives

| Key material | Location | Persistence |
|---|---|---|
| **Phone DH private key** | Phone only — Android EncryptedSharedPreferences / iOS Keychain via `FlutterSecureStorage` | Survives app restarts; destroyed on uninstall or Keychain wipe |
| **Phone DH public key** | Transmitted to server during key exchange; stored on phone in secure storage | Phone + in-transit (one-time) |
| **Server DH private key** | Server memory only, for the duration of a single session | **Ephemeral** — generated per key-exchange, used once to derive shared secret, then discarded (never persisted to DB) |
| **Server DH public key** | Transmitted to phone during newsletter processing | In-transit only |
| **Derived AES-128 key** | Phone secure storage (persistent); server memory (ephemeral, session-scoped) | Phone: persistent. Server: **never stored.** |
| **Encrypted credentials** | Database (`user_subscription_credentials` table) as BYTEA | At rest — useless without the AES key |
| **Plaintext credentials** | Server memory, briefly, only during an active fetch request when the phone provides the decryption key | Seconds. Zeroed after use. |

### Critical difference from the current code

The current `dh_service_simple.py` stores the server private key in
`newsletter_server_keys` and the derived AES key in `dh_aes_keys` — **both
in plaintext in the database.** This defeats the entire purpose. A DB dump
gives an attacker: encrypted creds + AES key = plaintext. The new design
**must not persist any key material on the server.**

---

## 2. Why a Server Compromise Fails

**Scenario:** Attacker has full database dump, all source code, all
environment variables, all secrets.

**What they find in the database:**
- `user_subscription_credentials`: rows with `encrypted_username` (BYTEA)
  and `encrypted_password` (BYTEA) — AES-128-CBC ciphertext.
- `phone_credential_nonce` or equivalent: the IV prepended to each
  ciphertext (needed for decryption but not secret).
- No AES keys. No DH private keys. No wrapped DEKs. No KMS references.

**What they find in the code:**
- The derivation algorithm (DH Group 14 → SHA-256 → first 16 bytes = AES key).
- The encryption algorithm (AES-128-CBC, PKCS7 padding, IV prepended).

**What stops them:**
- The AES key is derived from `shared_secret = server_public^phone_private mod p`.
- They have neither `phone_private` (on the phone's Keychain) nor
  `server_private` (was ephemeral, never persisted).
- Without either private key, computing the shared secret requires solving
  the Discrete Logarithm Problem in a 2048-bit group — computationally
  infeasible.

**Honest limitation — active session window:**

If an attacker compromises the server *while a user's phone is actively
performing a fetch*, the derived AES key exists in server process memory for
the duration of that request (seconds). A sufficiently sophisticated
attacker with live memory access could extract it. This is the inherent cost
of "phone-present" over "phone-only" (where the phone does the decryption
itself and never sends the key). Michael should understand this is a
seconds-wide window, not a persistent exposure.

---

## 3. Session Flow

```
1. USER OPENS APP, navigates to a subscription-required article

2. APP → SERVER: POST /credential_session_start
   Body: { device_id, article_id }
   
3. SERVER: generates ephemeral DH keypair (private_s, public_s)
   Holds private_s in memory ONLY (not DB).
   SERVER → APP: { server_public_key: hex(public_s), session_id: uuid }

4. APP: retrieves stored phone DH private key from Keychain
   Computes: shared_secret = server_public^phone_private mod p
   Derives: aes_key = SHA256(shared_secret)[:16]
   APP → SERVER: POST /credential_session_unlock
   Body: { session_id, device_id, client_public_key: hex(phone_public) }

5. SERVER: computes shared_secret = phone_public^server_private mod p
   Derives: aes_key = SHA256(shared_secret)[:16]
   Decrypts credentials from DB using this AES key.
   Uses credentials to fetch the paywalled article.
   ─── Plaintext credentials exist in memory HERE (step 5 only) ───
   
6. SERVER: returns fetched article content to app.
   IMMEDIATELY: zeroes aes_key, zeroes plaintext credentials, 
   discards server_private from memory.
   The session_id is invalidated.

7. APP: displays article. Key material unchanged in Keychain
   (ready for next session).
```

**Where assembled key exists:** Server process memory, step 5 only. Duration:
the time to decrypt two VARCHAR values + perform one HTTP fetch to the
newspaper site (typically 2–10 seconds).

**Key material lifecycle:**
- Server DH private key: created at step 3, destroyed at step 6 (~seconds).
- Server-side AES key: derived at step 5, destroyed at step 6 (~seconds).
- Phone-side AES key: persistent in Keychain (this is by design — it's
  the same key every time, allowing stored creds to remain decryptable
  across sessions without re-entering them).

---

## 4. What Happens When the Phone Is Absent

**The server cannot decrypt.** Period. There is no background processing,
no scheduled re-fetch, no queuing.

**Product consequences:**
- Newsletter processing that discovers a `subscription_required` article
  **flags it but does not fetch full content.** The user sees a teaser/summary
  with a "Full article requires your presence" indicator.
- When the user next opens the app and views that article, the phone-present
  session (steps 1–7 above) fires and fetches the full content on demand.
- If the user never opens the app for that article, it stays unfetched.

**This is the honest cost of Option 1.** A KMS-based approach (Option 2, which
Michael rejected) would allow background fetching because the server can
decrypt on its own. Phone-present means: no phone, no decryption, no fetch.

**Recommendation:** Show a clear UI state: "📱 Open app to unlock full
article" — not an error, a feature. The user chose security over convenience.

---

## 5. Key Loss

**Phone lost, stolen, or app reinstalled → credentials are unrecoverable.**

The AES key that encrypted the stored credentials existed only on that phone
(derived from the phone's DH private key, which lived in the Keychain and is
gone). The server has ciphertext it can never decrypt.

**This is a feature, not a bug.** It is exactly Michael's requirement: "if
our server is penetrated by hackers, they would not be able to get the
credentials." The same property that protects against hackers protects
against key loss.

**What happens:**
1. Server detects the phone is new (new device_id or re-registration).
2. Old encrypted rows for that device become dead ciphertext.
3. User is prompted to re-enter credentials.
4. A new DH handshake establishes a new key; credentials are re-encrypted
   under the new key.
5. Old rows can be garbage-collected.

**There is no recovery mechanism, and there should not be one.** Any
"recovery" path (backup key, server escrow, email reset) would reintroduce
exactly the server-side decryptability that Michael rejected.

---

## 6. What Existing Code Survives

| File | Verdict | Reason |
|---|---|---|
| `dh_service_simple.py` | **REWRITE** | DH math is correct (RFC 3526 Group 14, SHA-256 derivation). But it stores private keys and AES keys to the database — that behavior must be removed entirely. The pure-math functions (`generate_server_keypair`, `calculate_shared_secret`, `derive_aes_key`) survive; the `store_*` and DB functions are deleted. |
| `credential_encryption.py` | **DELETE** | Implements KMS envelope encryption — the exact approach Michael rejected. None of it applies to phone-present. |
| `migrate_credentials_encrypt.py` | **DELETE** | Adds KMS columns (`wrapped_dek`, `encryption_nonce`) that do not exist in the phone-present design. |
| `newsletter_processor_service.py` `/key_exchange` endpoint | **REWRITE** | The handshake concept survives but must not persist key material. The endpoint should return the ephemeral server public key and hold private key in memory only. |
| `newsletter_processor_service.py` `/submit_credentials` endpoint | **REWRITE** | Currently decrypts then stores **plaintext** (`decrypted_username`, `decrypted_password`). Must instead: receive phone-encrypted credentials, store them as ciphertext, never decrypt at submission time. Decryption only happens during a phone-present fetch session. |
| `subscription_encryption_service.dart` (Flutter) | **KEEP, minor cleanup** | DH key generation, shared-secret derivation, AES encryption are all correct and needed. Remove debug `print` statements that log plaintext credentials and key material. |
| DB table `dh_server_keys` | **DROP** | Server private keys must never be persisted. |
| DB table `dh_aes_keys` | **DROP** | Derived AES keys must never be persisted. |
| DB table `device_encryption_keys` | **DROP** | Not used, not needed. |
| DB table `newsletter_server_keys` | **DROP** | Same as `dh_server_keys` — server private keys must be ephemeral. |
| DB columns `decrypted_username`, `decrypted_password` | **DROP** | Plaintext storage is the vulnerability. Replaced by `encrypted_username`, `encrypted_password` (BYTEA). |

---

## 7. Schema Change (SQL — not applied)

```sql
-- STEP 1: Add encrypted columns
ALTER TABLE user_subscription_credentials
  ADD COLUMN encrypted_username BYTEA,
  ADD COLUMN encrypted_password BYTEA,
  ADD COLUMN encryption_iv BYTEA;          -- IV used during encryption (needed for AES-CBC decrypt)

-- STEP 2: Drop plaintext columns (AFTER code changes deployed)
ALTER TABLE user_subscription_credentials
  DROP COLUMN decrypted_username,
  DROP COLUMN decrypted_password;

-- STEP 3: Drop tables that should never have existed
DROP TABLE IF EXISTS dh_server_keys;
DROP TABLE IF EXISTS dh_aes_keys;
DROP TABLE IF EXISTS device_encryption_keys;
DROP TABLE IF EXISTS newsletter_server_keys;

-- STEP 4: Add a device registration table (tracks which phone public key
-- was used to encrypt which credential row — needed for garbage collection
-- after key loss, and for the session handshake)
CREATE TABLE credential_device_keys (
  id SERIAL PRIMARY KEY,
  device_id VARCHAR(255) NOT NULL UNIQUE,
  phone_public_key_hex TEXT NOT NULL,      -- phone's DH public key (for session derivation)
  registered_at TIMESTAMP DEFAULT NOW(),
  last_session_at TIMESTAMP               -- updated each successful session
);

-- STEP 5: Link credentials to the device key that encrypted them
ALTER TABLE user_subscription_credentials
  ADD COLUMN credential_device_id INTEGER REFERENCES credential_device_keys(id);
```

**Note:** `encryption_iv` stores the random IV prepended to the AES-CBC
ciphertext. It is not secret — just required for decryption alongside the key.
Some implementations prepend IV to the ciphertext blob (as the Dart code
currently does); if that convention is kept, `encryption_iv` as a separate
column is optional. Design choice for the implementation ticket.

---

## 8. Honest Assessment — Is Phone-Present Usable?

**Yes, with one product constraint Michael must accept:**

The feature as originally conceived (background newsletter processing fetches
paywalled articles automatically) is **incompatible** with phone-present
encryption. The server cannot fetch paywalled content without credentials,
and it cannot get credentials without the phone.

**What works:**
- User submits credentials once (phone encrypts and stores).
- User opens app, taps a subscription-required article → phone-present
  session decrypts → server fetches full content → user reads it.
- Credentials are entered once, used many times (Michael's requirement:
  "user would not have to enter the same credentials many times").

**What doesn't work:**
- Automatic background fetching of paywalled articles while phone is idle.
- Pre-caching full paywalled articles for offline reading without user
  interaction.

**This is acceptable** because:
1. The current system already requires the user to be in the app (there is
   no background article fetching today — LOCAL-147 gated the endpoints).
2. Michael explicitly said: "Fetching happens while the user is in the app.
   No background processing."
3. The latency added (2–10 seconds for the session handshake + fetch) is
   within acceptable UX for reading a news article.

**If requirements change later** (e.g., "I want background fetching"), that
would require revisiting Option 2 (server-side KMS) or a hybrid where the
phone pre-authorizes a time-limited token. That's a different design.

---

## 9. Threat Model Summary

| Threat | Mitigated? | How |
|---|---|---|
| Database dump | ✅ Yes | Ciphertext only; no keys stored |
| Server code + secrets stolen | ✅ Yes | Keys are ephemeral in memory, not in env vars or config |
| Man-in-the-middle (network) | ✅ Yes | DH exchange over HTTPS; even without HTTPS, DH prevents passive eavesdropping |
| Attacker with live server memory access during active session | ⚠️ Partially | Key exists for seconds during fetch; attacker needs process-level access at exactly that moment |
| Phone theft (unlocked) | ⚠️ Partially | FlutterSecureStorage uses OS Keychain/Keystore (hardware-backed on most devices); app-level PIN/biometric would add a layer but is not in scope |
| Phone loss / reinstall | ✅ By design | Credentials become unrecoverable → user re-enters (this IS the security model) |
| Insider with DB access | ✅ Yes | Same as database dump — no keys at rest |
| Brute-force the AES key | ✅ Yes | AES-128 = 2^128 keyspace; infeasible |
| Solve DH discrete log | ✅ Yes | 2048-bit group; infeasible with known algorithms |
