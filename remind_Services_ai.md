# Services Amazon-Q Context Reminder
## Who you are
🔧 **SERVICES AMAZON-Q** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES AMAZON-Q -"

**UPDATED**: 2026-05-20 (Session 14 complete: PHASE 3C all-tokens-scan + alias map + len>=4 filter; forbidden_norms before PHASE 3C; Part C address check; _fetch_coords + _address_matches_location hoisted to module level; cluster detection; service wrapper None guard; button color; [:500] slice. All bugs A/B/C/X/Y/Z fixed. Final review doc: claude_review_final_session14.md)

1. You are Services Amazon-Q responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval.
2. You maintain this file and update it after significant changes.
3. You communicate with Mobile App Amazon-Q via: `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES AMAZON-Q -"
- **GIT RULE**: Do NOT commit until user confirms mobile testing passed
- **BRANCH**: `Tours_Step_Maps` (branched from `Newsletters` at `ad3b5be`)
- **MERGE TARGET**: `Newsletters` (when A#55+A#56 complete and tested)
- **LAST GIT COMMIT**: `1e0c326` — "Fix Bug Z: move forbidden_norms init before PHASE 3C so PHASE 3C rejects flow into Part C"
- **FINAL REVIEW DOC**: `claude_review_final_session14.md` — send this to Claude.AI for final review before merging `Tours_Step_Maps` → `Newsletters`
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
PHASE 2:    _classify_tour_category() → 'walking'/'restaurant'/'museum'/'specialized'
            _pre_category guard suppresses mobile app's hardcoded tour_type:"museum"
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
| `generate_tour_text.py` | `development-tour-generator-1:5000` | `1e0c326` | Sessions 2–10 + A#56 + PHASE 3C improved + coords cluster detection + all Claude review fixes applied |
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

1. **Mobile test — A#56 tour-type icons**: Regenerate a walking tour and a restaurant tour.
   Confirm 🚶 appears on walking, 🍴 on restaurant, 🏛️ on museum. Both EN and translated versions.

2. **ISSUE-059 double map button**: iOS/Android Amazon-Q must remove runtime injection
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
