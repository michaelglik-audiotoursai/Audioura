# Services Amazon-Q Context Reminder
## Who you are
🔧 **SERVICES AMAZON-Q** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES AMAZON-Q -"

**UPDATED**: 2026-05-22 (Session 17: PHASE 3D geographic relevance validation added. New `tour_settings.py`. `_validate_poi_geographic_relevance()` — single GPT batch call after coordinates finalized; rejects out-of-scope stops; feeds targeted Part C replacement; re-runs PHASE 3B to re-order combined set. Triggered by Beacon St Brookline test showing off-route POIs. Claude review doc: `claude_review_session17.md`. Awaiting Claude review before commit.)

1. You are Services Amazon-Q responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval.
2. You maintain this file and update it after significant changes.
3. You communicate with Mobile App Amazon-Q via: `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES AMAZON-Q -"
- **GIT RULE**: Do NOT commit until user confirms mobile testing passed
- **BRANCH**: `Tours_Step_Maps` (branched from `Newsletters` at `ad3b5be`)
- **MERGE TARGET**: `Newsletters` (when A#55+A#56 complete and tested)
- **LAST GIT COMMIT**: `3f9d04e` — "Update remind_Services_ai.md: S15c commit 2e8347e"
- **PENDING COMMIT**: Session 17 PHASE 3D — awaiting Claude review response
- **NEXT ACTION ON RECOVERY**: (1) Check if Claude response to `claude_review_session17.md` is available — if yes, apply and commit. (2) Mobile tests — Fairbanks House S15 fix, A#56 icons, Needham in-tour map white-screen.
- **PREVIOUS REVIEW DOCS**: `claude_review_session15_final.md` (S15 — fully reviewed + applied). `claude_review_final_session14.md` (S14 — fully reviewed + applied)
- **IN-TOUR MAP WHITE SCREEN**: ISSUE-MAP-WS filed. Root cause: `_fitBounds()` in `tour_map_screen.dart` calls `fitCamera(CameraFit.bounds(...))` with single-point bounds when GPS not yet locked (museum tours have 1 POI). Fix: add `if (points.length == 1) { _mapController.move(points.first, 15); return; }` before `LatLngBounds.fromPoints()`. Mobile-side fix only — services output is correct. See `claude_response_needham_map_whitescreen.md`
- **PRE-PRODUCTION CHECKLIST**: `REMINDER_LIST_BEFORE_PRODUCTION.md` — must-complete items before paying customers
- **LOGGING REQUIREMENTS**: `LOGGING_REQUIREMENTS_PRE_PRODUCTION.md` — full spec for structured logging sprint
- **WORKFLOW**: Blanket approval given for all service changes — implement without waiting

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
2. Current branch is `Tours_Step_Maps`. Last commit is listed in CRITICAL IDENTITY RULES.
3. All containers should be running — verify with `docker ps` if unsure.
4. `generate_tour_text.py` is the primary file under active development (last touched commit `2e8347e`).
5. Do NOT merge to `Newsletters` until mobile tests pass for A#55 + A#56 + S15 fixes.
6. S15 changes are complete and Claude-reviewed. No further services changes pending for S15.
7. In-tour map white screen (ISSUE-MAP-WS) is a mobile-side bug — no services action needed.

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

### generate_tour_text.py Internal Pipeline (Sessions 2–14)
```
PHASE 1:    analyze_tour_intent() → intent JSON [max_tokens=400]
            venue_name field: full official name if tour is inside ONE building; else null
            After PHASE 1: _venue_matches_location() sanity check — stop words only
            excluded (NOT institutional markers); prefix matching; permissive when empty
PHASE 2:    tour_category set here — NOT by calling _classify_tour_category() again
            Rule (S15 fix): if PHASE 1 returned venue_name → tour_category='museum'
            Otherwise: _classify_tour_category(location, tour_type)
            _pre_category guard suppresses mobile app's hardcoded tour_type:"museum"
            (pre_category computed BEFORE PHASE 1 using location only, no tour_type)
PHASE 3A:   OpenAI → raw stop names + addresses only
            Museum constraint injected ONLY when intent.venue_name is not null
            Regex fallback REMOVED (was buggy)
