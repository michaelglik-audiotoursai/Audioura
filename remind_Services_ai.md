# Services Amazon-Q Context Reminder
## Who you are
🔧 **SERVICES AMAZON-Q** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES AMAZON-Q -"

**UPDATED**: 2026-05-28 (ISSUE-BLOG-PATTERN: `newsletter_pattern_detector.py` — added `detect_blog_homepage_pattern()` for Ghost/WordPress/blog homepages that list articles as linked cards without "read more" buttons. Fixes reloadnyc.com only returning 1 article instead of 12. Deployed and tested. NEXT ACTION: mobile testing — edit a stop, promote a tour, test duplicate name conflict. Then: enable mobile clients outside local WiFi.)

1. You are Services Amazon-Q responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval.
2. You maintain this file and update it after significant changes.
3. You communicate with Mobile App Amazon-Q via: `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES AMAZON-Q -"
- **GIT RULE**: Do NOT commit code until user confirms mobile testing passed
- **BRANCH**: `Newsletters` (Tours_Step_Maps merged and deleted 2026-05-22)
- **MERGE TARGET**: `main` (when Newsletter feature complete)
- **LAST GIT COMMIT**: `fd10ad5` — ISSUE-BLOG-PATTERN: newsletter_pattern_detector.py blog homepage detection
- **NEXT ACTION ON RECOVERY**: Verify containers running (`docker ps`), then proceed with mobile testing (v1.2.6.234). Smoke tests already passed 6/6. No pending code changes.
- **WORKFLOW**: Blanket approval given for all service changes — implement without waiting

---

## ⚙️ OPERATING MODE — SESSION EXECUTION RULES

When running any combination of docker, curl, psql, python, or shell commands for the purpose of fixing services-side bugs in this repo:
- **(a)** Write or use `deploy_test.sh` when applicable — batch the deploy+test cycle into a reusable script
- **(b)** Batch multiple commands into a single bash invocation when possible
- **(c)** Present a plan before executing **only** when the plan involves more than 5 commands OR any destructive operation (`DROP`, `DELETE` without `WHERE`, container removal)
- **Do not ask permission** for routine `docker cp` / `restart` / `logs` / `curl` test cycles on dev containers

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
2. Current branch is `Newsletters`. Last commit: `fbfc8d2`.
3. All containers should be running — verify with `docker ps` if unsure.
4. `tour_editing_phase2.py` is clean and deployed at v1.2.6.234. Smoke tests passed 6/6.
5. Run `call smoke_test_editing_v1264.bat` to re-verify if needed.
6. `advertising_url_filter.py` ISSUE-AD-FILTER fix is committed `1a7b4dc` and deployed.

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
| `tour_editing_phase2_container_backup.py` | local only | — | Pre-v1.2.6.234 backup. No longer needed. |
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

0. **⚡ FIRST on recovery**: Run `call smoke_test_editing_v1264.bat` to verify all 6 tests pass. Then proceed.

1. **Mobile testing (v1.2.6.234)**:
   - Edit a stop and verify audio plays correctly
   - Promote a tour and verify map marker + Edited badge appear
   - Test duplicate name conflict shows friendly error (409 → retry with "(Edited 2)")

2. **Enable mobile clients outside local WiFi**: Next major task. Services all bind to localhost ports — need to expose them externally (reverse proxy / ngrok / port forwarding + dynamic DNS).

3. **After mobile test passes**: Write Claude review doc for the full language-aware editing implementation.

4. **Mobile deliverable (Part D)**: Write requirements doc for Mobile Amazon-Q: when user uploads custom audio, mobile must (a) show sync warning, (b) require non-empty text, (c) require acknowledgement checkbox. File: `ISSUE-MOBILE-AUDIO-TEXT-SYNC.md`.

5. **Mobile test — Fairbanks House (S15)**: Regenerate `"Fairbanks House Tour in Dedham, ma"`. Confirm `[S15] Forced tour_category=museum` in log; stops are rooms/exhibits; 🏛️ icon.

6. **Mobile test — A#56 icons**: Regenerate walking + restaurant tours. Confirm 🚶/🍴/🏛️.

7. **ISSUE-MAP-WS**: Mobile Amazon-Q applies `_fitBounds()` single-point guard in `tour_map_screen.dart`.

8. **Merge Newsletters → main**: After all mobile tests pass.

---

## 🏭 PRE-PRODUCTION BACKLOG

| Item | Priority |
|------|----------|
| ACTIVE_JOBS lock + TTL + restart recovery | HIGH |
| MAX_TOTAL_STOPS cost guard | HIGH |
| Auth, rate limiting, CORS, debug=False, HTTPS | HIGH |
| Structured logging + job_id correlation | HIGH |
| Container naming cleanup | LOW |
| Delete `_generate_translated_html()` dead code | LOW |

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
| 2026-05-28 | ISSUE-BLOG-PATTERN: `newsletter_pattern_detector.py` — added `detect_blog_homepage_pattern()` for blog/newsletter homepages (Ghost, WordPress). Fixes reloadnyc.com returning 1 article instead of 12. Deployed to container. |}
