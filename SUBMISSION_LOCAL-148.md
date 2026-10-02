##### READY FOR REVIEW

**Task:** LOCAL-148  
**Branch:** `kiro/local148-credential-pipeline-assessment`  
**Commit:** `f5b4356`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02

---

## Deliverable

`CREDENTIAL_PIPELINE_ASSESSMENT.md` — 344 lines at repo root.

## Per-file changes

| File | Action | Lines |
|------|--------|-------|
| `CREDENTIAL_PIPELINE_ASSESSMENT.md` | Created | +344 |

## Verbatim Evidence

### Import results (D39 — actually run, not inferred from reading)

```
$ python3 -c "import subscription_credentials_service"
(no output — imports cleanly)

$ python3 -c "import diffie_hellman_service"
ModuleNotFoundError: No module named 'Crypto'

$ python3 -c "import subscription_article_processor"
ModuleNotFoundError: No module named 'selenium'
```

### Database queries (read-only)

```sql
-- Table exists
SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_subscription_credentials');
-- true

-- Zero rows
SELECT COUNT(*) FROM user_subscription_credentials;
-- 0

-- Columns (no encrypted columns present)
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'user_subscription_credentials';
-- id: integer
-- device_id: character varying
-- article_id: character varying
-- domain: character varying
-- created_at: timestamp without time zone
-- decrypted_username: character varying  ← PLAINTEXT
-- decrypted_password: character varying  ← PLAINTEXT
-- consolidated_user_id: character varying
-- verified_at: timestamp without time zone

-- Supporting tables all exist, all empty
-- dh_server_keys: 0 rows
-- dh_aes_keys: 0 rows
-- device_encryption_keys: 0 rows
```

### Client reachability (grep evidence)

```
audio_tour_app/lib/screens/home_screen.dart:2595:
    builder: (context) => SubscriptionCredentialDialog(

audio_tour_app/lib/screens/home_screen.dart:3415:
    builder: (context) => SubscriptionCredentialDialog(
```

Both call sites are in the active `home_screen.dart` — the app's main screen.
The dialog is triggered when articles with `subscription_required == true` are
displayed.

### Dockerfile verification

```
$ cat Dockerfile.newsletter-processor
FROM python:3.9-slim
WORKDIR /app
RUN pip install flask psycopg2-binary requests beautifulsoup4
COPY newsletter_processor_service.py .
EXPOSE 5017
CMD ["python", "newsletter_processor_service.py"]
```

Missing: `dh_service_simple.py`, `credential_verification_service.py`,
`user_consolidation_service.py`, `subscription_detector.py`. Container
would crash on startup.

### Docker status (newsletter-processor not running)

```
$ docker ps | grep -i "newsletter\|5017"
newsletter-link-extractor-1  0.0.0.0:5014->5000/tcp  Up 4 days
```

No newsletter-processor container exists. Port 5017 is unoccupied.

### Compose file search

```
$ grep -r "newsletter-processor\|5017" docker-compose*.yml
docker-compose.yml:78:  newsletter-processor:
docker-compose.yml:80:    container_name: newsletter-processor-1
docker-compose.yml:82:      - "5017:5017"
```

Present in `docker-compose.yml` (dev/legacy). NOT in `docker-compose-master.yml`.

## Acceptance Criteria Checklist

- [x] Import result for each of the three modules, actually run
- [x] DB findings with queries used, read-only
- [x] Clear answer: client half is LIVE (user-reachable from home_screen)
- [x] Sizing: deployment-only ~2-4h; with encryption fix ~1-2d; full Phase 2 ~1wk
- [x] Security observations: plaintext storage, debug credential logging,
      ephemeral keys stored permanently
- [x] $0.00 API spend — no credentials created, stored, or transmitted
- [x] `git status --short` clean

## Constraints Honored

- [x] No Docker builds
- [x] Read-only against database (SELECT only)
- [x] No services deployed
- [x] No app modifications
- [x] No real credentials written anywhere
- [x] No `audioura-*` containers touched
- [x] `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md` untouched

## Limitations

- Cannot verify cloud gateway routing (`api.audioura.com/newsletter/...`)
- Cannot build/run the Flutter app on device (Docker builder hung)
- Newsletter processor Dockerfile broken (ImportError) — not tested at
  container runtime level, assessed from file content
- `UNREACHED_CODE_AUDIT.md` referenced in task does not exist in this
  worktree (may be on another branch)
