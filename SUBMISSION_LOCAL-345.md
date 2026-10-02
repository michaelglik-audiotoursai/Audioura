##### READY FOR REVIEW

**Task:** LOCAL-345 — Use available corpus  
**Commit:** f393450  
**Branch:** kiro/local345-use-available-corpus  
**Base:** storied

---

## 1. Root Cause: Why UNESCO Reached the Orientation but Not the Body

**Code path:**  
`generate_tour_text.py` line ~6559 → fetches corpus via `get_stop_corpus_for_tour()`  
`generate_tour_text.py` line ~7672 → injects via `format_passages_for_prompt()`  
`stop_corpus_reader.py` line ~279 → `format_passages_for_prompt()` builds the injection block

**The defect:** `format_passages_for_prompt()` injected corpus as:
```
PER-STOP SOURCE MATERIAL for "Cours Saleya Market" (from verified sources — use this as your primary factual basis):
  Passage 1 [ROLE: about_subject]: 2021: The city of Nice and its heritage sites...

GROUNDING RULE (D50 — critical): Substantiate claims ONLY from the passages above.
Do NOT supplement with facts from your own training data...
```

This is a **constraint** ("don't claim things outside these passages"), not a **directive** ("you must use these passages in your body"). The LLM obeys the letter: it avoids ungrounded claims but also sees no mandate to incorporate the passages. The orientation picks up "UNESCO" because the corpus block has recency bias at the end of the prompt — the LLM's initial orientation sentence draws on the freshest context. But by the time it generates the body (dozens of tokens later), it reverts to training data.

The Marquis etymology and "over 100 vendors" are both pure fabrication from training data, filling space because the model was never told it MUST use the provided material in the body.

## 2. "Had Corpus, Used None of It" — Measured Across All Scorable Tours

**Script:** `tests/run_local345_corpus_usage_audit.py`  
**Method:** For each stop with corpus, extract 4+ char content words from passages (excluding stop-words and stop-title words), then check if ANY appear in the body text. A floor metric: "zero overlap" means the body is entirely disconnected from the corpus.

```
Total stops with body text:         159
Stops with corpus available:        100
Stops with corpus UNUSED in body:   5
Usage rate:                         95.0%
```

**The 5 corpus-unused stops:**
| Tour | Stop | Passages |
|------|------|----------|
| LOCAL317_5stop_old_nice_restaurant.txt | Olive & Artichaut | 1 |
| LOCAL318_5stop_old_nice_restaurant.txt | La Rossettisserie | 1 |
| phase2_chagall_cache_hit.txt | La Bible : Abraham et Isaac en route… | 2 |
| phase2_chagall_rich.txt | La Bible : Abraham et Isaac en route… | 2 |
| pilot_chagall_resubmit.txt | The Sacrifice of Isaac | 2 |

Note: The Cours Saleya Market stop (the triggering defect) is not in `tours/` — tour files are gitignored. The 5 above are the measurable instances in the available corpus.

## 3. Why "over 100 vendors" Was Not Detected

**Location:** `tour_rubric_scorer.py` lines 783-793 (Track 1: digit-based measurement pattern)

The regex `\b(\d+(?:\.\d+)?\s*(?:m|cm|mm|...noun_list...))\b` previously listed ONLY:
- Physical units: m, cm, mm, km, kg, lb, ft, in
- Anatomical: arms, heads, hands, legs, eyes, faces
- Architectural: storeys, floors, columns, pillars, panels, tiers, steps
- Temporal: years, centuries, decades
- Other units: meters, centimetres, feet, kilograms, tons, pounds

**`vendors`** was not in this list. Neither were `stalls`, `merchants`, `shops`, `visitors`, or any general-quantity noun. The pattern was museum-oriented and missed outdoor/walking tour claims entirely.

**Fix:** Added to Track 1 and Track 2:
```
vendors?|stalls?|shops?|merchants?|artists?|
species?|varieties?|paintings?|sculptures?|works?|pieces?|
visitors?|tourists?|residents?|inhabitants?|
hectares?|acres?|miles?|blocks?|
seats?|tables?|dishes?|wines?|beers?|
churches?|chapels?|cathedrals?|mosques?|temples?|
islands?|beaches?|ports?|harbou?rs?
```

## 4. Fix Applied

**`stop_corpus_reader.py`** — Added BODY USAGE RULE after the GROUNDING RULE:
```python
"BODY USAGE RULE (LOCAL-345 — critical): Your DESCRIPTION BODY (the main narrative "
"paragraphs after the orientation) MUST incorporate specific facts, dates, or claims "
"from the passages above. The orientation alone is not sufficient — the body text is "
"where the listener spends most of their time. If a passage mentions a UNESCO designation, "
"a founding date, a named historical event, or a specific fact, that material MUST appear "
"in the body narrative, not just be referenced in the orientation line. A body that "
"contains zero material from the provided passages is a failure."
```

**`tour_rubric_scorer.py`** — Extended both Track 1 and Track 2 noun lists.

## 5. Verification

```
$ python3 -m pytest tests/test_local345_corpus_in_body.py -v
8 passed

$ python3 -m pytest tests/test_local34{0,2,3,4}*.py -v
48 passed (all neighboring tests pass, no regressions)
```

Museum bounds:
- 8-stop (Asian Arts): 77.3 ≥ 75.0 ✓
- 3-stop (Palais Lascaris): 83.3 ≥ 70.0 ✓

## 6. Regeneration Request

LEAD: Please regenerate the Cours Saleya Market stop (stop 1 of the Nice walking 4-stop tour) using the updated `stop_corpus_reader.py`. With the BODY USAGE RULE in place:
- The Marquis etymology must be gone (the corpus says nothing about it)
- The UNESCO designation must appear in the body (the corpus explicitly states it)
- "over 100 vendors" should now score as a numeric claim if it persists (it shouldn't — no corpus basis)

## Per-file Summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | Added BODY USAGE RULE directive in `format_passages_for_prompt()` |
| `tour_rubric_scorer.py` | Extended Track 1 & 2 digit-noun patterns (+7 noun groups) |
| `tests/test_local345_corpus_in_body.py` | 8 tests: digit detection, corpus-body overlap, prompt directive, museum bounds |
| `tests/run_local345_corpus_usage_audit.py` | Audit script measuring corpus usage across all scorable tours |

## Limitations

- The Cours Saleya Market tour file is not in `tours/` (gitignored); the defect was confirmed against the DB corpus row (id=62) and the prompt injection code path.
- The BODY USAGE RULE is a prompt-level fix; compliance depends on the LLM. Regeneration is required to verify it works in practice. `OPENAI_API_KEY` is not in this environment.
- The "had corpus, used none" audit uses a content-word overlap heuristic (≥1 word from passages in body). A stop could use a corpus fact rephrased beyond recognition and score as "unused" — false positives are possible but the 5 identified stops were manually inspected and are genuine gaps.
- The corpus for Cours Saleya Market is thin (1 passage, 151 chars). Even with the fix, the body will be thin.