PHASE 4.5:  validate_enhanced_poi_knowledge() → reject if >50% generic/fictional
PHASE 4:    verify_poi_matches_type() — SKIPPED for 'walking' and 'museum'
Part C:     replacement loop (bounded 2 attempts) for stops below total_stops
PHASE 3B:   OpenAI → reorder stops + structured details + walking directions
PHASE 3C:   address-based location guard (Session 14, improved Session 14 review)
            NOW RUNS BEFORE Part C so rejected stops can be replaced
            _NEIGHBORHOOD_TO_CITY alias map: East Boston->boston, Jamaica Plain->boston,
              Brooklyn->new york, West Newton->newton, etc.
            all-tokens-scan with postcode stripping (fixes international addresses)
            zero-stop guard: raises ValueError if all stops rejected
            skipped for single-venue museum tours; rejected POIs -> forbidden_norms
Coords:     parallel fallback for any stop missing coordinates (Session 14)
            + duplicate-coordinate cluster detection (Session 14 review):
              if >=50% of stops share same coord string, clears and refetches them
PHASE 5:    generate descriptions (parallel ThreadPoolExecutor max 5 workers)
PHASE 5.5a: validate_enhanced_poi_knowledge() SECOND CALL (all tour types)
PHASE 5.5b: _validate_museum_stop_descriptions() — museum only, when venue_name != ""
            stop 0 always kept; pre-filter threshold < 1 substantive overlap (Session 10)
