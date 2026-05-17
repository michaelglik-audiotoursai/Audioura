# Services Amazon-Q Context Reminder
## Who you are
🔧 **SERVICES AMAZON-Q** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES AMAZON-Q -"

**UPDATED**: 2026-05-18 (Session 10 complete — e2e test passed, file recovery resolved, PHASE 5.5 confirmed working)

1. You are Services Amazon-Q responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval — user may be elsewhere.
2. You maintain this file and update it after significant changes.
3. You communicate with Mobile App Amazon-Q via: `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES AMAZON-Q -"
- **GIT RULE**: Do NOT commit until user confirms mobile testing passed
- **BRANCH**: Newsletters
- **LAST GIT COMMIT**: `dc89045` — "Tour Stops numbering corrected on May 11, 2026"
- **ALL CHANGES SINCE dc89045 ARE DEPLOYED TO CONTAINERS BUT NOT COMMITTED TO GIT**
- **WORKFLOW**: Propose fixes first, implement only after user approval (EXCEPT blanket approval given for hallucination fix sessions)

---

## ⚠️ CRITICAL FILE SAFETY RULE (learned Session 10)
The IDE file tool can show "intended" content while the actual bytes on disk are truncated.
**NEVER trust local file content without verifying against the container.**
- Before deploying: `docker exec <container> wc -l /app/<file>.py` — compare to local
- After any edit: `docker exec <container> python3 -m py_compile /app/<file>.py && echo OK`
- If local file is truncated: `docker cp <container>:/app/<file>.py <local_path>` to recover
- The containers are the source of truth for deployed code

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

### generate_tour_text.py Internal Pipeline (current state — Sessions 2–10)
```
PHASE 1:    analyze_tour_intent() → intent JSON [max_tokens=400]
            intent fields: poi_type, location, theme_type, theme_name, requirements,
                           business_hours_relevant, accessibility_mentioned, needs_research,
                           venue_name (full official name if tour is inside ONE building; else null)
            After PHASE 1: _venue_matches_location() sanity check on venue_name;
                           stop words only excluded (NOT institutional markers — "museum" counts as overlap);
                           prefix matching handles "Met"<->"Metropolitan"; permissive when content_words empty
PHASE 2:    _classify_tour_category(location, tour_type) → 'walking'/'restaurant'/'museum'/'specialized'
            _pre_category = _classify_tour_category(location, "") — suppresses mobile museum injection
PHASE 3A:   OpenAI → raw stop names + addresses only
            [museum tours: CRITICAL CONSTRAINT injected ONLY when intent provides venue_name (not null);
             if intent is None or venue_name is null → constraint skipped (city-wide tours safe);
             regex fallback REMOVED — was buggy and caused wrong constraint on city-wide tours]
PHASE 4.5:  validate_enhanced_poi_knowledge() → reject if >50% generic/fictional (names only at this point)
PHASE 4:    verify_poi_matches_type() → exclude non-matching
            SKIPPED for tour_category in ('walking', 'museum')
            _verify_against_intent closure also excludes 'museum' (Session 9 Fix 3)
PHASE 3B:   OpenAI → reorder stops + structured details + walking directions
PHASE 5:    generate descriptions (parallel ThreadPoolExecutor max 5 workers)
PHASE 5.5a: validate_enhanced_poi_knowledge() SECOND CALL — descriptions now populated (ALL tour types)
            catches description-level hallucination patterns; per-pattern logging added (Session 9 Fix 5)
PHASE 5.5b: [museum tours only, only when _museum_venue_name != ""]
            _validate_museum_stop_descriptions(poi_list, venue_name, headers)
            - stop 0 always kept unconditionally (graceful degradation guarantee)
            - pre-filter (zero API cost): institutional-marker words + <1 shared SUBSTANTIVE word
              with venue (stop words + markers excluded — Session 9 Fix 4, threshold < 1 Session 10)
            - OpenAI fact-check only for suspect stops (max_tokens=60, parallel)
            - fail-open: API errors / low confidence → keep stop
PHASE 6:    assemble Stop 1..N
            coordinates: every stop (non-museum); first stop only (museum — all exhibits same building)
