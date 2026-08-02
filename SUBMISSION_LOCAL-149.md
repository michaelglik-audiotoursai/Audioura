##### READY FOR REVIEW

## LOCAL-149 — Dormant Service Inventory

### Commit
See `git log --oneline storied..HEAD` for hash after push.

### Summary
Inventoried all services that would activate if either compose file were used to
start dormant containers. Enumerated every HTTP route from source code, flagged
credential-accepting routes, DB-writing routes, and cost-incurring routes.

### What was done

1. **Compared compose files**: Identified services in `docker-compose.yml` (old)
   absent from `docker-compose-master.yml` (active), and services referenced by
   the mobile app with no running container.

2. **Enumerated routes** by grep for `@app.route`, `add_url_rule`, and HTTP handler
   methods in each dormant service source file.

3. **Checked app references** in `audio_tour_app/lib/config/endpoints.dart` and
   service files to determine which dormant services the app actively calls.

4. **Verified restorability** by cross-referencing LOCAL-145 and LOCAL-147 submissions
   which confirmed image contents via `docker run --entrypoint ls`.

5. **Captured docker ps** before and after — identical (no containers started).

### Key Findings

| Service | Port | Verdict | Critical Route |
|---------|------|---------|----------------|
| newsletter-processor | 5017 | ⛔ DO NOT RESTORE | `/submit_credentials` stores passwords in plaintext |
| subscription_credentials_service | 5019 | ⛔ DO NOT RESTORE | `/submit_credentials` — orphan Stage 1 prototype |
| tour-editing (simple) | 5020 | ✅ Safe to restore | Filesystem only, no DB/creds/APIs |
| customAudio / version_api | 5023 | ⚠️ Wrong implementation | App expects custom audio API, file serves version API |
| coordinates | 5006 | — Cannot restore | Source file deleted, superseded by coordinates-fromai |

### Evidence

#### docker ps — before (start of task):
```
audioura-coordinates-fromai-1
audioura-map-delivery-1
audioura-polly-tts-1-1
audioura-tour-generation-modernized-1-1
audioura-tour-generator-1
audioura-tour-id-resolution-1
audioura-tour-orchestrator-1
audioura-tour-processor-1
audioura-tour-update-1
audioura-translation-service-1
audioura-treats-1
audioura-user-api-2-1
audioura-voice-control-1
background-article-processor-1
development-postgres-2-1
news-generator-1
news-orchestrator-1
news-processor-1
newsletter-link-extractor-1
simple-news-search-1
tour-editing-phase2-1
```

#### docker ps — after (end of task):
```
audioura-coordinates-fromai-1
audioura-map-delivery-1
audioura-polly-tts-1-1
audioura-tour-generation-modernized-1-1
audioura-tour-generator-1
audioura-tour-id-resolution-1
audioura-tour-orchestrator-1
audioura-tour-processor-1
audioura-tour-update-1
audioura-translation-service-1
audioura-treats-1
audioura-user-api-2-1
audioura-voice-control-1
background-article-processor-1
development-postgres-2-1
news-generator-1
news-orchestrator-1
news-processor-1
newsletter-link-extractor-1
simple-news-search-1
tour-editing-phase2-1
```

**Identical — no containers started, stopped, or created.**

#### Route enumeration evidence — newsletter_processor_service.py:
```
grep -n "@app.route" newsletter_processor_service.py
672:@app.route('/health', methods=['GET'])
676:@app.route('/newsletters_v2', methods=['GET'])
770:@app.route('/get_articles_by_newsletter_id', methods=['POST'])
906:@app.route('/process_newsletter', methods=['POST'])
2370:@app.route('/key_exchange', methods=['POST'])
2425:@app.route('/submit_credentials', methods=['POST'])
2622:@app.route('/get_user_consolidation_status/<device_id>', methods=['GET'])
2646:@app.route('/decrypt_credentials', methods=['POST'])
```

#### Route enumeration evidence — subscription_credentials_service.py:
```
grep -n "@app.route" subscription_credentials_service.py
27:@app.route('/health', methods=['GET'])
31:@app.route('/submit_credentials', methods=['POST'])
138:@app.route('/get_stored_credentials', methods=['POST'])
```

#### Route enumeration evidence — tour_editing_simple.py (http.server, no Flask):
```
Routes extracted from do_GET/do_POST handler dispatch:
GET  /health
GET  /tour/<tour_id>/edit-info
GET  /tours-near
POST /tour/<tour_id>/update-stop
POST /tour/<tour_id>/create-custom
```

#### App endpoint references:
```
grep -n "Service\." audio_tour_app/lib/config/endpoints.dart
Service.newsletter: 5017    → app calls /newsletters_v2, /process_newsletter, /submit_credentials, /key_exchange
Service.customAudio: 5023   → app calls /tour/<id>/stop/<n>/custom-audio, /audio-versions, /audio-metadata
Service.tourEditing: 5022   → ALREADY RUNNING (phase2, not dormant)
```

#### Credential storage — plaintext columns confirmed in source:
```python
# newsletter_processor_service.py:2561
cursor.execute("""
    INSERT INTO user_subscription_credentials 
    (device_id, article_id, domain, decrypted_username, decrypted_password, verified_at)
    VALUES (%s, %s, %s, %s, %s, NOW())
    ...
""", (device_id, article_id, domain, decryption_result['username'], decryption_result['password']))
```

### Per-file changes

| File | Change |
|------|--------|
| `DORMANT_SERVICES.md` | New — full dormant service inventory |
| `SUBMISSION_LOCAL-149.md` | This file |

### Limitations

1. **Image contents not verified for all services.** Only confirmed for newsletter-processor
   and tour-editing-simple (via prior LOCAL-145/147 work). Verifying others would require
   `docker run --entrypoint ls` which starts a container.

2. **Dynamic route registration.** If imported modules register Flask routes at import time
   (via Blueprint or otherwise), those routes would not be caught by grep for `@app.route`.
   Verified that `user_consolidation_service` and `credential_verification_service` (imported
   by newsletter-processor) are plain classes, not Blueprint registrations.

3. **The custom audio service gap.** The app expects a service on port 5023 that implements
   custom audio upload/versioning. No such implementation exists. `version_api.py` occupies
   that port but serves a completely different API.

4. **`coordinates_service.py` cannot be audited** — file does not exist. If an old Docker
   image contains it, its routes are unknown from this analysis.

5. **No database queries were run.** The task specified read-only against the DB but
   route enumeration was done entirely from source code, not runtime introspection.
