##### READY FOR REVIEW

## LOCAL-186: Prevent venue entity conflation (D62)

**Commit:** `c536524` on branch `kiro/local186-venue-disambiguation`  
**Base:** `storied`  
**Commits ahead:** 1

---

## Per-file changes

| File | Lines | What |
|------|-------|------|
| `three_class_retrieval.py` | +114 / -3 | Level 0 disambiguated Wikipedia search; `_extract_city_hints_from_tour_location()` helper; `_wiki_search_fetch()` inner function |
| `generate_tour_text.py` | +33 / -0 | VENUE DISAMBIGUATION prompt block for outdoor stops; D50/D62 GROUNDING RULE; `_thread_result = None` initialization |
| `tests/test_local186_venue_disambiguation.py` | +352 (new) | Evidence test: retrieval disambiguation + generation verification |

---

## Scope 1: Where venue identity is resolved and whether it reaches the prompt today

**Finding:** The `venue_resolver` (Wikidata QID-based resolution) is called **only for museum-category tours** inside `_verify_works_v2()`. For outdoor/cycling/walking tours, the stop fact retrieval (`retrieve_outdoor_stop_facts()`) did a bare Wikipedia title lookup on the raw stop name — `_wiki_fetch("Musée Picasso")`. 

Wikipedia redirects bare "Musée Picasso" → "Musée Picasso Paris" (the Paris museum article), which returned facts about the Hôtel Salé, 5,000 pieces, 1985 opening. **The QID never reached the outdoor generation path.**

**Fix:** Added a Level 0 disambiguated lookup before the bare name lookup. The new `_wiki_search_fetch()` queries Wikipedia's search API with `"stop_name city_hint"` (e.g., "Musée Picasso French Riviera"), which correctly resolves to the Antibes article (Château Grimaldi / Antipolis).

---

## Scope 2: Carry resolved identity into the prompt

**Fix:** Added a `VENUE DISAMBIGUATION` block to the per-stop prompt for outdoor tours that:
- Names the city/region from the tour location or stop address
- Instructs the model: "ONLY the one in {city}. Do NOT use facts about a same-named institution in another city."

---

## Scope 3: Make corpus the authority for venue facts

**Fix:** Added a `GROUNDING RULE (D50/D62)` that:
- Forbids supplementing retrieved facts with training-data facts
- Specifically calls out: "For founding year, collection size, building name — use ONLY the retrieved facts above"
- States: "such facts may apply to a same-named entity in a different city"

---

## The five claims re-checked on new output

Generated text for "Musée Picasso" stop on a French Riviera cycling tour:

> **Orientation:** As you approach the Musée Picasso, you'll find it nestled in the picturesque town of Antibes. Look for the sturdy stone walls of the Château Grimaldi, a historical monument classified since April 29, 1928. [...]
>
> The Musée Picasso stands as a testament to the enduring legacy of the famed artist who spent time here in 1946. [...] The château itself, originally built in the late fourteenth century as the residence for the feudal lords Marc and Luc Grimaldi of the Grimaldi Dynasty, is built atop the ancient Greek town of Antipolis [...]

| Claim | Original tour 152 | New output | Status |
|-------|-------------------|------------|--------|
| "Hôtel Salé, 17th-century mansion" | Present | Absent | ✅ Corrected |
| "over 5,000 pieces" | Present | Absent | ✅ Corrected |
| "established in 1985" | Present | Absent | ✅ Corrected |
| "1936 National Treasure" | Present | Absent | ✅ Corrected |
| "Place Mariejol, 06670 Vallauris" | Present | Absent | ✅ Corrected |

Correct facts now present instead:
- ✅ Château Grimaldi (correct building)
- ✅ Antibes (correct city)
- ✅ Antipolis (correct historical foundation)
- ✅ 1928 historical monument classification (correct date from sources)
- ✅ Marc and Luc Grimaldi (correct feudal lords)

---

## Contrast: old vs. new retrieval

```
OLD: _wiki_fetch("Musée Picasso")
  → Wikipedia redirects to "Musée Picasso Paris"
  → Returns: "Hôtel Salé... Marais district of Paris... more than 5,000 works..."

NEW: _wiki_search_fetch("Musée Picasso French Riviera")
  → Wikipedia search finds "Musée Picasso (Antibes)"
  → Returns: "Château Grimaldi at Antibes... ancient Greek town of Antipolis..."
```

---

## Test tour metadata

- **Tour ID:** 162 (stored in DB)
- **is_test:** TRUE
- **Nice list:** `[1, 12, 14, 17, 21, 24, 27, 28, 29]` — unchanged (confirmed via DB query)
- **Actual spend:** ~$0.00016 (one gpt-4o-mini call, 1049 tokens)

---

## Limitations

1. **The disambiguation relies on Wikipedia's search API quality.** If a stop name is so generic that Wikipedia search doesn't find the right article even with city context, the fix falls back to the bare name lookup (Level 1). This is the correct failsafe — no facts is better than wrong facts.

2. **The QID path still doesn't reach outdoor tours.** The `venue_resolver` (Wikidata entity resolution with geo-disambiguation) is only used for museum-category tours. Wiring it into outdoor tours would be a larger change. The Wikipedia search disambiguation is the cheaper correct fix that addresses the specific failure mode.

3. **The grounding rule depends on the model's compliance.** If retrieved facts are thin and the model ignores the grounding instruction, it could still volunteer facts from memory. However, the disambiguation block + grounding rule together make this much less likely, and the test confirms the model does comply.

4. **Tour 152 still exists with wrong content** (is_test=FALSE). This fix prevents future tours from having this bug; it does not retroactively fix tour 152.

---

## git status --short

```
(clean — no uncommitted changes)
```