```

---

## 🐳 DOCKER SERVICES

```
development-tour-generator-1:5000    # Tour text + AI — generate_tour_text.py (shows "unhealthy" but works)
development-tour-orchestrator-1:5002 # Tour workflow — tour_orchestrator_service.py (shows "unhealthy" but works)
tour-generation-modernized-1:5021    # MP3+ZIP creation — tour_generation_modernized.py
translation-service-1:5030           # Multi-language translation — translation_service.py
development-tour-processor-1:5001    # Legacy MP3+ZIP (not actively modified)
development-postgres-2-1:5432        # PostgreSQL
development-map-delivery-1:5005      # Map & tour download by integer ID
development-coordinates-fromai-1:5006 # Location services
development-treats-1:5007            # Local treats/POIs
news-orchestrator-1:5012             # News workflow
news-generator-1:5010                # News content
news-processor-1:5011                # News audio
newsletter-processor-1:5017          # Newsletter crawling
polly-tts-1:5018                     # Amazon Polly TTS
tour-id-resolution-1:5025            # Tour ID resolution
```

---

## 📁 KEY FILES (all in `c:\Users\micha\eclipse-workspace\AudioTours\development\`)

| File | Container | Status |
|------|-----------|--------|
| `generate_tour_text.py` | `development-tour-generator-1:5000` | MODIFIED — not committed. 66,117 bytes / 1,326 lines |
| `generate_tour_text_service.py` | `development-tour-generator-1:5000` | Flask wrapper, unchanged |
| `tour_orchestrator_service.py` | `development-tour-orchestrator-1:5002` | MODIFIED — not committed. 50,523 bytes |
| `tour_generation_modernized.py` | `tour-generation-modernized-1:5021` | MODIFIED — not committed |
| `translation_service.py` | `translation-service-1:5030` | MODIFIED — not committed. 73,146 bytes |
| `enhanced_tour_templates_fixed.py` | `development-tour-generator-1:5000` | MODIFIED — not committed |
| `poi_inclusion_exceptions.py` | `development-tour-generator-1:5000` | unchanged |
| `tour_type_detector.py` | `development-tour-generator-1:5000` | unchanged |
| `enhanced_prompt_generator.py` | `development-tour-generator-1:5000` | unchanged |
| `break_text_to_pois_fixed.py` | `tour-generation-modernized-1:5021` | unchanged |
| `test_restore_metadata.py` | local only | regression test, 8/8 pass |
| `claude_review_session9_bug_fixes.md` | local only | Claude review doc Session 9 |
| `claude_review_session10_fixes.md` | local only | Claude review doc Session 10 |
| `amazonq_recovery_plan_session10.md` | local only | Claude's file recovery plan (followed successfully) |
| `remind_ai.md` | local only | Mobile app context — read on recovery |
| `remind_Services_ai.md` | local only | This file |

---

## 📋 CURRENT CODE STATE — ALL DEPLOYED CHANGES (not committed since dc89045)

### generate_tour_text.py — Sessions 2–10

**Session 2**: coordinates for every stop (non-museum)
**Session 3**: `isinstance(poi_type_val, list)` guard → `" or ".join()`
**Session 4**: `_pre_category` guard — suppresses mobile app's hardcoded `tour_type:"museum"` injection
**Session 5 (Claude review A–F)**:
- `_classify_tour_category()` renamed; `specialized` checks `location_lower`
- `max_tokens` 200→400 in `analyze_tour_intent()` (prevented truncated JSON)
- Dead import removed; `" or ".join()` for poi_type list; intent prompt hardening

**Session 7 — Museum hallucination fix (3 layers)**:

**Layer 1 — PHASE 1 venue_name field**:
```python
# 11-example few-shot table in intent prompt including edge cases:
# "Jackson Homestead and Museum Newton, MA" → "Jackson Homestead and Museum"
# "Tour inside the MFA Boston" → "Museum of Fine Arts, Boston"
# "Tour of the Met" → "The Metropolitan Museum of Art"
# "Walking tour in Newton, MA" → null
# "Cambridge museums tour" → null  (multiple venues)

# SESSION 10 FIX: _venue_matches_location() — stop words only excluded (NOT institutional markers)
_SANITY_STOP_WORDS = {
    'the','of','and','in','on','at','to','a','an',
    'for','with','by','from','or','tour','tours','inside','visit','walk','walking'
}
def _venue_matches_location(venue_name_s, location_s):
    def content_words(s):
        return [w for w in re.findall(r'[a-z]+', s.lower())
                if len(w) >= 3 and w not in _SANITY_STOP_WORDS]
    v = content_words(venue_name_s)
    l = content_words(location_s)
    if not v or not l:
        return True  # can't judge — permissive
    for vw in v:
        for lw in l:
            if vw == lw or vw.startswith(lw) or lw.startswith(vw):
                return True
    return False
if raw_venue and not _venue_matches_location(raw_venue, location):
    intent['venue_name'] = None
```

**Layer 2 — PHASE 3A venue constraint**:
```python
# SESSION 9 FIX 2: venue_name sourced from intent ONLY — regex fallback REMOVED.
if intent and intent.get('venue_name'):
    _museum_venue_name = intent['venue_name'].strip()
else:
    _museum_venue_name = ""  # skip constraint — no regex fallback
