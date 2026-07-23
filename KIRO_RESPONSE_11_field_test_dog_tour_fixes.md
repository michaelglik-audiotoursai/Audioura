# KIRO_RESPONSE_11_field_test_dog_tour_fixes.md — Execution Report

**Author:** Kiro (Mac Mini CLI)  
**Date:** 2026-07-22  
**In response to:** `KIRO_REVIEW_11_field_test_dog_tour_fixes.md`  
**Status:** All 8 issues addressed. Dog tour generates with correct title, category, stops_count, no museum register, no duplicate orientation.

---

## Issue 1 — stops_count persistence ✅

**Changes:**
- `tour_orchestrator_service.py:304`: Added `stops_count=None` parameter to `store_audio_tour()`
- `tour_orchestrator_service.py:478`: Added `stops_count` to INSERT columns/values
- `tour_orchestrator_service.py:823`: Passed `stops_count=ACTIVE_JOBS[job_id].get("actual_stops")` to call

**Verification:**
```sql
SELECT id, tour_name, stops_count FROM audio_tours ORDER BY id DESC LIMIT 1;
 id |                     tour_name                      | stops_count
----+----------------------------------------------------+-------------
  8 | dog ridding tour, Big Lake, AK - Dog Sledding Tour |           2
```

**Out of scope (noted):** iPhone app saves requested count. Server now returns `actual_stops` in status — app should prefer it (separate ticket).

---

## Issue 2 — "dog" not recognized as animal transport ✅

**Change:** `generate_tour_text.py:65`:
```python
'animal': re.compile(r'\b(camel(?:back)?|horse(?:back)?|dog|dogsled(?:ding)?|sled\s*dog|mushing|husky)\b(?:\s+\w+)?\s*tour\b', re.IGNORECASE),
```

**Verification:** `[TRANSPORT] mode=animal, country_scope=None (keyword=animal, intent=animal)`

---

## Issue 3 — Title reflects transport mode ✅

**Change:** `generate_tour_text.py:~3311-3335`: Added `_TRANSPORT_DISPLAY_NAMES` and `_ANIMAL_DISPLAY_NAMES` dicts. For animal mode, looks up matched keyword to derive specific name (Dog Sledding, Camelback, Horseback).

**Verification:** `Step-by-Step Audio Guided Tour: dog ridding tour, Big Lake, AK - Dog Sledding Tour`

---

## Issue 4 — DB tour_name uses effective category ✅

**Change:** `tour_orchestrator_service.py:~770-787`: Parse ` - <X> Tour` suffix from generated content's first line (read from `tour_file`). Fall back to raw `tour_type` only if content unavailable.

**Verification:** DB row shows "Dog Sledding Tour" not "museum Tour".

---

## Issue 5 — LLM fallback for unknown transport modes ✅

**Changes:**
1. Broadened intent prompt transport_mode description: `animal (ANY animal-powered: camel, horseback, dog sled, elephant, donkey, husky, etc.)`
2. Added examples: dog sledding, robot riding, segway
3. Added guardrail regex: logs `[TRANSPORT] UNRECOGNIZED MODE CANDIDATE: '<word>'` when a `<word> riding/sledding/drawn tour` pattern matches but keyword table returns `on_foot`

---

## Issue 6 — Museum narrative register removed from non-museum tours ✅

**Change:** `generate_tour_text.py:~2991-3015`: Gated the existing museum expansion prompt on `if tour_category == 'museum'`. Added a new non-museum prompt that:
- Uses outdoor/location framing (no "exhibit", "viewing platform", "artwork")
- Explicitly prohibits museum framing
- Prohibits inventing named people

**Verification:** `grep -ic "exhibit\|museum\|viewing platform\|artwork" tour_content.txt` → **0**

---

## Issue 7 — Duplicate "Orientation:" fixed ✅

**Change:** `generate_tour_text.py:~3529-3555`: Replaced the double-prefix pattern. Now strips any leading `Orientation:` from LLM output (`re.sub(r'^Orientation:\s*', '', ...)`) before prepending the single controlled prefix.

**Verification:** `grep -c "Orientation:" tour_content.txt` → **2** (one per stop, exactly)

---

## Issue 8 — Grounding quality improvements ✅

**8.1 (Fabricated people):** Non-museum prompt explicitly says "Do NOT invent specific named people or attribute quotes unless they are well-documented public figures associated with this location."

**8.2 (Wrong coordinates for real venue):** Noted as known limitation — no fix in this pass. Would require canonical location cross-check infrastructure.

**8.3 (Walking directions for 30km legs):** `generate_tour_text.py:~2509`: Directions prompt now uses transport-mode-appropriate language:
```python
f"{'turn-by-turn walking directions' if transport_mode == 'on_foot' else f'route directions suitable for {transport_mode} travel'}"
```

---

## Test results

```
python3 test_sq4_merge.py           → ALL TESTS PASSED ✅
python3 test_palais_fix_lead_fixture.py → All tests passed ✅
```

**Generated dog tour verification:**
- Title: "Dog Sledding Tour" ✅
- Category: walking (with transport_mode=animal) ✅
- DB stops_count: 2 (matches ZIP contents) ✅
- Museum register words: 0 ✅
- Orientation duplicates: none (2 total, one per stop) ✅
- Keyword detection: `keyword=animal` (not relying on LLM fallback) ✅

---

## Files changed

| File | Issues addressed |
|------|-----------------|
| `generate_tour_text.py` | 2, 3, 5, 6, 7, 8.1, 8.3 |
| `tour_orchestrator_service.py` | 1, 4 |

---

## Awaiting

Claude's review. Changes are in working tree (not committed per instructions).


---

## Addendum — Two follow-ups from review verdict (2026-07-22 21:44)

### Follow-up 1: UPDATE path stops_count ✅

**Change:** `tour_orchestrator_service.py:~445,455`: Added `stops_count = %s` to both UPDATE branches in `store_audio_tour()`.

### Follow-up 2: Translation inheritance of stops_count ✅

**Changes:**
- `translation-service/translation_service.py:173`: Added `stops_count` (index 10) to the original tour SELECT
- `translation-service/translation_service.py:278`: Added `stops_count` to the primary translation INSERT, inheriting from `original_tour[10]`
- `translation-service/translation_service.py:1590`: Same for the fallback ZIP translation path

**Verification:**
```sql
SELECT id, tour_name, stops_count FROM audio_tours WHERE id IN (8, 9);
 id |                                    tour_name                                    | stops_count
----+---------------------------------------------------------------------------------+-------------
  8 | dog ridding tour, Big Lake, AK - Dog Sledding Tour                              |           2
  9 | тур на собачьих упряжках, Большое озеро, штат Аляска - тур на собачьих упряжках |           2
```

Both original (8) and translated (9) tours have `stops_count = 2`. Russian tour name contains no museum wording.

---

**Files changed (addendum):**
- `tour_orchestrator_service.py` — 2 UPDATE statements
- `translation-service/translation_service.py` — 1 SELECT + 2 INSERTs
