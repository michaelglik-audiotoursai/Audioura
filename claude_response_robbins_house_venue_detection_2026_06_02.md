# Claude Review & Fix — Robbins House Scope-Containment Failure
**Date:** 2026-06-02
**Reviewing:** `claude_review_robbins_house_venue_detection_2026_06_02.md` (Kiro)
**Request under test:** "tour in Robbin's House and Monument Square museum in Concord, MA" — 8 POIs, Russian
**File:** `generate_tour_text.py`
**Verdict:** Kiro's *mechanism* is correct. Kiro's *framing* — "intent-analysis limitation / prompt engineering / user education, not a code bug" — undersells a concrete, fixable defect: the pipeline **injects a scope constraint and then never enforces it.** That is a code bug, and it is fixable with a post-generation containment check modeled on a guard that already exists in this file.

---

## 1. What actually happened (confirmed in code)

For this request the intent analysis returned `venue_name: null`, `geographic_scope: "Robbin's House and Monument Square museum"`, `scope_precision: "DISTRICT"`. Three guards could have caught the out-of-scope stops; none did:

1. **Museum containment guard (PHASE 5.5b, line 1472).** Runs only when `tour_category == 'museum' and _museum_venue_name`. `venue_name` was null → **did not fire.**
2. **S17 scope constraint (lines 736-747).** Because `scope_precision == 'DISTRICT'`, the constraint text **was** injected: *"GEOGRAPHIC SCOPE — ALL stops MUST be located within: Robbin's House and Monument Square museum… if it is outside, it does not belong."* But this is only a **prompt instruction**. GPT ignored it and produced Walden Pond, The Old Manse, etc. **Nothing validates that the instruction was obeyed.**
3. **GEO-CHECK (lines 1200-1300).** This only enforces **walking-distance compactness** via haversine outlier removal. Walden Pond, The Old Manse, and Monument Square are all within a few km of each other in Concord, so they pass the compactness test. GEO-CHECK checks *"are the stops close together?"* — never *"are the stops inside the named place?"*

So the failure is not merely that intent analysis mis-read the venue. The deeper defect is that **the system asked GPT to stay inside a named scope, GPT didn't, and no stage checked.** Intent analysis will always be imperfect; the missing enforcement layer is the real bug.

---

## 2. Why I push back on "not a code bug / user education"

Kiro's Q3 suggests the user could just request "Robbins House museum, Concord, MA" without the "and." True — but that makes correctness depend on perfect phrasing, and the system already *claims* to honor scope (it injects the S17 constraint). A constraint that is stated but unenforced is worse than no constraint: it looks handled and silently isn't. The same class of gap produced the earlier "Thoreau's Bedroom" miss. The robust answer in both cases is the same: **verify, after generation, that stops are actually inside the requested bound** — exactly the post-generation check Kiro floats in Q4 and then doesn't commit to. I recommend committing to it.

---

## 3. Primary fix — PHASE 5.6: geographic-scope containment guard

Add a containment validator that runs whenever the request is bounded to a tight named place but the museum guard did **not** run. It mirrors the existing `_validate_museum_stop_descriptions` (PHASE 5.5b), with one deliberate difference: it checks **every** stop, not just institution-named ones — because out-of-scope landmarks ("Walden Pond", "The Old Manse") carry no institutional marker and would slip through a name-based pre-filter (the same blind spot that let "Thoreau's Bedroom" through).

### New function (place next to `_validate_museum_stop_descriptions`, ~line 438)

