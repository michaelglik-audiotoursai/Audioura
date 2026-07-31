##### READY FOR REVIEW

# SUBMISSION — LOCAL-53: Push `storied` to origin

**Agent:** Mac Mini Kiro  
**Date:** 2026-07-31  
**Branch:** `storied`  
**Cleared by:** PUSH_CLEARED.md confirmed present before any action taken.

---

## Part 1 — Fresh-Clone Self-Sufficiency

Cloned from local repo into `/tmp/freshclone-check`:
```
git clone /Users/micha/Audioura /tmp/freshclone-check --branch storied
```

### Check 1: Dockerfiles Exist

| Service | Dockerfile | Status |
|---------|-----------|--------|
| tour-id-resolution | Dockerfile.tour-id-resolution | PRESENT |
| tour-generator | Dockerfile.generator | PRESENT |
| tour-orchestrator | Dockerfile.orchestrator | PRESENT |
| tour-generation-modernized-1 | Dockerfile.modernized | PRESENT |
| polly-tts-1 | Dockerfile.polly-tts | PRESENT |
| translation-service | translation-service/Dockerfile | PRESENT |
| tour-processor | Dockerfile.tour-processor | PRESENT |
| postgres-2 | (image: postgres:15-alpine) | N/A |
| user-api-2 | user-tracking/Dockerfile | PRESENT |
| tour-update | tour-update-service/Dockerfile | PRESENT |
| coordinates-fromai | coordinates_fromAI/Dockerfile | PRESENT |
| map-delivery | map_delivery/Dockerfile | PRESENT |
| treats | Dockerfile.treats | PRESENT |
| voice-control | voice_control/Dockerfile | PRESENT |
| news-generator-1 | Dockerfile.news-generator | PRESENT |
| news-processor-1 | Dockerfile.news-processor | PRESENT |
| news-orchestrator-1 | Dockerfile.news-orchestrator | PRESENT |
| newsletter-link-extractor | Dockerfile.newsletter-link-extractor | PRESENT |
| background-article-processor | Dockerfile.background-article-processor | PRESENT |
| simple-news-search | Dockerfile.simple-news-search | PRESENT |

**Result: ALL PRESENT ✓**

### Check 2: COPY/ADD Sources Exist and Survive .dockerignore

#### Root-context builds (.dockerignore applies):

