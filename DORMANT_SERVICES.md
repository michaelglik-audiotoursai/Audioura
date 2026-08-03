# Dormant Services Inventory — LOCAL-149

**Date:** 2026-08-02  
**Author:** Mac Mini Kiro  
**Context:** D40 — a dormant service was restored and exposed a live plaintext-credential endpoint.  
**Purpose:** Before any further restoration, enumerate what every dormant service serves.

---

## Method

1. Compared `docker-compose.yml` (old dev compose) against `docker-compose-master.yml` (active stack).
2. Identified services present in old compose but absent from master.
3. Identified services referenced by the mobile app (`endpoints.dart`) that have no running container.
4. Identified standalone service files (with Flask routes or HTTP handlers) that exist in the repo with no compose entry anywhere.
5. Enumerated routes by grep for `@app.route`, `add_url_rule`, and HTTP handler methods (`do_GET`/`do_POST`).
6. Cross-referenced `docker ps` output (captured without starting anything) against both compose files.

**What this method would miss:**
- Dynamically registered routes (e.g., via Blueprint `register_blueprint` in an import that wasn't traced).
- Routes added by imported modules that themselves register Flask routes at import time (newsletter_processor imports `user_consolidation_service` and `credential_verification_service` which register as Blueprints — these were checked and found to be plain classes, not Blueprint-registering modules).
- Any service whose source file has been deleted but whose Docker image still exists with baked-in code from an earlier commit.

---

## 1. newsletter-processor (port 5017) — `newsletter_processor_service.py`

**Risk verdict: DO NOT RESTORE — accepts third-party credentials in plaintext, writes them to DB unencrypted.**

This is the service that caused the D40 incident. It was restored by LOCAL-147, found to expose credential endpoints, and stopped within the hour.

### Route Table

| Method | Path | Flags |
|--------|------|-------|
| GET | `/health` | — |
| GET | `/newsletters_v2` | 🗄️ DB read |
| POST | `/get_articles_by_newsletter_id` | 🗄️ DB read, generates DH keypairs, stores keys in DB |
| POST | `/process_newsletter` | 🗄️ DB write, 💰 calls news-orchestrator (triggers OpenAI), 🌐 fetches external URLs, 🔑 reads `decrypted_username`/`decrypted_password` from DB for authenticated scraping |
| POST | `/key_exchange` | 🔑 **Accepts client DH public key, computes shared secret, stores AES key in DB** |
| POST | `/submit_credentials` | 🔑⚠️ **CRITICAL: Accepts newspaper passwords, decrypts them, stores as `decrypted_username`/`decrypted_password` (PLAINTEXT) in `user_subscription_credentials`** |
| GET | `/get_user_consolidation_status/<device_id>` | 🗄️ DB read |
| POST | `/decrypt_credentials` | 🔑⚠️ **Returns decrypted credentials (username/password) in HTTP response body** |

### Specific Dangers

1. **`/submit_credentials`** — Stores third-party newspaper passwords in plaintext columns (`decrypted_username`, `decrypted_password`). No encryption at rest. This is the exact issue D40 describes.
2. **`/decrypt_credentials`** — Returns stored plaintext passwords in a JSON response. Combined with `/submit_credentials`, this is a full credential exfiltration surface.
3. **`/key_exchange`** — The DH exchange is correctly implemented but moot because the decrypted result is stored unencrypted.
4. **`/process_newsletter`** — Costs money: calls the news-orchestrator which triggers OpenAI. Also reads stored credentials to authenticate with paywalled sites (Boston Globe, NY Times).

### Restorable Without Build?

**Yes.** The file exists in `audioura-tour-generator:latest` (confirmed by LOCAL-147 submission — it was started with `docker run` from that image). All imports (`apple_podcasts_processor`, `spotify_processor`, `subscription_detector`, `dh_service_simple`, `user_consolidation_service`, `credential_verification_service`, `advertising_url_filter`) are present in the same image.

### Mobile App Calls It?

**Yes.** `endpoints.dart:29` maps `Service.newsletter: 5017`. The app calls:
- `/newsletters_v2` (home_screen.dart)
- `/process_newsletter` (home_screen.dart, tour_generator_screen.dart)
- `/submit_credentials` (subscription_service.dart)
- `/key_exchange` (subscription_service.dart)

---

## 2. tour-editing (port 5020) — `tour_editing_simple.py`

**Risk verdict: Safe to restore (if needed) — no credentials, no DB, no paid APIs.**

### Route Table

| Method | Path | Flags |
|--------|------|-------|
| GET | `/health` | — |
| GET | `/tour/<tour_id>/edit-info` | Reads filesystem (`tours/` directory) |
| GET | `/tours-near` | Reads filesystem |
| POST | `/tour/<tour_id>/update-stop` | ✏️ Writes to filesystem (`tours/` directory) |
| POST | `/tour/<tour_id>/create-custom` | ✏️ Writes to filesystem (copies tour directory) |

### Specific Dangers

None. This is a `http.server`-based (no Flask) prototype that reads/writes tour JSON and text files on the local filesystem. No database connection, no paid API calls, no credential handling, no email.

### Restorable Without Build?

**Yes.** The file exists in `audioura-tour-generator:latest` (confirmed in LOCAL-145: `docker run --entrypoint ls audioura-tour-generator:latest /app/tour_editing_simple.py` succeeded). Uses only Python stdlib (`http.server`, `json`, `pathlib`, `uuid`, `shutil`, `zipfile`).

### Mobile App Calls It?

**No.** `endpoints.dart` maps `Service.tourEditing: 5022` (the phase2 service). Port 5020 is not referenced anywhere in the Dart codebase. This service is superseded by `tour_editing_phase2.py`.

---

## 3. subscription_credentials_service (port 5019) — `subscription_credentials_service.py`

**Risk verdict: DO NOT RESTORE — stores encrypted credentials but has no encryption-at-rest implementation, and is superseded by the same routes in newsletter-processor.**

### Route Table

| Method | Path | Flags |
|--------|------|-------|
| GET | `/health` | — |
| POST | `/submit_credentials` | 🔑⚠️ **Stores encrypted_username/encrypted_password in DB. No decryption-at-rest — stores ciphertext directly.** 🗄️ DB write |
| POST | `/get_stored_credentials` | 🔑 Returns credential metadata (domain, article_id — not the encrypted values) |

### Specific Dangers

1. **`/submit_credentials`** — While this version stores the *encrypted* form (unlike the newsletter-processor which decrypts first), it still writes credentials to `user_subscription_credentials` without any server-side encryption envelope. The "encryption" is client-side DH-derived AES — once the AES key is compromised (stored in `dh_aes_keys` table), all credentials are recoverable.
2. This is an **orphan** — no compose entry in either file, no Dockerfile. It was apparently a Stage 1 prototype before the newsletter-processor absorbed its functionality.

### Restorable Without Build?

**Unknown — likely yes** if the image contains it, but this was never deployed. No Dockerfile references it. Would need to verify the file exists in `audioura-tour-generator:latest`.

### Mobile App Calls It?

**No.** The app calls `/submit_credentials` on `Service.newsletter` (port 5017), not port 5019.

---

## 4. coordinates (port 5006) — `coordinates_service.py` [SOURCE FILE MISSING]

**Risk verdict: Cannot restore — source file does not exist.**

### Route Table

N/A — `coordinates_service.py` does not exist in the repository. The old `docker-compose.yml` references it, but it has been superseded by `coordinates_fromAI/app.py` (which runs as `coordinates-fromai` in master on the same external port 5006).

### Restorable Without Build?

**Unknown.** The source file is gone. The old compose points to a build context of `.` with command `python coordinates_service.py`. If the file doesn't exist in the image either, the container would crash on start.

### Mobile App Calls It?

**No.** The app does not directly call coordinates — it goes through the orchestrator.

---

## 5. customAudio / version_api (port 5023) — `version_api.py`

**Risk verdict: Restore with routes gated — the app actively calls this port, but the backing file (`version_api.py`) does NOT implement the custom audio API the app expects.**

### Route Table (as implemented in `version_api.py`)

| Method | Path | Flags |
|--------|------|-------|
| GET | `/health` | — |
| GET | `/tour/<int:tour_id>/version` | No DB, returns generated timestamp |
| POST | `/tours/check-versions` | No DB, returns generated timestamps |

### What the App Expects (from `custom_audio_service.dart`)

| Method | Path | Actually Implemented? |
|--------|------|-----------------------|
| POST | `/tour/<id>/stop/<n>/custom-audio` | ❌ No |
| DELETE | `/tour/<id>/stop/<n>/custom-audio` | ❌ No |
| GET | `/tour/<id>/stop/<n>/audio-versions` | ❌ No |
| GET | `/tour/<id>/audio-metadata` | ❌ No |

### Specific Dangers

The file `version_api.py` is harmless (no DB, no credentials, no paid APIs). However:
1. It does NOT serve the custom audio API the app needs.
2. No compose entry exists for port 5023 in either compose file.
3. There is no actual custom audio service implementation in the repo.

### Restorable Without Build?

**Possibly** — `version_api.py` exists in the repo and uses only Flask (likely in the image). But starting it would not give the app what it needs.

### Mobile App Calls It?

**Yes.** `endpoints.dart:31` maps `Service.customAudio: 5023`. `custom_audio_service.dart` makes POST/DELETE/GET calls to this port. All calls currently fail (connection refused).

---

## 6. diffie_hellman_service (no port / no compose) — `diffie_hellman_service.py`

**Risk verdict: DO NOT RESTORE as a service — it's a library module, not a Flask app. But it implements the DH crypto that enables plaintext credential storage.**

### Route Table

N/A — this file has no Flask app, no HTTP routes. It's a Python module with functions (`generate_server_keypair`, `calculate_shared_secret`, `decrypt_dh_credential`, etc.) and a `__main__` block that creates DB tables and runs a self-test.

### Why It's Listed

It's part of the credential pipeline (UNREACHED_CODE_AUDIT Rank 2). It's imported by `newsletter_processor_service.py` (as `dh_service_simple.py`, a variant). Running its `__main__` would create `dh_server_keys` and `dh_aes_keys` tables — but those likely already exist from the D40 incident.

### Restorable Without Build?

N/A — not a service.

### Mobile App Calls It?

No — indirectly via the newsletter-processor's `/key_exchange` route.

---

## Summary Table

| # | Service | Port | Compose File | Risk | Credentials | DB Write | Costs Money | App Calls It | Restorable |
|---|---------|------|--------------|------|-------------|----------|-------------|--------------|------------|
| 1 | newsletter-processor | 5017 | old only | ⛔ DO NOT RESTORE | ✅ Plaintext | ✅ | ✅ OpenAI | ✅ | Yes (image) |
| 2 | tour-editing | 5020 | old only | ✅ Safe | ❌ | ❌ | ❌ | ❌ (superseded) | Yes (image) |
| 3 | subscription_credentials_service | 5019 | nowhere | ⛔ DO NOT RESTORE | ✅ Encrypted (weak) | ✅ | ❌ | ❌ | Unknown |
| 4 | coordinates | 5006 | old only | — Source missing | — | — | — | ❌ | No |
| 5 | customAudio (version_api) | 5023 | nowhere | ⚠️ Wrong implementation | ❌ | ❌ | ❌ | ✅ | Possibly |
| 6 | diffie_hellman_service | — | nowhere | ⛔ Enables plaintext creds | N/A (library) | ✅ (creates tables) | ❌ | ❌ | N/A |

---

## What `docker-compose up` (old file) Would Actually Start

If someone ran `docker-compose up` using the old `docker-compose.yml`:

| Service | Port | Status vs Master | Danger |
|---------|------|------------------|--------|
| postgres-2 | 5432 | Port conflict (master uses 5433) | Would fail or shadow the running DB |
| tour-processor | 5001 | Duplicate of running service | Port conflict |
| tour-orchestrator | 5002 | Duplicate of running service | Port conflict |
| map-delivery | 5005 | Duplicate of running service | Port conflict |
| coordinates | 5006 | **Source file missing** — container crash | Port conflict with coordinates-fromai |
| treats | 5007 | Duplicate of running service | Port conflict |
| news-generator | 5010 | Duplicate of running service | Port conflict |
| news-processor | 5011 | Duplicate of running service | Port conflict |
| news-orchestrator | 5012 | Duplicate of running service | Port conflict |
| **newsletter-processor** | **5017** | **⛔ NOT in master, dormant** | **Plaintext credentials endpoint goes live** |
| polly-tts | 5018 | Duplicate of running service | Port conflict |
| **tour-editing** | **5020** | **NOT in master, dormant** | Safe (filesystem only) |
| tour-generation-modernized | 5021 | Duplicate of running service | Port conflict |
| tour-editing-phase2 | 5022 | Already running (from master) | Port conflict |
| translation-service | 5030 | Duplicate of running service | Port conflict |

**Net new exposure from `docker-compose up` on the old file: newsletter-processor (dangerous) and tour-editing (safe).**

---

## Limitations

1. **Image contents not verified for all services.** Only newsletter-processor and tour-editing-simple were confirmed present in `audioura-tour-generator:latest` (per LOCAL-145 and LOCAL-147 submissions). `subscription_credentials_service.py` presence in the image is unverified — confirming it would require `docker run --entrypoint ls` which is a container start.

2. **Blueprint/import-time registration.** The newsletter-processor imports `user_consolidation_service` and `credential_verification_service` which were verified (by reading source) to be plain Python classes, not Flask Blueprint registrations. However, if those modules were changed to register routes, this audit would not catch it without re-reading them.

3. **Dynamic route registration.** No `add_url_rule`, `register_blueprint`, or `importlib` patterns were found in the dormant service files. If routes are registered dynamically by imported modules at Flask app creation time, this audit would miss them.

4. **The "custom audio" gap.** The app expects a service on port 5023 that implements custom audio upload/versioning. No such implementation exists in the repo. This is a feature gap, not a dormant service — but it explains why `Service.customAudio` calls always fail.

5. **Cloud Run deployments.** `tour_worker_service.py` and other Cloud Run targets were not audited — they're not Docker-compose-managed and outside scope.