```python
def _validate_stops_within_scope(poi_list, scope_name, headers, max_check=12):
    """
    PHASE 5.6 — Geographic-scope containment guard.

    Runs when the request is bounded to a tight named place (a single venue OR a
    BUILDING/DISTRICT-precision scope) but no museum venue_name was detected, so the
    PHASE 5.5b museum guard did not fire. Verifies every generated stop is actually
    located WITHIN scope_name and removes famous-but-out-of-scope landmarks
    (e.g. "Walden Pond" for a "Robbins House" request).

    Unlike the museum guard, this checks EVERY stop (no institution-marker pre-filter),
    because out-of-scope landmarks usually have no institutional marker in their names.

    Stop 0 is kept unconditionally (graceful degradation). Original order preserved.
    """
    if not poi_list or not scope_name:
        return poi_list

    def _check_one(poi):
        name = poi.get('name', '')
        desc = (poi.get('description', '') or '')[:400]
        prompt = (
            f"You are a geography fact-checker for location tours.\n"
            f"The tour must stay strictly within: '{scope_name}'.\n"
            f"Stop name: '{name}'\n"
            f"Description snippet:\n{desc}\n\n"
            f"Question: Is this stop physically located INSIDE or within the bounds of "
            f"'{scope_name}'? A stop that is in the same town but OUTSIDE '{scope_name}' "
            f"is NOT inside.\n"
            "Respond ONLY with valid JSON:\n"
            '{"inside_scope": true/false, "confidence": "high/medium/low", "reason": "<brief>"}'
        )
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a geography fact-checker. Respond only with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 60,
        }
        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, data=json.dumps(data))
            if resp.status_code != 200:
                return poi, True, "low", f"API error {resp.status_code} — keeping"
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
            return (poi, parsed.get("inside_scope", True),
                    parsed.get("confidence", "low"), parsed.get("reason", ""))
        except Exception as e:
            return poi, True, "low", f"check error: {e}"

    first_stop = poi_list[0]
    candidates = poi_list[1:1 + max_check]   # cost cap
    tail = poi_list[1 + max_check:]          # keep any overflow unchecked

    survivors = []
    if candidates:
        with ThreadPoolExecutor(max_workers=min(len(candidates), 5)) as ex:
            futures = {ex.submit(_check_one, p): p for p in candidates}
            results = [f.result() for f in as_completed(futures)]
        results.sort(key=lambda x: candidates.index(x[0]))
        for poi, inside, conf, reason in results:
            if inside or conf == "low":      # keep on low confidence (don't over-remove)
                survivors.append(poi)
            else:
                print(f"   X SCOPE-CHECK REMOVED '{poi['name']}' — outside '{scope_name}': {reason}")

    kept = [first_stop] + survivors + tail
    kept.sort(key=lambda p: poi_list.index(p))
    return kept
```

### Call site (immediately after PHASE 5.5b, ~line 1474)

```python
# PHASE 5.6: geographic-scope containment — only when the museum guard did NOT run
if not (tour_category == 'museum' and _museum_venue_name):
    _scope_for_check = _museum_venue_name or (
        _geo_scope if _scope_precision in ('BUILDING', 'DISTRICT') else '')
    if _scope_for_check:
        _before = len(poi_list)
        print(f"\nPHASE 5.6: Validating stops are within '{_scope_for_check}'...")
        poi_list = _validate_stops_within_scope(poi_list, _scope_for_check, headers)
        print(f"OK PHASE 5.6: {len(poi_list)}/{_before} stop(s) within scope")
        if len(poi_list) <= max(1, _before // 2):
            print(f"  [PHASE 5.6] >50% of stops were outside '{_scope_for_check}' — "
                  f"scope is likely a small single venue mis-read as a district; "
                  f"delivering {len(poi_list)} verified stop(s).")
```

For the Robbins House request this asks, per stop, *"Is Walden Pond within 'Robbin's House and Monument Square museum'?"* → no → removed; same for The Old Manse, etc. The result is a short, **correct** tour (the genuine Robbins House stop(s)) rather than 8 confidently-wrong Concord landmarks. Note it does **not** depend on fixing intent analysis — it works off the scope string the user actually gave, so it is robust to the "and" mis-parse.

---

## 4. Secondary fix — recover the missed single venue (improves detection, optional)