| Dockerfile | Source | Exists? | Survives .dockerignore? |
|-----------|--------|---------|------------------------|
| tour-id-resolution | requirements-tour-id-resolution.txt | ✓ | ✓ (!requirements*.txt) |
| tour-id-resolution | deeplink_resolution_endpoint.py | ✓ | ✓ |
| tour-id-resolution | storied_version_constants.py | ✓ | ✓ |
| tour-id-resolution | tour_id_resolution_service.py | ✓ | ✓ |
| tour-id-resolution | tour_sharing.py | ✓ | ✓ |
| generator | requirements_generator.txt | ✓ | ✓ (!requirements*.txt) |
| generator | *.py (332 files, excluded subset is test/util only) | ✓ | ✓ |
| generator | *.json (story_type_taxonomy.json, source_tier_rules.json) | ✓ | ✓ (exceptions in .dockerignore) |
| generator | templates/ | ✓ | ✓ (!templates/ !templates/**) |
| orchestrator | requirements_orchestrator.txt | ✓ | ✓ (!requirements*.txt) |
| orchestrator | tour_orchestrator_service.py | ✓ | ✓ |
| orchestrator | entitlements.py | ✓ | ✓ |
| modernized | requirements-modernized.txt | ✓ | ✓ (!requirements*.txt) |
| modernized | tour_generation_modernized.py | ✓ | ✓ |
| modernized | job_store.py | ✓ | ✓ |
| polly-tts | polly_tts_service.py | ✓ | ✓ |
| tour-processor | requirements-tour-processor.txt | ✓ | ✓ (!requirements*.txt) |
| tour-processor | tour_generation_service.py | ✓ | ✓ |
| tour-processor | text_to_index_fixed.py | ✓ | ✓ (!*_fixed.py) |
| tour-processor | break_text_to_pois_fixed.py | ✓ | ✓ (!*_fixed.py) |
| tour-processor | build_mp3_simple.py | ✓ | ✓ (!build_mp3_simple.py) |
| tour-processor | build_web_page_fixed.py | ✓ | ✓ (build_*.py excluded BUT !*_fixed.py re-includes) |
| tour-processor | single_file_app_builder.py | ✓ | ✓ |
| tour-processor | prepare_for_netlify.py | ✓ | ✓ |
| treats | treats_service.py | ✓ | ✓ |
| news-generator | requirements-news.txt | ✓ | ✓ (!requirements*.txt) |
| news-generator | news_generator_service.py | ✓ | ✓ |
| news-processor | requirements-news.txt | ✓ | ✓ |
| news-processor | news_processor_service.py | ✓ | ✓ |
| news-orchestrator | requirements-news.txt | ✓ | ✓ |
| news-orchestrator | news_orchestrator_service.py | ✓ | ✓ |
| newsletter-link-extractor | requirements-newsletter.txt | ✓ | ✓ |
| newsletter-link-extractor | newsletter_link_extractor_service.py | ✓ | ✓ |
| background-article-processor | requirements-newsletter.txt | ✓ | ✓ |
| background-article-processor | background_article_processor_service.py | ✓ | ✓ |
| simple-news-search | requirements-newsletter.txt | ✓ | ✓ |
| simple-news-search | simple_news_search_service.py | ✓ | ✓ |

#### Subdirectory builds (own context, no root .dockerignore):

| Directory | requirements.txt | Other sources | Status |
|-----------|-----------------|---------------|--------|
| translation-service/ | PRESENT | translation_service.py, blobstorage.py — PRESENT | ✓ |
| user-tracking/ | PRESENT | COPY . . (all files) | ✓ |
| tour-update-service/ | PRESENT | COPY . . (all files) | ✓ |
| coordinates_fromAI/ | PRESENT | app.py — PRESENT | ✓ |
| map_delivery/ | PRESENT | COPY . . (all files) | ✓ |
| voice_control/ | PRESENT | COPY . . (all files) | ✓ |

**Result: ALL SOURCES EXIST AND SURVIVE .dockerignore ✓**

### Check 3: requirements*.txt Files Present

| File | Status |
|------|--------|
| requirements-tour-id-resolution.txt | PRESENT |
| requirements_generator.txt | PRESENT |
| requirements_orchestrator.txt | PRESENT |
| requirements-modernized.txt | PRESENT |
| requirements-tour-processor.txt | PRESENT |
| requirements-news.txt | PRESENT |
| requirements-newsletter.txt | PRESENT |
| translation-service/requirements.txt | PRESENT |
| user-tracking/requirements.txt | PRESENT |
| tour-update-service/requirements.txt | PRESENT |
| coordinates_fromAI/requirements.txt | PRESENT |
| map_delivery/requirements.txt | PRESENT |
| voice_control/requirements.txt | PRESENT |

**Result: ALL PRESENT ✓**

### Check 4: docker compose config parses

```
$ cd /tmp/freshclone-check && touch .env && docker compose -f docker-compose-master.yml config -q
time="2026-07-31T12:42:29-04:00" level=warning msg="The \"OPENAI_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-07-31T12:42:29-04:00" level=warning msg="The \"OPENAI_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-07-31T12:42:29-04:00" level=warning msg="The \"SERP_API_KEY\" variable is not set. Defaulting to a blank string."
(exit code 0)
```

Note: Empty `.env` file needed because `polly-tts-1` and `translation-service` use `env_file: .env`. Without it, compose exits 1. This is documented in WINDOWS_SETUP.md.

**Result: PARSES SUCCESSFULLY ✓**

### Check 5: .env Absent / Manual Setup Required

`.env` is **ABSENT** from the clone (confirmed by `ls -la .env` → no such file).  
`.gitignore` line 22 excludes `.env`.

**Manual setup required on Windows:**
1. `.env` file — must be placed at repo root (travels by USB, never committed)
2. Docker network `development_default` — must be created manually
3. Docker Desktop for Windows — must be installed

**Result: .env ABSENT ✓ — DOCUMENTED ✓**

---

## Part 2 — The Push

### Before-count:
```
$ git rev-list --count origin/storied..storied
192
```

### Push (192 commits):
```
$ git push origin storied
To https://github.com/michaelglik-audiotoursai/Audioura.git
   fe7eee7..8d98006  storied -> storied
```

### After-count:
```
$ git rev-list --count origin/storied..storied
0
```

### origin/storied HEAD:
```
$ git log --oneline -1 origin/storied
8d98006 Merge branch 'kiro/local49-persist-tour-content' into storied

$ git log --oneline -1 storied
8d98006 Merge branch 'kiro/local49-persist-tour-content' into storied
```

**Result: PUSH VERIFIED ✓ — after-count = 0, origin matches local.**

### Follow-up push (WINDOWS_SETUP.md + CLAUDE.md port fix):
```
$ git push origin storied
To https://github.com/michaelglik-audiotoursai/Audioura.git
   8d98006..cce44aa  storied -> storied

$ git rev-list --count origin/storied..storied
0

$ git log --oneline -1 origin/storied
cce44aa Add WINDOWS_SETUP.md and fix stale Postgres port in CLAUDE.md
```

---

## Part 3 — Windows Handoff Document

`WINDOWS_SETUP.md` committed and pushed to `storied` at `cce44aa`.

Contents:
- Exact clone + checkout commands for `storied` branch
- `.env` via USB placement instructions
- Docker Desktop requirement
- Docker network creation (`development_default`)
- AirPlay/port-5000 conflict note
- amd64 vs arm64 note (build fresh, don't copy images)
- **Postgres host port 5433** (not 5432) — also fixed in `CLAUDE.md`
- Build and start commands (`docker compose -f docker-compose-master.yml up -d --build`)
- Health check commands for all services
- End-to-end tour generation curl command with expected output
- Troubleshooting table

`CLAUDE.md` port fix: line 136 changed `localhost:5432` → `localhost:5433`.

---

## Summary

| Criterion | Status |
|-----------|--------|
| Part 1 Check 1: Dockerfiles exist | ✓ ALL PRESENT |
| Part 1 Check 2: COPY sources exist + survive .dockerignore | ✓ ALL VERIFIED |
| Part 1 Check 3: requirements*.txt present | ✓ ALL 13 FILES |
| Part 1 Check 4: compose config parses | ✓ EXIT 0 |
| Part 1 Check 5: .env absent, manual setup documented | ✓ |
| Part 2: Push (before=192, after=0, HEADs match) | ✓ |
| Part 3: WINDOWS_SETUP.md committed and pushed | ✓ |
| CLAUDE.md port 5432→5433 fix | ✓ |
| No force-push, no history rewrite | ✓ |
