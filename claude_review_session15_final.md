# Claude.AI Final Review — Session 15 Complete Change Set

**Branch:** `Tours_Step_Maps`
**Base branch:** `Newsletters`
**Merge target:** `Newsletters` (pending this review + mobile test)

**Commits in this review (chronological):**
| Commit | Description |
|--------|-------------|
| `1e9a718` | Fix: venue_name from PHASE 1 forces museum category; remove unconditional classifier override at PHASE 2 (Fairbanks House bug) |
| `2e5eff1` | S15 safety net: `_EXPLICIT_NON_MUSEUM_TOUR_RE` guard + `[S15]` log lines + 4 negative PHASE 1 prompt examples |

**File changed:** `generate_tour_text.py` → container `development-tour-generator-1:5000`

**Previous review doc:** `claude_review_final_session14.md` (13 changes, all reviewed and applied — including Q2 word-set subset check and Q4 `except ValueError` guard)

---

## Background — What Was Broken

**Test input (Android device):**
```
"Fairbanks House Tour in Dedham, ma"
tour_type = "museum"   ← sent by mobile app
total_stops = 4
```

**Expected:** Museum tour — stops are rooms, exhibits, and historical features inside the Fairbanks House (oldest surviving timber-frame house in North America, built 1637).

**Actual (tour ID 288):** Walking tour of Dedham — stops were separate buildings and landmarks around the town.

---

## Root Cause (two compounding issues)

### Issue 1 — Bug2Fix guard suppressed `tour_type="museum"` correctly

The `_pre_category` guard (Session 4) computes category from the location string alone, then suppresses the mobile app's hardcoded `tour_type="museum"` from the PHASE 1 prompt when `_pre_category != 'museum'`.

`"Fairbanks House Tour in Dedham, ma"` contains no museum keywords → `_pre_category = 'walking'` → `tour_type` suppressed.

This is **correct behaviour** — the guard exists to prevent the mobile's hardcoded `tour_type="museum"` from contaminating intent analysis for restaurant/walking tours. It is not the bug.

### Issue 2 — Unconditional `_classify_tour_category()` call at PHASE 2 overwrote the correct result

After PHASE 1, GPT correctly identified `venue_name = "Fairbanks House"` from the location string alone. This is the authoritative signal that the tour is a single-venue museum tour.

However, the old code at PHASE 2 called `_classify_tour_category(location, tour_type)` **unconditionally**, overwriting whatever PHASE 1 established:

```python
# BEFORE (buggy — old line 507):
tour_category = 'intelligent'                                 # dead assignment
tour_category = _classify_tour_category(location, tour_type) # unconditional override
```

`_classify_tour_category` is a keyword matcher. Its museum keyword list:
```python
museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
```

`"Fairbanks House Tour in Dedham, ma"` matches none → returns `'walking'` → `venue_name` signal discarded.

### Why the keyword list cannot be extended to fix this

Adding `'house'`, `'estate'`, `'homestead'` to `museum_keywords` would cause false positives on walking tours:
- `"walking tour near the Old State House, Boston"` → misclassified as museum
- `"Lyman Estate neighborhood walk, Waltham MA"` → misclassified as museum

The correct signal is already available from PHASE 1 GPT analysis. The keyword classifier is a fallback for when PHASE 1 is unavailable.

---

## Commit 1 — `1e9a718`: Core fix

**Change:** Replaced the unconditional `_classify_tour_category()` call with a conditional based on `venue_name`. Removed dead `tour_category = 'intelligent'` assignment.

```python
# AFTER (commit 1e9a718, lines 514–525):

        # If PHASE 1 identified a specific venue AND the location string does not
        # explicitly request a non-museum tour type, force museum category.
        # Safety net (_EXPLICIT_NON_MUSEUM_TOUR_RE) prevents GPT-hallucinated venue_names
        # on "walking tour starting at X" / "restaurant tour near X" requests from
        # silently flipping the category. See S15 Claude review §3.
        if intent.get('venue_name') and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location):
            tour_category = 'museum'
            print(f"  [S15] Forced tour_category=museum from venue_name='{intent['venue_name']}'")
        else:
            if intent.get('venue_name'):
                print(f"  [S15] venue_name='{intent['venue_name']}' overridden — location contains explicit non-museum phrase")
            tour_category = _classify_tour_category(location, tour_type)
    else:
        print("⚠️ Intent analysis failed, using fallback detection")
        intent = None
        tour_category = _classify_tour_category(location, tour_type)

    # PHASE 2: Detect tour type and get appropriate template
    # NOTE: tour_category already set above — do NOT call _classify_tour_category again here
    # (that was the bug: it overwrote the venue_name-based 'museum' decision with 'walking').
    print(f"\nDetected tour category: {tour_category.upper()}")
```