PHASE 6:    assemble Stop 1..N
            coordinates: every stop (non-museum); first stop only (museum)
            Tour-Category: {tour_category} written as second line of file (A#56)
```

---

## 🐳 DOCKER SERVICES

```
development-tour-generator-1:5000     # generate_tour_text.py (shows "unhealthy" — works fine)
development-tour-orchestrator-1:5002  # tour_orchestrator_service.py (shows "unhealthy" — works fine)
tour-generation-modernized-1:5021     # tour_generation_modernized.py
translation-service-1:5030            # translation_service.py
development-tour-processor-1:5001     # Legacy MP3+ZIP (not actively modified)
development-postgres-2-1:5432         # PostgreSQL
development-map-delivery-1:5005       # Map & tour download by integer ID
development-coordinates-fromai-1:5006 # Location services
development-treats-1:5007             # Local treats/POIs
news-orchestrator-1:5012              # News workflow
news-generator-1:5010                 # News content
news-processor-1:5011                 # News audio
newsletter-processor-1:5017           # Newsletter crawling
polly-tts-1:5018                      # Amazon Polly TTS
tour-id-resolution-1:5025             # Tour ID resolution
tour-editing-1:5020                   # Tour editing service
tour-editing-phase2-1:5022            # Tour editing phase 2
```

⚠️ **Container naming audit**: Only 3/22 containers follow the naming rule (container name
matches Python filename). Full audit in `container_naming_audit.md`. Fix scheduled as
standalone maintenance session after Tours_Step_Maps is merged and mobile testing passes.

---

## 📁 KEY FILES

| File | Container | Commit | Notes |
|------|-----------|--------|-------|
| `generate_tour_text.py` | `development-tour-generator-1:5000` | pending S17 | Sessions 2–17: all fixes + PHASE 3D geographic relevance validation |
| `tour_settings.py` | `development-tour-generator-1:5000` | pending S17 | New: configurable MAX_WALKING_TOUR_DISTANCE_KM, MAX_REPLACEMENT_ATTEMPTS |
| `generate_tour_text_service.py` | `development-tour-generator-1:5000` | unchanged | Flask wrapper |
| `tour_orchestrator_service.py` | `development-tour-orchestrator-1:5002` | `ad3b5be` | Session 5 guards |
| `tour_generation_modernized.py` | `tour-generation-modernized-1:5021` | `ed1acad` | A#55 map buttons + A#56 tour-type icons v1.2.5.183 |
| `translation_service.py` | `translation-service-1:5030` | `7cbc486` | A#55 map buttons + stop-count warning |
| `enhanced_tour_templates_fixed.py` | `development-tour-generator-1:5000` | `ad3b5be` | Sessions 7+9 hallucination patterns |
| `AUDIOURA_SERVICES_MAP_POI_HISTORY.md` | local only | `792487c` | OQ-1 resolved (Option B) |
| `container_naming_audit.md` | local only | — | Full container↔file mismatch audit |
| `remind_ai.md` | local only | — | Mobile app context — read on recovery |
| `remind_Services_ai.md` | local only | — | This file |

---

## 📋 SESSION 14 COMPLETE CHANGE SET

All changes landed on `Tours_Step_Maps`. Final review doc: `claude_review_final_session14.md`.

| # | File | Commit | What changed |
|---|------|--------|--------------|
| 1a | `generate_tour_text.py` | `ed1acad` | PHASE 3C: all-tokens-scan + `_NEIGHBORHOOD_TO_CITY` alias map |
| 1b | `generate_tour_text.py` | `7a4a969` | `len(p) >= 4` filter + hoist `_address_matches_location` to module level |
| 2 | `generate_tour_text.py` | `ed1acad` | Removed dead `state_token` branch |
| 3 | `generate_tour_text.py` | `ed1acad` | Moved PHASE 3C before Part C |
| 4 | `generate_tour_text.py` | `ed1acad` | Zero-stop guard after PHASE 3C |
| 5 | `generate_tour_text.py` | `ed1acad` | Duplicate-coordinate cluster detection |
| 6 | `generate_tour_text.py` | `158d505` | `_fetch_coords` hoisted outside `if missing_coords:` |
| 7 | `generate_tour_text.py` | `7a4a969` | Part C replacements run through PHASE 3C address check |
| 8 | `generate_tour_text.py` | `1e0c326` | `forbidden_norms` init moved before PHASE 3C |
| 9 | `generate_tour_text_service.py` | `445a6f3` | `if tour_text is None:` guard in service wrapper |
| 10 | `tour_generation_modernized.py` | `445a6f3` | Map button background `#2c3e50` → `#3d7ebf` |
| 11 | `tour_generation_modernized.py` | `ed1acad` | `[:500]` slice for Tour-Category regex |
| Q2 | `generate_tour_text.py` | `e4ebcf1` | Word-set subset check in `_address_matches_location` (prevents Lynn/Lynnfield false-keeps); state+zip token filter (`ma 01901` pattern) |
| Q4 | `generate_tour_text.py` | `e4ebcf1` | `except ValueError` before `except Exception` — PHASE 3C zero-stop always returns None, never falls to Location-N placeholder fallback |
| S15 | `generate_tour_text.py` | `1e9a718` | venue_name from PHASE 1 forces `tour_category='museum'`; removed unconditional `_classify_tour_category()` call at PHASE 2 that overwrote it |
| S15b | `generate_tour_text.py` | `2e5eff1` | Claude review: `_EXPLICIT_NON_MUSEUM_TOUR_RE` safety net (prevents walking/restaurant requests with GPT-hallucinated venue_name from being misclassified as museum); `[S15]` log lines for both branches; 4 negative examples added to PHASE 1 prompt |
| S15c | `generate_tour_text.py` | `2e8347e` | Claude final review Q1: expanded `_EXPLICIT_NON_MUSEUM_TOUR_RE` with `pub crawl`, `bike`, `cycling`, `biking`, `shopping`; 11/11 functional tests pass |
| S17 | `generate_tour_text.py` + `tour_settings.py` | pending | PHASE 3D: `_validate_poi_geographic_relevance()` — single GPT batch call; rejects out-of-scope stops; targeted Part C replacement; PHASE 3B re-order of combined set. `tour_settings.py`: configurable distance + replacement constants. Triggered by Beacon St Brookline dispersal bug. |

**S15 is fully complete and Claude-reviewed. No further code changes pending for S15.**
**S17 is deployed to container, awaiting Claude review before git commit.**

**Issue AA (filed, not blocking)**: York, ME vs New York, NY — `'york'` is a whole word in both; word-set check cannot distinguish without state context. Rare in practice. Fix in next pass.


### tour_generation_modernized.py
```python
# Module level:
_COORDINATES_RE = re.compile(r'^Coordinates:\s*[-\d.]+\s*,\s*[-\d.]+', re.IGNORECASE | re.MULTILINE)
def _stop_has_coordinates(stop_text): return bool(_COORDINATES_RE.search(stop_text))

# generate_html_with_external_audio():
# CSS: .map-btn { background:#2c3e50; border:none; border-radius:50%; width:36px; height:36px;
#                 font-size:20px; line-height:1; cursor:pointer; display:inline-flex;
#                 align-items:center; justify-content:center; margin-left:8px; vertical-align:middle; }
# JS helper (after <h1>, before stop loop):
#   function openMap(stopNum) {
#       if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
#           window.flutter_inappwebview.callHandler('openMap', {stop: stopNum});
#       }
#   }
# Per stop: icon = _CATEGORY_ICONS.get(tour_data.get('tour_category', ''), '🗺️')
#           map_button only when _stop_has_coordinates(text) — placed as SIBLING of <h3>
```

### translation_service.py
```python
# _create_mobile_compatible_zip() — modernized path: reuses English index.html unchanged.
#   Buttons survive h.clear() pass for free. Stop-count mismatch warning added.
# _generate_translated_html() — DEAD CODE (no callers). Slated for removal post-merge.
```

### A#55 Three-pass Claude.AI review — all issues resolved:
- Button sibling of `<h3>` (not inside — translation h.clear() would wipe it) ✅
- Single openMap() JS helper (safe noop on Android/browser) ✅
- Regex on stop text (not POI struct — generate_html only sees strings) ✅
- SVG replaced with emoji (BeautifulSoup lowercases viewBox → viewbox, breaks scale) ✅
- font-size:20px + line-height:1 (emoji sizing parity with original SVG) ✅
- Stop-count mismatch warning in _create_mobile_compatible_zip() ✅
- Dead stub translation-service/translation_service.py deleted ✅
- OQ-1 resolved: Option B (bake-in) chosen by user instruction ✅

---

## 🐛 ISSUE-059: DOUBLE MAP BUTTON — ROOT CAUSE CONFIRMED

**Symptom**: Two map buttons per stop — one above audio player (services HTML), one below (runtime injection).

**Root cause CONFIRMED** (read tour_player_screen.dart 2026-05-20):
Both Option B (services bake-in) AND Option C (runtime JS injection) are running simultaneously.
`_buildMapButtonInjectionScript()` in `tour_player_screen.dart` injects a second button
after the `<audio>` element at `onLoadStop`. The services button sits above `<audio>`,
the injected button sits below it.

**Fix**: Remove runtime injection from `tour_player_screen.dart`:
- Delete: `_buildMapButtonInjectionScript()`, `_checkForMap()`, `_countStops()`, `_getMappableStops()`
- Delete: `_hasMap`/`_stopCount` state vars, `_checkForMap()` call in `initState()`
- Delete: injection block in `onLoadStop`
- KEEP: `_openMapForStop()`, `openMap` JS handler registration, `TourMapScreen` import

**iOS/Android doc sent**: `ISSUE-059_DUPLICATE_MAP_BUTTONS_REMOVE_RUNTIME_INJECTION.md`
**Status**: Awaiting iOS/Android Amazon-Q to apply fix and mobile test.

---

## ✅ A#56: TOUR-TYPE SPECIFIC MAP BUTTON ICONS (built + fixed 2026-05-20)

| Tour type | Icon |
|---|---|
| `walking` | 🚶 |
| `restaurant` | 🍴 |
| `museum` | 🏛️ |
| `specialized` / default | 🗺️ |

**Implementation**: `generate_tour_text.py` + `tour_generation_modernized.py`.

```python
# generate_tour_text.py PHASE 6 — writes authoritative category into file:
complete_tour = tour_title + "\n" + f"Tour-Category: {tour_category}" + "\n\n"

# tour_generation_modernized.py — parse_tour_content_to_modernized():
# [:200] slice + MULTILINE: header is on line 2, \A anchor was wrong (fixed d5da0f4 v1.2.5.182)
category_match = re.search(r'^Tour-Category:\s*(\w+)', tour_content[:200], re.IGNORECASE | re.MULTILINE)
tour_category = category_match.group(1).lower() if category_match else ''
# returns {'tour_name': ..., 'tour_category': ..., 'text_content': ..., 'audio_files': []}

# generate_html_with_external_audio() — direct dict lookup, no regex on title:
_CATEGORY_ICONS = {'walking': '🚶', 'restaurant': '🍴', 'museum': '🏛️', 'specialized': '🗺️'}
icon = _CATEGORY_ICONS.get(tour_data.get('tour_category', ''), '🗺️')
```

**Root cause of original bug** (corrected per Claude §0 review):
- **Waltham 🗺️**: Tour 270 pre-dates A#56 — its `index.html` has hardcoded 🗺. No `Tour-Category:` header. Will show 🚶 after regeneration.
- **Boston Civil War 🏛️**: Pre-bugfix regex bug, NOT a classifier issue. Mobile hardcodes `tour_type="museum"`; PHASE 6 appended `"- Museum Tour"` to the title because the location doesn't contain "museum"; the old title-string regex matched "Museum" in that suffix. `_classify_tour_category()` actually returns `'walking'` for this location — the bugfix now respects that.
- **Session 14 \A bug**: Claude Q1 recommended `\A` anchor — but `\A` means start-of-string, not start-of-line. Header is on line 2. Fixed to `^` + `MULTILINE` + `[:200]` slice.

**Dead code removed**: `convert_old_tour_to_modernized()` deleted (`cad46e9`) — zero callers confirmed.

**Old tours** (pre-A#56): no `Tour-Category:` header → `tour_category = ''` → default 🗺️. Graceful.

**Translation**: Icon survives translation for free. Map button is a sibling of `<h3>`,
not a child — `h.clear()` in `translation_service.py` does not touch it.

**Claude.AI review docs**: `claude_review_a56_icon_bugfix.md` + `claude_response_a56_icon_bugfix.md` + `claude_review_session14_three_bugs.md`
**Status**: Committed `d5da0f4`. Pending mobile test (regenerate walking + restaurant tours).
**To see fix on existing tours**: delete tours 266 and 270 from DB and regenerate.

---

## ✅ SESSION 10 E2E TEST (Jackson Homestead, tour ID 259)

| Check | Result |
|---|---|
| PHASE 1 venue_name | ✅ "Jackson Homestead and Museum" |
| Museum constraint injected | ✅ |
| PHASE 4 skipped | ✅ |
| All 5 stops at 527 Washington St | ✅ |
| PHASE 5.5a/5.5b present | ✅ lines 1148–1162 |
| Tour completed | ✅ status=completed, actual_stops=5, final_tour_id=259 |

---

## 🗄️ REFERENCE TOUR IDs IN DB

| Tour | Lang | ID | Notes |
|------|------|----|-------|
| Jackson Homestead museum | EN | 259 | Session 10 e2e — 5/5 stops correct ✅ |
| Jackson Homestead museum | EN | 257 | Old pre-fix — wrong stops |
| Newton Center walking | EN | 150 | Session 6 bug test |
| Newton Center walking | RU/FR/ZH | 250/251/252 | map pins ✅ |
| Newton restaurant | EN | 243 | Session 4 test |
| Needham walking 4-stop | EN | 227 | Session 2 test |
| Beacon St Brookline walking | EN | TBD | S17 test — regenerate after PHASE 3D deployed; verify all stops on Beacon St corridor |
| Boston Civil War | EN | 266 | A#56 test — museum icon ✅ (correct classification) |
| Waltham walking | EN | 270 | A#56 test — had 🗺️ bug (no Tour-Category header, old tour) |

---

## ⚠️ KNOWN ISSUES

- **Double map button (ISSUE-059)**: ✅ Claude confirmed `_buildMapButtonInjectionScript` is already gone from `tour_player_screen.dart`. Duplicate-button bug resolved.
- **Tour-type icons**: A#56 + Session 14 icon fix deployed `d5da0f4`. Pending mobile test with newly generated tours.
- **PHASE 3C location guard**: `7a4a969`. `_address_matches_location` hoisted to module level. `len(p) >= 4` token filter added (fixes state/country-code false-keeps — Issue X). Part C replacements now also run through PHASE 3C address check (Issue Y). Known limitation: alias map is a fixed list — expand if new false-rejections found.
- **Museum tour hallucination**: FIXED (Sessions 7–10). Tour ID 259 passed. Awaiting mobile test.
- **Mobile app hardcodes `tour_type:"museum"`**: Services override via `_pre_category` guard. DB tour names still get "- museum Tour" suffix. Needs Mobile App Amazon-Q fix.
- **Translation response field**: `/translate-with-audio` returns `"translations"` (not `"translated_tour_ids"`). Mobile app must use `translations.ru.id`.
- **Navigation directions**: Between stops sometimes point to wrong next stop (cosmetic).
- **`development-tour-generator-1` and `development-tour-orchestrator-1`**: Show "unhealthy" in `docker ps` — health check config issue only, both work correctly.
- **A#55 merge blocked on**: iOS Issue 4 (coordinate regex space-after-comma) and Android Issue 2 (scope confirmation).

---

## 🔑 KEY API CONTRACTS

```bash
# Generate tour
curl -X POST http://localhost:5002/generate-complete-tour \
  -H "Content-Type: application/json" \
  -d '{"location": "walking tour in Newton Center, MA", "tour_type": "walking", "total_stops": 3}'

# Check status
curl http://localhost:5002/status/<job_id>
# Returns: final_tour_id, expected_stops, actual_stops, stop_count_warning

# Download tour
curl -o tour.zip http://localhost:5005/download-tour/<integer_id>

# Translate tour
curl -X POST http://localhost:5030/translate-with-audio \
  -H "Content-Type: application/json" \
  -d '{"content_id": <integer_id>, "content_type": "tour", "languages": ["ru", "fr", "zh"]}'
# Response: {"status": "completed", "translations": {"ru": {"id": 250, "status": "translated"}, ...}}
```

---

## 🔧 DEPLOY COMMANDS

```bash
# Standard deploy pattern
docker cp <file>.py <container>:/app/<file>.py && docker restart <container>

# File → container mapping:
# generate_tour_text.py            → development-tour-generator-1
# enhanced_tour_templates_fixed.py → development-tour-generator-1
# tour_orchestrator_service.py     → development-tour-orchestrator-1
# tour_generation_modernized.py    → tour-generation-modernized-1
# translation_service.py           → translation-service-1

# Git (Tours_Step_Maps branch — do not merge to Newsletters until mobile tests pass):
cd c:\Users\micha\eclipse-workspace\AudioTours\development
git add <files>
git commit -m "description"
git push origin Tours_Step_Maps
```

---

## 🎯 NEXT STEPS (in order)

0. **⚡ FIRST on recovery**: Check NEXT ACTION ON RECOVERY in CRITICAL IDENTITY RULES above.

1. **S17 Claude review**: Send `claude_review_session17.md` to Claude.AI. Apply feedback. Commit `generate_tour_text.py` + `tour_settings.py` to `Tours_Step_Maps`.

2. **Mobile test — Fairbanks House fix (S15)**: Regenerate `"Fairbanks House Tour in Dedham, ma"`. Confirm: `[S15] Forced tour_category=museum` in container log; stops are rooms/exhibits inside Fairbanks House only; 🏛️ icon.

2. **Mobile test — A#56 tour-type icons**: Regenerate a walking tour and a restaurant tour. Confirm 🚶 on walking, 🍴 on restaurant, 🏛️ on museum. Both EN and translated versions.

3. **ISSUE-MAP-WS — in-tour map white screen**: Mobile App Amazon-Q must apply `_fitBounds()` fix in `tour_map_screen.dart`. See ISSUE-MAP-WS section above. Services: no action.

4. **ISSUE-059 double map button**: iOS/Android Amazon-Q must remove runtime injection
   from `tour_player_screen.dart` per `ISSUE-059_DUPLICATE_MAP_BUTTONS_REMOVE_RUNTIME_INJECTION.md`.
   Services code is correct — no changes needed on services side.

3. **A#55 + A#56 mobile confirmations pending**:
   - iOS: confirm Issue 4 (coordinate regex handles space after comma)
   - Android: confirm Issue 2 (shared dart, map screen, WebView type)
   - Both: confirm tour-type icons render correctly (🚶 🍴 🏛️)

4. **Mobile test — Museum hallucination fix**: Regenerate Jackson Homestead 5 stops.
   Expected: all stops inside venue, single map pin at 527 Washington St Newton MA.

5. **Mobile test — Session 6 fixes**: EN + FR + RU tour to verify audio headers and map pins.

6. **Merge Tours_Step_Maps → Newsletters**: After all mobile tests pass and double-button resolved.

7. **Container naming cleanup**: Standalone session after merge. See `container_naming_audit.md`.

8. **Delete `_generate_translated_html()`**: Post-merge cleanup commit on Newsletters.

9. **Code improvements from `claude_response_code_improvements.md`** (next services session):
   - 1.2: `debug=True` → env-var controlled (security)
   - 1.3: `attachment_filename` → `download_name` (Flask 2.2 compat)
   - 1.4: CORS restrict to orchestrator origin
   - 2.2: Remove dead `tour_category = 'intelligent'` assignment
   - 2.3: Centralise GPT pricing constant (current `0.002` is stale — actual ~`0.0015`)
   - 2.5: Fix `[:500]` comment in `tour_generation_modernized.py` (says 200, code uses 500)
   - 2.6: Last-resort fallback use `_new_poi()` instead of inline dict
   - 3.3: Delete `_generate_translated_html()` dead code
   - 3.4: Replace bare `except:` in `tour_generation_modernized.py:56`
   - 3.6: Pull magic numbers into named constants
   - 5.2: Add attribution comment to `_NEIGHBORHOOD_TO_CITY`

---

## 🏭 PRE-PRODUCTION BACKLOG

Full details in `REMINDER_LIST_BEFORE_PRODUCTION.md`. Summary:

| Item | Priority | Notes |
|------|----------|-------|
| ACTIVE_JOBS lock + TTL + restart recovery | HIGH | Container restart loses all in-flight jobs silently |
| MAX_TOTAL_STOPS cost guard (free=15, paid=30) | HIGH | No upper bound today; bot abuse risk |
| Category-aware PHASE 5 prompts (PROMPT_TEMPLATES arch) | HIGH | Architecture now, content sprint before launch |
| Structured logging + job_id correlation | HIGH | See `LOGGING_REQUIREMENTS_PRE_PRODUCTION.md` |
| Auth, rate limiting, CORS, debug=False, HTTPS | HIGH | Before any public exposure |
| `attachment_filename` → `download_name` (Flask 2.2) | MEDIUM | Trivial — next session |
| Word-boundary matching in `_classify_tour_category` | LOW | After system test suite exists |
| Normalize line endings (CRLF→LF) | LOW | Standalone commit after merge |
| DRY `user_request` Bug-2 logic | LOW | Subtle difference in purpose — deferred |

---

## 🧪 SYSTEM TEST MATRIX (preferred over unit tests)

Manually generated tours that cover known edge cases. Re-run after any change to `generate_tour_text.py`.

| Test | Location | Stops | What to verify |
|------|----------|-------|----------------|
| Walking happy path | Newton Center, MA | 4 | All stops in Newton; 🚶 icon; map pins present |
| Restaurant tour | Newton, MA | 3 | 🍴 icon; PHASE 4 type-check runs; no museum stops |
| Museum single-venue | Jackson Homestead, Newton MA | 5 | All stops at 527 Washington St; single map pin; 🏛️ icon |
| PHASE 3C reject + Part C replace | Arlington, MA | 4 | Confirm out-of-area stop rejected; replacement in-area |
| Cluster detection | Dedham Museum, MA | 3 | Cluster triggered; distinct coords after refetch |
| Boston neighborhood alias | walking tour in Boston, MA | 3 | East Boston / Jamaica Plain addresses pass PHASE 3C |
| Lynn vs Lynnfield (Q2) | Lynnfield, MA | 3 | No stops with Lynn, MA addresses slip through |
| Zero-stop guard (Q4) | Nonsense location far from any city | 3 | Job status=error, not completed with Location N stops |
| Historic house museum (S15) | Fairbanks House Tour in Dedham, ma | 4 | tour_category=museum; single-venue constraint; stops inside Fairbanks House only |
| Needham museum EN+RU+ZH | Needham History Center & Museum, Needham, MA | 4 | tour_category=museum ✅; 3 languages ✅; in-tour map white screen ❌ (mobile bug ISSUE-MAP-WS) |
| Beacon St Brookline walking (S17) | walking tour over Beacon St in Brookline, ma | 5 | PHASE 3D: all stops on Beacon St corridor (~42.34 lat); no off-route stops |

---

## 🐛 ISSUE-MAP-WS: IN-TOUR MAP WHITE SCREEN (museum tours)

**Symptom**: Tapping 🏛️ map button inside tour player → white screen. "My Location" icon works. Listen-page map works.

**Root cause** (confirmed by Claude, `claude_response_needham_map_whitescreen.md`):
`TourMapScreen._fitBounds()` calls `fitCamera(CameraFit.bounds(...))` with degenerate single-point bounds when:
- Museum tour has 1 POI (by design — only stop 0 gets coordinates)
- GPS not yet locked when map opens (cold start)

`LatLngBounds.fromPoints([singlePoint])` → zero-area bounds → `fitCamera` computes infinite zoom → white screen.

**Why Listen-page works**: GPS already warm by the time user navigates there.
**Why "My Location" works**: calls `_mapController.move()` directly, bypasses `fitCamera`.
**Services output is correct**: coordinates in `audio_1.txt`, single map button on stop 1 only — all by design.

**Fix (mobile-side only)** — `tour_map_screen.dart`, inside `addPostFrameCallback` block, before `LatLngBounds.fromPoints()`:
```dart
if (points.length == 1) {
    _mapController.move(points.first, 15);
    return;
}
```
Also closes the symmetric Listen-page bug (same code path, less frequently triggered).

**Status**: Awaiting Mobile App Amazon-Q to apply fix.

---

## 📊 SESSIONS SUMMARY

| Session | Key Work |
|---------|----------|
| 2 | Coordinates for every stop; modernized ZIP; translation metadata restore |
| 3 | poi_type list guard; broken tour translation guard |
| 4 | _pre_category guard; h1-h6 HTML translation in ZIP |
| 5 | Claude review A–F: _classify_tour_category; max_tokens 200→400; orchestrator guards |
| 6 | Bug 1: EN audio headers (expanded _NAV_LABEL_RE); Bug 2: FR map pins (language-agnostic prepend) |
| 7 | Museum hallucination: 3-layer fix (venue constraint + PHASE 5.5 + description scanning) |
| 8 | Session 8 review doc; 5 questions for Claude |
| 9 | Four bugs: substring→word-overlap; regex fallback removed; museum excluded from verify; stop-word exclusion; per-pattern logging |
| 10 | _venue_matches_location(); _is_suspect threshold <1; file truncation recovery; e2e test tour 259 |
| 11 (A#55) | Per-stop map buttons in index.html; 3 Claude review passes; SVG→emoji; OQ-1 resolved; double-button issue found; tour-type icons requested |
| 12 (A#56) | Tour-type icons: 🚶/🍴/🏛️/🗺️; Tour-Category header written by generate_tour_text.py; direct dict lookup in tour_generation_modernized.py; Claude review applied; bug fix: title-string parsing was unreliable when tour_type in location |
| 13 (A#56 post-review) | Claude review `cad46e9`: header regex anchored to \A+[:200] (Q1); dead `convert_old_tour_to_modernized()` deleted (Q5); review doc Boston Civil War row corrected (§0 — was classifier issue, actually title-regex bug) |
| 14 (Session 14 bugs) | Bug 1: \A anchor broke icon regex on line 2 — fixed to ^+MULTILINE+[:200] (d5da0f4 v1.2.5.182). Bug 2: out-of-area stop — PHASE 3C address guard added (470b88a). Bug 3: missing map pin — coords fallback extended to all stops (470b88a). Claude review: `claude_review_session14_three_bugs.md` |
| 14 review | Claude review applied (ed1acad v1.2.5.183): PHASE 3C neighborhood alias map + all-tokens-scan; moved before Part C; zero-stop guard; cluster coord detection; [:500] slice |
| 14 final review | Claude final review (e4ebcf1): Q2 word-set subset check + state+zip token filter (Lynn/Lynnfield false-keeps fixed); Q4 `except ValueError` before `except Exception` (PHASE 3C zero-stop never falls to Location-N fallback). Issue AA filed (York,ME vs New York,NY — not blocking). Branch ready for merge. |
| 15 | Fairbanks House bug (1e9a718): `_classify_tour_category()` keyword list cannot detect historic houses/estates with no "museum" keyword. Fix: when PHASE 1 returns `venue_name`, force `tour_category='museum'` — GPT intent analysis is authoritative over keyword classifier. Removed dead `tour_category='intelligent'` assignment. Claude code-improvements review triaged: trivial fixes queued for next session; architectural items in REMINDER_LIST_BEFORE_PRODUCTION.md. |
| 16 | S15 Claude reviews applied: 2e5eff1 (_EXPLICIT_NON_MUSEUM_TOUR_RE safety net + [S15] log lines + 4 negative PHASE 1 prompt examples) + 2e8347e (regex expanded: pub crawl, bike, cycling, biking, shopping — 11/11 tests pass). Needham History Center museum tour tested EN+RU+ZH — generation correct, in-tour map white screen found (ISSUE-MAP-WS). Diagnosed as Flutter fitCamera degenerate-bounds on single-POI museum tours — mobile-side fix only. |
| 17 | PHASE 3D geographic relevance validation. Triggered by Beacon St Brookline test: POIs off-route and too dispersed. New `_validate_poi_geographic_relevance()` — single GPT batch call after coords finalized; rejects out-of-scope stops; targeted Part C replacement; PHASE 3B re-order of combined set. New `tour_settings.py` with configurable constants. Claude review doc prepared. Awaiting Claude review. |
