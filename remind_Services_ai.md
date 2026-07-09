# Services Kiro Context Reminder
## Who you are
🔧 **SERVICES KIRO** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES KIRO -"

**UPDATED**: 2026-07-02 (STORIED BRANCH ACTIVE — local Docker runs `STORIED_MODE=true`. GCloud production unchanged at Beta `beta-2.1.1+18`.)

1. You are **Services Kiro** responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval.
2. You maintain this file and update it after significant changes.
3. Task management via ClickUp (Storied space, list 🟦 Services — Kiro).

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES KIRO -"
- **GIT BRANCH**: `storied` (off `main` = `beta-2.1.1+18`). **Never touch `main`.**
- **VERSION**: `2.2.0+1` (distinct from Beta's 2.1.x)
- **LAST GIT STATE**: I-CON module + Generic Grounding Phase 1 complete (`3cc9132`). All pushed to `origin/storied`.
- **NEXT ACTION ON RECOVERY**: Read `remind_Services_ai.md`. Check branch is `storied`. Check ClickUp for LEAD responses on Generic Grounding self-assessment (wdvrdawcyx) and I-CON calibration report (wdvrdawexa). Container should be running — if not: `docker-compose -f docker-compose-master.yml build tour-generator && docker-compose -f docker-compose-master.yml up -d tour-generator`.
- **WORKFLOW**: Blanket approval for all service changes. One task = one commit = one review.

---

## 🏗️ STORIED RELEASE — CURRENT STATE (Jul 5, 2026)

### Two Environments
| Environment | Branch | URL | Mode | Purpose |
|---|---|---|---|---|
| **GCloud (production)** | `main` (`beta-2.1.1+18`) | `https://api.audioura.com` | Beta | Google/Apple closed testing — DO NOT TOUCH |
| **Local Docker** | `storied` | `http://localhost:5000` | `STORIED_MODE=true` | Storied development + testing |

### Container Status
- `development-tour-generator-1` — **RUNNING**, `STORIED_MODE=true`, port 5000
- Container built from `docker-compose -f docker-compose-master.yml build tour-generator` (reproducible, no docker cp needed)
- `.dockerignore` fixed with exceptions for `requirements_generator.txt`, `story_type_taxonomy.json`, `templates/`
- OpenAI API key present; Wikipedia accessible from container (200)

### Active Work: Generic Grounding Phase 1 (wdvrdawcyx)
**ClickUp task:** `wdvrdawcyx` — 🌍 Generic Grounding (urgent, Storied flagship)
**Latest commit:** `fde1ecb` on `storied`
**Protocol:** CIL — approach approved with 7 amendments, coding in progress

**What's done (Phase 1 Step 0+1):**
- venue_resolver.py: Wikidata entity resolution ✅
  - Multi-strategy search + P31 type filter + geo-disambiguation (haversine) ✅
  - P856/P625/P17/P571 extraction ✅
  - P138/P921/P547 artist-link union + name-inference fallback ✅
  - SPARQL works query (P195/P276) → canonical titles ✅
  - build_dynamic_aliases() with W4 numeral invariants ✅
  - User-Agent + retry-then-degrade ✅
- _verify_works_v2: wired to venue_resolver (canonical titles = union of SPARQL + site + wiki) ✅
- story_miner.py: generic language parameter, localized keywords, Chagall URLs removed ✅
- Chagall .replace() band-aid deleted (amendment #7) ✅
- Acceptance: Matisse 7/8, Chagall 8/10 non-reg, Uffizi 175 SPARQL, Fruitlands resolved ✅

**What's remaining:**
- Delete _KNOWN_WORKS_BY_VENUE after proving SPARQL+site union is sufficient alone
- Full E2E generation test (Matisse and Uffizi)
- Extend test_w4_matcher.py against mocked SPARQL-built aliases
- Phase 2: Degradation ladder + Postgres cache

**Also in progress:** I-CON (wdvrdawexa) — approach posted, awaiting LEAD refinement

### Task Progress
- **~90 of 95 S-tasks** complete (code on `storied` branch)
- **5 deferred**: S79 (blocked by CIL), S80, S94, S95, POC v2
- **CIL cycle 3 of max 5** in progress on the museum quality overhaul

### Storied Pipeline Features (all active when STORIED_MODE=true)
1. **Narrative Spine** — gpt-4o generates arc/structure per tour (spine_generator.py)
2. **Fact Sheets** — RAG-grounded fact injection per stop (fact_extractor.py + rag_retriever.py)
3. **Story Types** — 6-type taxonomy, no consecutive repeats (story_type_assigner.py)
4. **Persona Tone** — 4 personas bias story selection + inject tone (onboarding_preference.py)
5. **De-repetition** — cross-stop detection + rewrite (derepetition_guard.py)
6. **Tour Hook** — Introduction paragraph before Stop 1 (tour_hook_generator.py)
7. **Improved Directions** — no fabricated distances (directions_generator.py)
8. **Tour Sharing** — 8-char share IDs + public GET (tour_sharing.py + sharing_endpoints.py)
9. **Referrals** — 6-char codes + redemption tracking (referral_engine.py + referral_endpoints.py)
10. **Attestation** — Play Integrity + App Attest log-only (attestation_verifier.py)
11. **Cost Ceiling** — $0.15 monitor, logs never aborts (cost_ceiling_monitor.py)
12. **Tour Cache** — exact-match Postgres cache (tour_cache_layer1.py)

### Key Files Added on Storied Branch
| File | Purpose |
|------|---------|
| `generate_tour_text.py` | Modified: +persona, +spine, +facts, +story_types, +hook, +directions, +cache |
| `generate_tour_text_service.py` | Modified: +persona lookup via user_id |
| `tour_orchestrator_service.py` | Modified: +persona wiring, +auto-share, +storied_mode insert |
| `api-gateway/main.py` | Modified: +ATTESTATION_MODE wiring, +version in /health |
| `spine_generator.py` | NEW: narrative spine generation |
| `fact_extractor.py` | NEW: RAG fact sheets |
| `story_type_assigner.py` | NEW: taxonomy assignment |
| `onboarding_preference.py` | NEW: 4 personas + weights |
| `persona_preference_store.py` | NEW: Postgres persona persistence |
| `derepetition_guard.py` | NEW: cross-stop repetition detection + rewrite |
| `directions_generator.py` | NEW: non-fabricated directions |
| `tour_hook_generator.py` | NEW: tour introduction from spine |
| `tour_sharing.py` + `sharing_endpoints.py` | NEW: share links |
| `referral_engine.py` + `referral_endpoints.py` | NEW: referral codes |
| `attestation_verifier.py` | NEW: log-only attestation |
| `storied_db_migration.sql` | NEW: all 5 new tables + audio_tours ALTER |

### Testing Storied Locally
Point the Audioura app at `http://<your-LAN-IP>:5000` and generate a tour. You should see:
- Introduction paragraph before Stop 1
- Varied narrative styles per stop (art, anecdote, history, etc.)
- No "vibrant colors and dreamlike imagery" clichés
- Persona tone if user_id has a stored preference

---

---

## ⚠️ CRITICAL FILE SAFETY RULE (learned Session 10)
The IDE file tool can show "intended" content while actual bytes on disk are truncated.
**NEVER trust local file content without verifying against the container.**
- Before deploying: `docker exec <container> wc -l /app/<file>.py`
- After any edit: `docker exec <container> python3 -m py_compile /app/<file>.py && echo OK`
- If local file truncated: `docker cp <container>:/app/<file>.py <local_path>` to recover
- **Containers are the source of truth for deployed code**

---

## 🔄 SESSION RECOVERY INSTRUCTIONS

After chat compaction, read this file top to bottom. Then:
1. The **NEXT ACTION ON RECOVERY** line above tells you exactly what to do first.
2. Current branch is `services-migration`. Last commit: `92b34a4`.
3. All containers should be running — verify with `docker ps` if unsure.
4. `tour_editing_phase2.py` is clean and deployed at v1.2.6.234. Smoke tests passed 6/6.
5. Run `call smoke_test_editing_v1264.bat` to re-verify if needed.
6. `advertising_url_filter.py` ISSUE-AD-FILTER fix is committed `1a7b4dc` and deployed.
7. `newsletter_pattern_detector.py` ISSUE-BLOG-PATTERN fix is committed `92b34a4` and deployed.
8. Branch history: `Newsletters` merged to `main` (v1.2.9+65), `services-migration` branched from there.

---

## ✅ COMPLETED WORK — v1.2.6.234 (commit fbfc8d2)

### What was implemented (from `claude_workplan_tour_editing.md` + `claude_spec_language_aware_editing.md`)

All 8 tasks complete. Schema migrations already done. Code deployed and committed.

#### Schema applied to DB (do NOT re-run):
```sql
ALTER TABLE audio_tours ADD COLUMN derived_from_tour_id integer REFERENCES audio_tours(id);
CREATE UNIQUE INDEX uq_audio_tours_original_name ON audio_tours (LOWER(tour_name)) WHERE original_tour_id IS NULL;
-- Duplicate originals cleaned up (3 pairs deleted, kept newer IDs: 287, 297, 301)
```

#### Changes deployed in v1.2.6.234:
1. `boto3` added to `requirements.txt`; AWS credentials added to `docker-compose.yml` for `tour-editing-phase2`
2. `VOICE_MAP` constant added (mirrors `translation_service.py`)
3. `comprehend_client` + `_detect_text_language()` — uses AWS Comprehend, fails open (returns None on error)
4. `_apply_custom_audio_file()` helper — raises JSON exception on failure, never falls back to TTS (R-C1)
5. `generate_audio_for_stop` — added `content_language='en'` param; fixed `voice` → `voice_id` (polly-tts bug fix)
6. `create_complete_tour_with_preservation` — added `content_language` param; replaced TTS fallback blocks with `_apply_custom_audio_file`
7. `bulk_save_stops` — reads `content_language` from request; language validation loop before tour creation → 400 `LANGUAGE_MISMATCH`
8. `promote_custom_tour` — reads `content_language` + `derived_from_tour_id`; whitespace-normalizes name; `request_string = "[custom edit] {name}"`; catches `pg_errors.UniqueViolation` → 409

#### Smoke test script:
`smoke_test_editing_v1264.bat` — 6 tests: health, bulk-save regression, language mismatch, promote new, promote duplicate, promote validation. All 6 passed.

---

## 🏗️ TOUR PIPELINE ARCHITECTURE

```
CLOUD MODE (GENERATION_MODE=cloud_tasks):
  Mobile App → api.audioura.com (Cloudflare + LB)
    → api-gateway (API key check)
      → tour-orchestrator (validate + quota + enqueue Cloud Task)
        → Cloud Tasks queue 'tour-generation'
          → tour-worker (full generation synchronously within request)
            → tour-generator (OpenAI text)
            → tour-modernized (Polly TTS → ZIP)
          → Cloud SQL (store tour, update job_status)
    → tour-orchestrator /status/<job_id> (reads job_status from Cloud SQL)
    → map-delivery /download-tour/<id> (serves from DB/R2)

LOCAL DOCKER MODE (GENERATION_MODE=thread, default):
  Mobile App
    → POST 5002/generate-complete-tour
    → 5000/generate  (generate_tour_text.py — OpenAI, produces Stop N: text)
    → 5021/process   (tour-generation-modernized-1 — MP3 via Polly → ZIP)
    → Store ZIP in PostgreSQL audio_tours table
    → Return final_tour_id (integer DB row ID)
    → POST 5030/translate-with-audio (for each language)
    → Store translated ZIP in audio_tours (original_tour_id = EN id)
```

---

## 🐳 DOCKER SERVICES

```
development-tour-generator-1:5000     # generate_tour_text.py
development-tour-orchestrator-1:5002  # tour_orchestrator_service.py
tour-generation-modernized-1:5021     # tour_generation_modernized.py
translation-service-1:5030            # translation_service.py
development-tour-processor-1:5001     # Legacy MP3+ZIP
development-postgres-2-1:5432         # PostgreSQL
development-map-delivery-1:5005       # Map & tour download
development-coordinates-fromai-1:5006 # Location services
development-treats-1:5007             # Local treats/POIs
news-orchestrator-1:5012              # News workflow
news-generator-1:5010                 # News content
news-processor-1:5011                 # News audio
newsletter-processor-1:5017           # Newsletter crawling
polly-tts-1:5018                      # Amazon Polly TTS
tour-id-resolution-1:5025             # Tour ID resolution
tour-editing-1:5020                   # Tour editing service
tour-editing-phase2-1:5022            # Tour editing phase 2 ← ACTIVE WORK
```

**polly-tts field name**: reads `voice_id` (NOT `voice`) — confirmed from container source. Fixed in v1.2.6.234.

---

## 📁 KEY FILES

| File | Container | Commit | Notes |
|------|-----------|--------|-------|
| `tour_editing_phase2.py` | `tour-editing-phase2-1:5022` | `fbfc8d2` | v1.2.6.234 — language-aware editing complete. Clean, deployed, smoke-tested. |
| `tour_orchestrator_service.py` | `development-tour-orchestrator-1:5002` | — | Dual-mode: thread (local) / cloud_tasks (production). Graceful shutdown. DB-backed /status. |
| `tour_worker_service.py` | Cloud Run `tour-worker:5040` | — | Cloud Tasks target. Full generation pipeline synchronous. Scale 0→N. |
| `job_store.py` | used by modernized + worker | — | DatabaseJobStore for multi-instance job state |
| `smoke_test_editing_v1264.bat` | local only | — | 6 automated tests. Run with `call smoke_test_editing_v1264.bat`. All passed. |
| `generate_tour_text.py` | `development-tour-generator-1:5000` | `64d8d67` | Sessions 2–17 complete |
| `map_delivery/app.py` | `development-map-delivery-1:5005` | `d186033` | ISSUE-061 fix |
| `translation_service.py` | `translation-service-1:5030` | `7cbc486` | Uses `voice_id` field in Polly calls via generate_audio() |
| `tour_generation_modernized.py` | `tour-generation-modernized-1:5021` | `ed1acad` | A#55 map buttons + A#56 icons |
| `claude_spec_language_aware_editing.md` | local only | — | Full spec for current work (Parts A/B/C/D) |
| `claude_response_promote_endpoint_review.md` | local only | `61e883d` | Claude review of REQ-PROMOTE — all issues addressed |
| `.env.example` | local only | — | Template for AWS credentials env vars (no real secrets) — commit to git |
| `advertising_url_filter.py` | `newsletter-processor-1:5017` | `1a7b4dc` | ISSUE-AD-FILTER: `ref=`/`referrer=` removed; `parse_qs` key-based query matching; assertion-based tests. 16/16 pass. |
| `newsletter_pattern_detector.py` | `newsletter-processor-1:5017` | `fd10ad5` | ISSUE-BLOG-PATTERN: added `detect_blog_homepage_pattern()` for Ghost/WordPress/blog homepages. Fixes reloadnyc.com 1→12 articles. |
| `claude_review_advertising_filter_fix_2026_06_01.md` | local only | — | Claude review request for ISSUE-AD-FILTER fix |
| `claude_review_blog_homepage_pattern_2026_05_28.md` | local only | — | Claude review request for ISSUE-BLOG-PATTERN fix |
| `claude_review_cpu_throttling_graceful_shutdown_2026_06_07.md` | local only | — | Claude review: CPU throttling fix + graceful shutdown handler |
| `claude_review_secret_fixes_final_2026_06_07.md` | local only | — | Claude review: OpenAI + AWS secret key fixes |

---

## 🗄️ audio_tours DB SCHEMA (current — after all migrations)

```
id                   serial PK
tour_name            varchar(255) NOT NULL
request_string       text NOT NULL
audio_tour           bytea
number_requested     integer DEFAULT 0
lat / lng            double precision
created_at           timestamp DEFAULT CURRENT_TIMESTAMP
language             varchar(10) DEFAULT 'en'
original_tour_id     integer FK→self  (NULL = original; set = translation)
tour_content         text             (stop text for translation)
content_language     varchar(10) DEFAULT 'en'
stops_count          integer DEFAULT 0
creator_type         varchar(50) DEFAULT 'Official'  ('Official'|'Custom')
description          text
derived_from_tour_id integer FK→self  (NULL = not edited; set = edited copy of X)

Indexes:
  uq_audio_tours_original_name UNIQUE (LOWER(tour_name)) WHERE original_tour_id IS NULL
  (+ standard btree indexes on language, lat/lng, original_tour_id, request_string, tour_name)
```

**Lineage semantics:**
- `original_tour_id = NULL` + `derived_from_tour_id = NULL` → Official original
- `original_tour_id = NULL` + `derived_from_tour_id = X` → Custom/edited tour (promoted)
- `original_tour_id = Y` + `derived_from_tour_id = NULL` → Translation of Y
- `original_tour_id = Y` + `derived_from_tour_id = X` → Translation of edited tour Y (derived from X)

---

## 🔧 REQ-PROMOTE + REQ-EDIT-LANG + REQ-EDIT-LINEAGE DESIGN DECISIONS

**Naming convention (B.4):** Mobile appends `(Edited)` to tour name. If name exists → 409 → mobile retries with `(Edited 2)`, etc. Services enforce uniqueness via DB constraint, never auto-name.

**Custom tours on map (§6.7):** CONFIRMED PUBLIC — all promoted custom tours appear as map markers. `tours-near` already returns `original_tour_id IS NULL` rows which includes Custom. No filter change needed.

**"Edited" badge:** In tour list only (not map markers). Mobile reads `creator_type='Custom'` or non-null `derived_from_tour_id` to show badge.

**Translation of edited tours:** Works identically to official tours — `original_tour_id IS NULL` so translation service treats it as any original.

**Language sync rule:** When user edits text → services regenerate audio in tour's language (Polly voice from VOICE_MAP). When user uploads MP3 → text must be in tour's language (Comprehend validates). Text and audio always kept in sync per stop.

**tour_content in promote:** Built server-side from `audio_*.txt` files — NOT trusted from mobile.

**base64 ZIP eliminated:** promote reads ZIP directly from container FS. Mobile sends only `custom_name`, `lat`, `lng`, `content_language`, `derived_from_tour_id`. No multi-MB upload.

---

## ⚠️ KNOWN ISSUES

- **Cloud Run CPU throttling (RESOLVED)**: Tour generation daemon thread was starved after HTTP response returned. Fixed with `--no-cpu-throttling --min-instances=1` on orchestrator and `--no-cpu-throttling` on modernized. Graceful shutdown handler added for safe redeployment.
- **Double map button (ISSUE-059)**: ✅ Resolved — `_buildMapButtonInjectionScript` already gone from `tour_player_screen.dart`.
- **Museum directions exit-to-street (ISSUE-060)**: Backlog. PHASE 3B not museum-aware. Fix deferred.
- **In-tour map white screen (ISSUE-MAP-WS)**: Mobile-side fix only. `_fitBounds()` in `tour_map_screen.dart` needs single-point guard. See `claude_response_needham_map_whitescreen.md`.
- **A#56 tour-type icons**: Deployed `d5da0f4`. Pending mobile test with newly generated tours.
- **polly-tts `voice` vs `voice_id`**: ✅ Fixed in v1.2.6.234 — editing service now sends `voice_id`.
- **`development-tour-generator-1` and `development-tour-orchestrator-1`**: Show "unhealthy" in `docker ps` — health check config issue only, both work correctly.
- **ISSUE-AD-FILTER** (newsletter `ref=` false-positive): ✅ Fixed and committed `1a7b4dc` — switched to `parse_qs` key-based query parameter matching; eliminates entire class of substring false-positives (`?topic=offering`, `?q=promotion+news`, etc.). 16/16 assertion tests pass.
- **ISSUE-BLOG-PATTERN** (blog homepage only returns 1 article): ✅ Fixed — added `detect_blog_homepage_pattern()` to `newsletter_pattern_detector.py`. Detects same-domain article card listings (Ghost, WordPress, etc.). reloadnyc.com now returns 12 articles instead of 1. Deployed to container.

---

## 🎯 NEXT STEPS (in order)

0. **⚡ FIRST on recovery**: Verify branch is `services-migration`. Check GENERATION_MODE env var status.

1. **Deploy Cloud Tasks infrastructure** (before launch):
   - Create `tour-generation` Cloud Tasks queue
   - Deploy `tour-worker` Cloud Run service (--timeout=900, --concurrency=1, --min-instances=0)
   - Set `GENERATION_MODE=cloud_tasks` + `JOB_STORE_MODE=database` on orchestrator
   - Remove `--no-cpu-throttling --min-instances=1` from orchestrator
   - Test: generate tour via Cloud Tasks end-to-end

2. **Mobile testing (current cloud mode)**:
   - Generate tour on cloud mode — verify completes reliably
   - Download tour — verify full ZIP with audio
   - Translate tour — verify translation works end-to-end

3. **Cost optimization**:
   - Once Cloud Tasks verified, remove always-on flags from orchestrator (~$30/mo saved)
   - Worker scales to zero between tours

4. **Mobile testing (v1.2.6.234 — local features)**:
   - Edit a stop and verify audio plays correctly
   - Promote a tour and verify map marker + Edited badge appear
   - Test duplicate name conflict shows friendly error (409 → retry with "(Edited 2)")

5. **Mobile deliverable (Part D)**: Write requirements doc for Mobile Amazon-Q: when user uploads custom audio, mobile must (a) show sync warning, (b) require non-empty text, (c) require acknowledgement checkbox.

6. **Merge to main**: After all mobile tests pass and Cloud Tasks verified.

---

## 🏭 PRE-PRODUCTION BACKLOG

| Item | Priority | Status |
|------|----------|--------|
| Cloud Tasks queue + tour-worker deployment | HIGH | Code ready, needs deploy |
| Remove --no-cpu-throttling/--min-instances=1 from orchestrator | HIGH | After Cloud Tasks verified |
| ACTIVE_JOBS lock + TTL + restart recovery | ~~HIGH~~ RESOLVED | Cloud Tasks + DatabaseJobStore |
| MAX_TOTAL_STOPS cost guard | HIGH | Entitlements covers this (tour_max_poi) |
| Auth, rate limiting, CORS, debug=False, HTTPS | HIGH | Done (gateway API key + IAM + Cloudflare) |
| Structured logging + job_id correlation | MEDIUM | |
| Container naming cleanup | LOW | |
| Delete `_generate_translated_html()` dead code | LOW | |

---

## 📊 SESSIONS SUMMARY (abbreviated)

| Sessions | Key Work |
|----------|----------|
| 2–14 | generate_tour_text.py: coordinates, museum fix, PHASE 3C address guard, cluster detection, S15 venue_name→museum, S17 geographic scope |
| 15–16 | S15 Claude reviews applied; Needham museum test; ISSUE-MAP-WS diagnosed |
| 17 | S17 complete: PHASE 3D removed, geographic_scope+scope_precision, GEO-CHECK haversine |
| A#55/A#56 | Per-stop map buttons, tour-type icons 🚶🍴🏛️🗺️ |
| ISSUE-061 | map_delivery translations excluded from tours-near; is_translation+parent_tour_id added |
| REQ-PROMOTE | promote endpoint designed, smoke-tested, Claude-reviewed |
| v1.2.6.234 | Language-aware editing (Parts A/B/C) complete — VOICE_MAP, content_language TTS, Comprehend lang detection, _apply_custom_audio_file, promote lineage+UniqueViolation. Smoke tests 6/6 pass. Committed fbfc8d2. Awaiting mobile test. |
| 2026-06-01 | Git cleanup pass by Strategic Advisor. remind_Services_ai.md reconstructed. ISSUE-AD-FILTER: `advertising_url_filter.py` — `ref=`/`referrer=` removed; `parse_qs` key-based matching (Claude Q2); assertion tests (Claude Q4). Committed `1a7b4dc`. |
| 2026-05-28 | ISSUE-BLOG-PATTERN: `newsletter_pattern_detector.py` — added `detect_blog_homepage_pattern()` for blog/newsletter homepages (Ghost, WordPress). Fixes reloadnyc.com returning 1 article instead of 12. Deployed to container. |
| 2026-06-07 | CPU THROTTLING FIX: `--no-cpu-throttling --min-instances=1` on tour-orchestrator, `--no-cpu-throttling` on tour-modernized. Graceful shutdown handler added to orchestrator (`_graceful_shutdown`, SIGTERM handling, thread tracking). Secret fixes: OpenAI key (wrong value), AWS keys (\r\n suffix), /user route added to gateway. |


---

## 🆕 STORIED BRANCH — New Service Files

The following modules were added on the `storied` branch to implement the Storied v2.2.0 pipeline:

| File | Purpose |
|------|---------|
| `spine_generator.py` | Narrative spine generation (gpt-4o) |
| `fact_extractor.py` | RAG-grounded fact sheets (gpt-3.5-turbo) |
| `story_type_assigner.py` | 6-type taxonomy assignment |
| `derepetition_guard.py` | Cross-stop repetition detection + rewrite |
| `directions_generator.py` | Improved non-fabricated directions |
| `tour_hook_generator.py` | Tour introduction from spine hook |
| `onboarding_preference.py` | 4 personas + weights |
| `persona_preference_store.py` | Postgres persona persistence |
| `persona_endpoints.py` | POST/GET /user/persona |
| `tour_sharing.py` + `sharing_endpoints.py` | Share links + POST/GET |
| `referral_engine.py` + `referral_endpoints.py` | Referral codes |
| `attestation_verifier.py` | Play Integrity + App Attest (log-only) |
| `cost_ceiling_monitor.py` | $0.15 ceiling guard |
| `storied_version_constants.py` | v2.2.0 versioning |

**Feature flag**: All Storied code is guarded by `STORIED_MODE` env var (default: false). When false, pipeline runs identically to Beta.