Note: the `_EXPLICIT_NON_MUSEUM_TOUR_RE` reference in commit `1e9a718` was added in commit `2e5eff1` — the two commits are presented together here as the complete change.

---

## Commit 2 — `2e5eff1`: Safety net (from Claude session 15 review)

The first commit introduced a regression risk identified in the Claude review: if GPT hallucinated a `venue_name` for a request like `"Walking tour starting at Faneuil Hall, Boston"`, the `venue_name → museum` override would fire incorrectly, injecting a single-venue museum constraint into a walking tour.

Three sub-changes applied:

### 2a — `_EXPLICIT_NON_MUSEUM_TOUR_RE` at module level (lines 35–44)

```python
# S15 safety net: if the location string explicitly names a non-museum tour type,
# do NOT force museum category on the strength of venue_name alone.
# Prevents GPT-hallucinated venue_names on walking/restaurant requests from
# silently flipping the category and injecting a single-venue museum constraint.
# Word-boundary anchored to avoid false positives ("touring" vs "tour").
_EXPLICIT_NON_MUSEUM_TOUR_RE = re.compile(
    r'\b(walking|restaurant|food|dining|culinary|self[- ]guided|architecture|architectural)'
    r'\s+tour\b',
    re.IGNORECASE,
)
```

**How it works:** If the location string contains an explicit non-museum tour phrase (e.g. `"walking tour"`, `"restaurant tour"`, `"food tour"`), the `venue_name → museum` override is blocked regardless of what GPT returned for `venue_name`. The classifier runs as normal fallback.

**Word-boundary anchoring:** `\b...\b` prevents `"touring"` from matching `"tour"`. The `self[- ]guided` alternation handles both `"self-guided tour"` and `"self guided tour"`.

### 2b — `[S15]` log lines in both branches (lines 519–524)

Both the override path and the safety-net path now log to container output:

```python
if intent.get('venue_name') and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location):
    tour_category = 'museum'
    print(f"  [S15] Forced tour_category=museum from venue_name='{intent['venue_name']}'")
else:
    if intent.get('venue_name'):
        print(f"  [S15] venue_name='{intent['venue_name']}' overridden — location contains explicit non-museum phrase")
    tour_category = _classify_tour_category(location, tour_type)
```

**Operational value:** Makes the next "why was tour X classified as Y?" question answerable from container logs in seconds. The safety-net log line is particularly useful — it confirms both that GPT returned a `venue_name` for an edge case AND that the safety net caught it.

### 2c — 4 negative examples in PHASE 1 prompt (lines 112–115)

Added to the `analyze_tour_intent()` examples block:

```
- "Walking tour starting at Faneuil Hall, Boston" → poi_type: "landmarks", theme_type: "STANDARD", venue_name: null
- "Restaurant tour near the Prudential Center, Boston" → poi_type: "restaurants", theme_type: "STANDARD", venue_name: null
- "Architecture tour around the Lyman Estate" → poi_type: "buildings", theme_type: "STANDARD", venue_name: null
- "Self-guided tour of Beacon Hill" → poi_type: "landmarks", theme_type: "STANDARD", venue_name: null
```

**Purpose:** Teaches GPT to return `venue_name: null` for `"tour starting at / near / around / of"` patterns. Belt-and-braces alongside the regex safety net — reduces the frequency of cases where the safety net needs to fire.

---

## Downstream Pipeline Impact

The fix affects PHASE 2 only. All downstream phases are unchanged:

| Phase | Behaviour when `venue_name` set (unchanged) |
|-------|---------------------------------------------|
| PHASE 3A | Museum constraint injected: `"All stops MUST be inside '{venue_name}'"` |
| PHASE 4 | Skipped for `tour_category == 'museum'` |
| PHASE 3C | Skipped for single-venue museum (`_museum_venue_name` set) |
| PHASE 5.5b | `_validate_museum_stop_descriptions()` runs — validates stops are inside venue |
| PHASE 6 | `Tour-Category: museum` written → 🏛️ icon in mobile app |
| Coordinates | First stop only (all exhibits in same building) |

---

## Regression Analysis

| Scenario | Before fix | After fix |
|----------|-----------|-----------|
| `"Fairbanks House Tour in Dedham, ma"` | ❌ walking (classifier overrides venue_name) | ✅ museum (venue_name authoritative) |
| `"Walking tour in Newton, MA"` | ✅ walking | ✅ walking (no venue_name from GPT) |
| `"Restaurant tour in Newton Center"` | ✅ restaurant | ✅ restaurant (no venue_name from GPT) |
| `"Jackson Homestead and Museum Newton, MA"` | ✅ museum (keyword match) | ✅ museum (venue_name + keyword both agree) |
| `"Tour inside the MFA Boston"` | ✅ museum (keyword match) | ✅ museum (venue_name + keyword both agree) |
| `"Walking tour starting at Faneuil Hall"` | ✅ walking (no venue_name in old code) | ✅ walking (safety net blocks override even if GPT returns venue_name) |
| `"Restaurant tour near the Prudential Center"` | ✅ restaurant | ✅ restaurant (safety net blocks override) |
| PHASE 1 failure (`intent = None`) | ✅ classifier runs | ✅ classifier runs (else branch unchanged) |
| `_venue_matches_location` discards venue_name | ✅ classifier runs | ✅ classifier runs (`intent.get('venue_name')` returns None) |