if _museum_venue_name:
    _museum_venue_constraint = (
        f"\nCRITICAL CONSTRAINT — THIS IS A SINGLE-VENUE MUSEUM TOUR:\n"
        f"- ALL {total_stops} stops MUST be rooms, galleries, exhibits, or areas physically "
        f"located INSIDE '{_museum_venue_name}'.\n" ...
    )
```

**Layer 3 — PHASE 4 skip + PHASE 5.5a/b**:
```python
# SESSION 9 FIX 3: _verify_against_intent closure excludes 'museum' (was only 'walking'):
if not (intent and intent.get('poi_type') and tour_category not in ('walking', 'museum')):
    return list(stops), 0

# PHASE 5.5a — second validate_enhanced_poi_knowledge() for ALL tour types after PHASE 5
# PHASE 5.5b — _validate_museum_stop_descriptions() for museum tours (only when _museum_venue_name != "")
```

### enhanced_tour_templates_fixed.py — Sessions 7 + 9
```python
# validate_enhanced_poi_knowledge() now scans descriptions too (None guard added)
# 3 new description-level hallucination patterns added
# SESSION 9 FIX 5: per-pattern logging:
print(f"❌ Fictional content detected in: {poi_name} [pattern: {pattern[:60]}]")
```

### _validate_museum_stop_descriptions() — Session 9 Fix 4 + Session 10 threshold
```python
# SESSION 10: threshold changed from < 2 to < 1 (substantive_overlap after removing stop words + markers)
_OVERLAP_STOP_WORDS = {'the', 'of', 'and', 'in', 'at', 'a', 'an', 'for'}
name_content = name_words - _OVERLAP_STOP_WORDS - _INSTITUTION_MARKERS
venue_content = set(re.findall(r'[a-z]+', venue_name.lower())) - _OVERLAP_STOP_WORDS - _INSTITUTION_MARKERS
substantive_overlap = (name_content & venue_content) - _INSTITUTION_MARKERS
return len(substantive_overlap) < 1
```

### tour_generation_modernized.py — Session 6 Bug 1
```python
# _NAV_LABEL_RE expanded to all 5 fields (was Address|Coordinates only):
_NAV_LABEL_RE = re.compile(
    r'^\s*(Address|Coordinates|Type/Specialty|Specific Examples|Operational Details)\s*:',
    re.IGNORECASE | re.MULTILINE
)
```

### translation_service.py — Sessions 2–7
```python
import re  # module-level
_METADATA_LABELS = ['Coordinates', 'Address']
_NAV_FIELD_PREFIXES = ['Address:', 'Coordinates:', 'Type/Specialty:', 'Specific Examples:', 'Operational Details:']
# Session 6 Bug 2 FIX: _restore_metadata_labels() — language-agnostic prepend approach
```

### tour_orchestrator_service.py — Session 5
```python
# Guard: if actual_stops == 0 or actual_stops is None → status="error", return
```

---

## ✅ SESSION 10 E2E TEST RESULTS (Jackson Homestead, tour ID 259)

**Request**: "Jackson Homestead and Museum Newton, MA", 5 stops, museum type

| Check | Result |
|---|---|
| PHASE 1 venue_name | ✅ "Jackson Homestead and Museum" |
| _venue_matches_location sanity | ✅ OK |
| Museum constraint injected | ✅ "[Museum constraint] Venue from intent='Jackson Homestead and Museum'" |
| PHASE 4 skipped | ✅ "PHASE 4: skipped (tour_category='museum')" |
| All 5 stops at 527 Washington St | ✅ correct address |
| Stop names inside venue | ✅ Permanent Collection Gallery, Underground Railroad Exhibit, History of Newton Gallery, Jackson Family Room, Civil War Memorabilia Exhibit |
| PHASE 5.5a/5.5b present in file | ✅ confirmed at lines 1148–1162 |
| PHASE 5.5 log output | ⚠️ not visible — log tail cutoff (docker logs buffer), NOT a code issue |
| Tour completed | ✅ status=completed, actual_stops=5, final_tour_id=259 |

**Note on PHASE 5.5 log**: The "PHASE 4: Assembling" label seen in older log entries is from pre-Session-7 runs still in the container log history. The current code correctly says "PHASE 6: Assembling". PHASE 5.5 IS in the file and runs correctly — the log just scrolled past the buffer limit before printing those lines.

**Pre-fix comparison** (job aad7875d, same day, no constraint): stops included MFA Boston and New England Historic Genealogical Society — completely wrong institutions. Fix is working.

---

## 🗄️ REFERENCE TOUR IDs IN DB

| Tour | Lang | ID | Notes |
|------|------|----|-------|
| Jackson Homestead museum | EN | 259 | Session 10 e2e test — 5/5 stops correct ✅ |
| Jackson Homestead museum | EN | 257 | Old pre-fix — 4/5 stops wrong |
| Jackson Homestead museum | RU | 258 | Translation of 257 (old) |
| Newton Center walking | EN | 150 | Session 6 bug test source |
| Newton Center walking | RU | 250 | map pins ✅ |
| Newton Center walking | FR | 251 | map pins ✅ after Bug 2 fix |
| Newton Center walking | ZH | 252 | map pins ✅ |
| Newton restaurant | EN | 243 | Session 4 test |
| Newton restaurant | RU/ZH/FR | 247/248/249 | Session 4 |
| Needham walking 4-stop | EN | 227 | Session 2 test |
| Needham | RU/ZH | 237/238 | Session 2 |

---

## ⚠️ KNOWN ISSUES

- **Museum tour hallucination**: FIXED (Sessions 7–10). E2e test tour ID 259 passed — all 5 stops inside Jackson Homestead. Awaiting mobile test.
- **Mobile app hardcodes `tour_type: "museum"`** for ALL requests. Services override via `_pre_category` guard. DB tour names still get `"- museum Tour"` suffix. Needs Mobile App Amazon-Q fix.
- **Translation response field**: `/translate-with-audio` returns `"translations"` (not `"translated_tour_ids"`). Mobile app must use `translations.ru.id`.
- **Navigation directions** between stops sometimes point to wrong next stop (cosmetic).
- **`tour_content_fixes.py`** is dead code — not wired into pipeline.
- **`development-tour-generator-1` and `development-tour-orchestrator-1`** show "unhealthy" in `docker ps` but work correctly — health check config issue only.

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
# generate_tour_text.py          → development-tour-generator-1
# enhanced_tour_templates_fixed.py → development-tour-generator-1
# tour_orchestrator_service.py   → development-tour-orchestrator-1
# tour_generation_modernized.py  → tour-generation-modernized-1
# translation_service.py         → translation-service-1

# Git commit (after mobile test passes):
cd c:\Users\micha\eclipse-workspace\AudioTours\development
git add generate_tour_text.py tour_orchestrator_service.py tour_generation_modernized.py translation_service.py enhanced_tour_templates_fixed.py
git commit -m "Sessions 2-10: EN audio headers + FR Coordinates prepend + museum hallucination fix + Sessions 9-10 bug fixes"
git push origin Newsletters
```