The containment guard above makes the tour *correct*; this makes it *fuller* by catching the venue when phrasing includes "and." Add a deterministic post-intent promotion: when `venue_name` is null but the request uses an interior preposition and the scope ends in an institutional noun, promote the scope to a venue and let the museum guard (5.5b) run.

```python
# After the venue_name sanity block (~line 556), before the S15 force:
if not intent.get('venue_name'):
    _req = (location or '').lower()
    _scope = (intent.get('geographic_scope') or '')
    _INSTITUTION_TAIL = ('museum', 'house', 'gallery', 'library',
                         'homestead', 'mansion', 'estate', 'manse')
    _interior = re.search(r'\b(in|inside|within|of)\b', _req)
    if (_interior and _scope
            and _scope.strip().lower().rstrip('.').endswith(_INSTITUTION_TAIL)
            and intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT')):
        intent['venue_name'] = _scope.strip()
        print(f"  [venue promotion] scope '{_scope}' promoted to venue_name "
              f"(interior preposition + institutional noun)")
```

This answers Kiro's Q1 ("how do we distinguish 'tour in Robbin's House' from 'tour in Harvard Square and MIT campus'?"): the discriminator is a **singular trailing institutional building noun** (`museum`/`house`/`gallery`/…). "Harvard Square" ends in "square" (a district noun) and "MIT campus" in "campus" — neither is in `_INSTITUTION_TAIL`, so they are *not* promoted, and the containment guard (Fix 3 below / Fix 1) handles them as a district. This heuristic is best-effort; it is safe precisely because Fix 1 is the real safety net behind it.

Also add one intent-prompt example (line ~139 area) so GPT learns the single-venue-with-"and" shape:
```
- "tour in Robbins House and Monument Square museum, Concord, MA" → venue_name: "The Robbins House", geographic_scope: "The Robbins House, Concord", scope_precision: "BUILDING"
```

---

## 5. Answers to Kiro's four questions

1. **More aggressive venue detection?** Yes, but narrowly and deterministically (Fix 4 above: interior preposition + trailing institutional building noun). Do *not* loosen the LLM prompt broadly — that risks the multi-venue regressions Kiro rightly fears. The real robustness comes from Fix 1, not from making intent analysis cleverer.
2. **Cap stops for small venues?** Don't hard-cap up front (you can't reliably know venue size before generation). Instead let Fix 1 cap it *empirically*: a tiny venue simply yields few in-scope stops, and the ">50% removed" branch surfaces it. Delivering 2 correct stops beats padding to 8 with out-of-scope landmarks. (If you later want a nicer UX, the ">50% removed" signal is the right place to optionally re-request a couple of genuine in-venue exhibits.)
3. **Worth fixing now?** The specific request is niche, but the **enforcement gap is general** — it is the same root as the Thoreau's Bedroom miss and will recur for any tightly-scoped request. Fix 1 is ~50 lines reusing an existing pattern and closes the whole class. Worth it; not Phase-B-blocking.
4. **Post-generation scope check?** Yes — this is exactly Fix 1, and it is the recommendation. Your instinct in Q4 was the right one.

---

## 6. Summary
| Layer | Today | Fix |
|---|---|---|
| Intent analysis | "and" → `venue_name: null`, scope→DISTRICT | Fix 4 (optional): deterministic venue promotion on interior-preposition + institutional-noun |
| In-prompt constraint | S17 text injected but unenforced | unchanged (keep as a hint) |
| Compactness | GEO-CHECK passes (stops are close) | unchanged (it's not the right tool for containment) |
| **Containment** | **none when `venue_name` null** | **Fix 1 (primary): PHASE 5.6 `_validate_stops_within_scope`, checks every stop** |

Primary recommendation: ship **Fix 1 (PHASE 5.6)**. It is the missing enforcement layer, robust to intent-analysis errors, reuses the existing PHASE 5.5b pattern, and self-limits small venues. Fix 4 + the prompt example are cheap detection improvements that make full-length correct tours more likely but are not required for correctness.