---

## Test Matrix for Mobile Validation

| Test | Input | Expected log line | Expected result |
|------|-------|-------------------|-----------------|
| Happy path — historic house | `"Fairbanks House Tour in Dedham, ma"` | `[S15] Forced tour_category=museum from venue_name='Fairbanks House'` | Museum tour, stops inside Fairbanks House, 🏛️ icon |
| Safety net fires | `"Walking tour starting at Faneuil Hall, Boston"` | `[S15] venue_name='Faneuil Hall' overridden — location contains explicit non-museum phrase` | Walking tour of Boston landmarks |
| No venue_name (normal walking) | `"Walking tour in Newton Center, MA"` | No `[S15]` line | Walking tour, 🚶 icon |
| No venue_name (restaurant) | `"Restaurant tour in Newton, MA"` | No `[S15]` line | Restaurant tour, 🍴 icon |

---

## Questions for Claude

**Q1 — `_EXPLICIT_NON_MUSEUM_TOUR_RE` keyword coverage: is the list complete enough?**

Current keywords: `walking`, `restaurant`, `food`, `dining`, `culinary`, `self-guided`, `architecture`, `architectural`.

Missing candidates that could also produce a GPT `venue_name` hallucination:
- `"pub crawl tour near the Old South Meeting House"` — no `pub crawl` in the list
- `"ghost tour starting at the Omni Parker House"` — no `ghost` in the list
- `"bike tour around the Lyman Estate"` — no `bike` in the list
- `"shopping tour near Faneuil Hall Marketplace"` — no `shopping` in the list

Should the list be expanded now, or is the current set sufficient for the known failure cases and the PHASE 1 prompt negative examples cover the rest? Is there a risk that over-expanding the list causes false negatives (legitimate single-venue tours that happen to mention a tour type in their location string)?

**Q2 — Interaction between `_venue_matches_location` sanity check and the safety net**

The `_venue_matches_location` sanity check (Session 10) discards `venue_name` if it has no word overlap with the location string. The safety net (`_EXPLICIT_NON_MUSEUM_TOUR_RE`) blocks the override if the location contains an explicit non-museum phrase.

These are two independent guards. Is there a case where they interact badly? Specifically:

- Location: `"Walking tour of the Fairbanks House, Dedham MA"` (user explicitly says "walking tour" but also names the venue)
- `_venue_matches_location("Fairbanks House", "Walking tour of the Fairbanks House, Dedham MA")` → `True` (word overlap: "fairbanks", "house")
- `_EXPLICIT_NON_MUSEUM_TOUR_RE.search("Walking tour of the Fairbanks House, Dedham MA")` → matches `"Walking tour"`
- Result: safety net fires → `tour_category = 'walking'`

Is this the correct result? The user said "walking tour" but named a specific historic house. Should the safety net yield to `venue_name` when the venue name has strong word overlap with the location? Or is "walking tour of X" always a walking tour regardless of what X is?

**Q3 — `max_tokens=400` for PHASE 1 with 16 examples: is it still sufficient?**

The PHASE 1 prompt now has 16 examples (was 10 before S15b). The `max_tokens=400` limit was set in Session 5 (increased from 200). The response JSON has 8 fields. With 16 examples in the prompt, does the increased prompt length affect the quality or completeness of the JSON response? Should `max_tokens` be increased to 500 to give GPT more room?

---

## Complete S15 Change Summary

| # | Commit | What | Why |
|---|--------|------|-----|
| S15a | `1e9a718` | `tour_category = 'museum' if venue_name and not safety_net else classifier` at PHASE 2; removed dead `tour_category = 'intelligent'` | Keyword classifier cannot detect historic houses/estates; PHASE 1 GPT intent is authoritative when `venue_name` returned |
| S15b-1 | `2e5eff1` | `_EXPLICIT_NON_MUSEUM_TOUR_RE` module-level constant | Prevents GPT-hallucinated `venue_name` on walking/restaurant requests from silently flipping category to museum |
| S15b-2 | `2e5eff1` | `[S15]` log lines in both override and safety-net branches | Operational observability — makes category decision visible in container logs |
| S15b-3 | `2e5eff1` | 4 negative examples in PHASE 1 prompt | Teaches GPT to return `venue_name: null` for `"tour starting at / near / around"` patterns |