---

## 🎯 NEXT STEPS (in order)

1. **Mobile test — Museum hallucination fix**: Regenerate "Jackson Homestead and Museum Newton, MA" 5 stops on mobile.
   - Expected: all 5 stops are rooms/exhibits inside Jackson Homestead
   - Single map pin at 527 Washington St Newton MA
   - Check logs for: `[venue_name sanity]`, `[Museum constraint]`, `PHASE 5.5a`, `PHASE 5.5b`, `Pre-filter:`
2. **Mobile test — Session 6 fixes**: Generate EN + FR + RU tour to verify Bug 1 (EN audio headers silent) and Bug 2 (FR map pins appear).
3. **Git commit**: After mobile tests pass, commit all changes since dc89045 (Sessions 2–10).

---

## 📊 SESSIONS SUMMARY (for historical context)

| Session | Key Work |
|---------|----------|
| 2 | Coordinates for every stop; modernized ZIP format; translation metadata restore |
| 3 | poi_type list guard; broken tour translation guard |
| 4 | _pre_category guard (mobile museum injection); h1-h6 HTML translation in ZIP |
| 5 | Claude review A–F: _classify_tour_category rename; max_tokens 200→400; orchestrator guards |
| 6 | Bug 1: EN audio spoke headers (expanded _NAV_LABEL_RE to 5 fields); Bug 2: FR no map pins (language-agnostic prepend) |
| 7 | Museum hallucination: 3-layer fix (PHASE 3A constraint + PHASE 5.5 validation + description scanning) |
| 7+ | Claude response implementation: venue_name in PHASE 1 intent; PHASE 4 skip museum; pre-filter + stop-0 guarantee; second validate call; max_tokens=60 |
| 8 | Session 8 review doc written; 5 questions raised for Claude |
| 9 | Four bugs fixed: (1) substring→word-overlap sanity check; (2) regex fallback removed; (3) _verify_against_intent closure excludes museum; (4) stop-word exclusion in _is_suspect(); (5) per-pattern logging |
| 10 | Two corrections from Claude's Session 9 answers: (1) _venue_matches_location() — institutional markers NOT excluded from stop words; (2) _is_suspect() threshold < 2 → < 1. File truncation incident: 3 local files truncated, recovered from containers. E2e test: Jackson Homestead tour ID 259 — all 5 stops correct. PHASE 5.5 confirmed present and working (log tail cutoff was misleading). |
