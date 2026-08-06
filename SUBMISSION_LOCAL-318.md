##### READY FOR REVIEW

## LOCAL-318: Dangling-demonstrative gate

**Commit:** bf6e96c  
**Branch:** kiro/local318-dangling-demonstrative  
**Commits ahead of storied:** 2

---

### Per-file summary

| File | Purpose |
|------|---------|
| `dangling_demonstrative_gate.py` | New module: detects `this/these/that/those + <noun phrase>` with no antecedent in same stop's spoken text. Repair from corpus (name substitution) or deletion. |
| `generate_tour_text.py` | Added PHASE 5.7b hook (after existing PHASE 5.7) calling the new gate. |
| `tests/test_local318_dangling_demonstrative.py` | 16 pytest tests covering detection, clean cases, repair, integration, corpus scan. |
| `tests/run_local318_generate_tour.py` | Generation script for 5-stop restaurant tour verification. |
| `tours/LOCAL318_5stop_old_nice_restaurant.txt` | Generated tour artifact — zero dangling demonstratives. |

---

### Root cause confirmed

PHASE 5.7 (line 8357 of `generate_tour_text.py`) scrubs **only** dangling "Stop N" references where N exceeds the final stop count. It does NOT examine demonstrative noun phrases. The existing `unglossed_reference_gate.py` handles **proper names** needing glosses, not demonstrative NPs.

The defect: "This chickpea flour pancake" references "socca" which appeared only in a schema line (`Specific Examples: socca (chickpea pancake)`) — never in spoken text. Schema lines are never read aloud.

---

### Verbatim evidence

**Detection of the exact defect:**
```
>>> detect_dangling_demonstratives(
...     "Madalin's great-grandchildren continue to honor her culinary traditions. "
...     "This chickpea flour pancake, cooked to a golden crisp, exemplifies the region's resourcefulness.",
...     "Acchiardo")
[{'sentence': "This chickpea flour pancake, cooked to a golden crisp, exemplifies the region's resourcefulness.",
  'demonstrative_np': 'This chickpea flour pancake',
  'head_noun': 'pancake', ...}]
```

**Repair with corpus:**
```
Before: This chickpea flour pancake, cooked to a golden crisp, exemplifies the region's resourcefulness.
After:  The socca, a chickpea flour pancake, cooked to a golden crisp, exemplifies the region's resourcefulness.
Action: repaired
```

**Three clean cases — zero findings:**
```
Case 1 "This restaurant opened in 1927." → 0 findings (setting noun)
Case 2 "Chagall painted the ceiling. This work took two years." → 0 findings (creative context)
Case 3 "These narrow streets wind through Vieux Nice." → 0 findings (setting noun)
```

**Corpus-wide count:** 12 dangling demonstratives across 52 existing tour files in `tours/*.txt`.

**Generated tour:** `tours/LOCAL318_5stop_old_nice_restaurant.txt` — 5 stops, zero dangling demonstratives, reads as coherent prose.

---

### Test output

```
16 passed in 0.09s

tests/test_local318_dangling_demonstrative.py::TestDetection::test_chickpea_pancake_detected PASSED
tests/test_local318_dangling_demonstrative.py::TestDetection::test_dangling_these_detected PASSED
tests/test_local318_dangling_demonstrative.py::TestDetection::test_dangling_that_detected PASSED
tests/test_local318_dangling_demonstrative.py::TestDetection::test_schema_line_does_not_count PASSED
tests/test_local318_dangling_demonstrative.py::TestCleanCases::test_restaurant_stop_is_the_restaurant PASSED
tests/test_local318_dangling_demonstrative.py::TestCleanCases::test_antecedent_present_in_same_stop PASSED
tests/test_local318_dangling_demonstrative.py::TestCleanCases::test_narrow_streets_setting PASSED
tests/test_local318_dangling_demonstrative.py::TestCleanCases::test_title_serves_as_antecedent PASSED
tests/test_local318_dangling_demonstrative.py::TestCleanCases::test_earlier_mention_in_same_stop PASSED
tests/test_local318_dangling_demonstrative.py::TestCleanCases::test_plural_antecedent_singular_demonstrative PASSED
tests/test_local318_dangling_demonstrative.py::TestRepair::test_repair_with_corpus_name PASSED
tests/test_local318_dangling_demonstrative.py::TestRepair::test_delete_when_no_corpus PASSED
tests/test_local318_dangling_demonstrative.py::TestRepair::test_delete_when_corpus_has_no_name PASSED
tests/test_local318_dangling_demonstrative.py::TestIntegration::test_gate_modifies_description PASSED
tests/test_local318_dangling_demonstrative.py::TestIntegration::test_gate_does_not_touch_clean_stops PASSED
tests/test_local318_dangling_demonstrative.py::TestCorpusScan::test_corpus_scan PASSED
```

---

### Limitations

1. **No full POS tagger.** NP extraction uses a word-list approach (modifier set + stop-word set) rather than a proper POS tagger. Edge cases where an unusual adjective or noun isn't in the lists may slip through or false-positive. The 12 corpus-wide findings include a few borderline cases (e.g. "These violas" at a stop titled "Violes d'amour" — French/English mismatch in title).

2. **Repair requires corpus pattern match.** The corpus name finder uses regex patterns like "X, a <description>" to locate the proper name. If the corpus describes the entity in an unusual syntactic pattern, repair will fail and the sentence will be deleted (safe fallback).

3. **Same-stop scope only.** By design, cross-stop references are not resolved. A noun mentioned in Stop 4 does not license a demonstrative in Stop 2.

4. **No LLM calls.** The gate is entirely deterministic (regex + word-lists). This means $0.00 marginal cost but no semantic understanding of whether a demonstrative is truly dangling in ambiguous cases.

5. **Generated tour (Stop 5, La Voglia)** contains a factually irrelevant passage about a G8 meeting — this is a pre-existing issue with the unsupported-claim gate (LOCAL-263 scope), not a dangling-demonstrative issue.
