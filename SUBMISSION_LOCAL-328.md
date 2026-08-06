##### READY FOR REVIEW

**Commit:** a995a4d  
**Branch:** kiro/local328-corpus-source-quality  
**Agent:** Mac Mini Kiro  
**Prior commit (kept):** af156c8 (measurement + sludge detection + quality scoring module)

## Per-file summary

| File | Change |
|------|--------|
| `corpus_source_quality.py` | Added Signal 5: `directory_breadcrumb_listing` — catches passages with 3+ dash-separated segments (breadcrumb navigation) plus a bare enumeration index (`\d+\.`). Structural, no phrase blocklist. |
| `generate_tour_text.py` | Replaced `SELECT stop_title, passage_count` with `SELECT stop_title, passages_json`; now computes `compute_quality_score` per stop and sorts by `-quality_score` instead of `-passage_count`. The source-weighted scoring (sludge excluded) is now the production selection signal. |
| `tests/test_local328_corpus_source_quality.py` | Added 5 new tests: `test_directory_breadcrumb_listing`, `test_breadcrumb_with_different_category`, `test_legitimate_dash_usage_not_flagged`, `test_rossettisserie_directory_listing_caught` (live DB), `test_selection_uses_quality_score_not_passage_count` (wiring check), `test_filter_applied_in_stop_corpus_reader` (wiring check). 24 total, all pass. |
| `stop_corpus_reader.py` | Unchanged in this commit — filter_passages_for_generation was already wired in af156c8. |

## Evidence: Yield per source type

```
Source Type           Total  Sludge  Useful  Sludge% Avg Chars
--------------------------------------------------------------
wikipedia               142       0     142     0.0%       246
bare_string              92       0      92     0.0%       403
web_search               86      29      57    33.7%       146
museum_official          41       0      41     0.0%       233
external_verified        36       1      35     2.8%       541
object_no_type           30       0      30     0.0%       428
museum_partner            1       0       1     0.0%       232
museum_site               1       0       1     0.0%       201
heritage                  1       0       1     0.0%       104
--------------------------------------------------------------
TOTAL                   430      30     400     7.0%
```

**Key finding:** web_search has 33.7% sludge rate. museum_official has 0%. The 3.3x yield gap LEAD measured is confirmed and now encoded in the scoring weights.

## Evidence: La Rossettisserie (bounce motivating example)

```
Stop: La Rossettisserie (4 passages)
  [KEEP  ] #1: "You will see two signs: Boulangerie de la Cathédrale and La Rossettisserie..."
  [SLUDGE (directory_listing)] #2: "... La Rossettisserie Lien en Bio ... {carte restaurant Nice..."
  [KEEP  ] #3: "The locally sourced menu at La Rossettisserie specializes in simple dishes..."
  [SLUDGE (directory_breadcrumb_listing)] #4: "La Rossettisserie - Restaurants near me - Nice, Alpes-Maritimes. 11. La..."

Survives: 2/4 passages
```

Passage #4 (the canonical directory listing from the bounce) is now caught by Signal 5. Passage #3 (the one genuinely useful sentence) survives. Passage #1 (promotional/wayfinding) survives — it contains a fact ("since 2008") and is not structurally a directory listing.

**Can this stop produce a fact?** Yes — passage #3 tells us the menu specializes in simple dishes with emphasis on meat. That is extractable. The quality score (0.5–1.0 depending on which venue entry) correctly reflects this is a poorly-documented stop.

## Evidence: Museum does not regress

```
Museum 8-stop (Musée des Arts Asiatiques):
  OLD ORDER (by -passage_count):    top-8 = {all 8 stops, same order}
  NEW ORDER (by -quality_score):    top-8 = IDENTICAL

  All 8 museum stops have 0 sludge, 100% museum_official passages.
  Quality scores: 9.0 – 18.0 per stop.
  Selection order is preserved exactly.
```

The museum tour cannot regress because all museum_official passages have 0% sludge. The quality_score preserves the same relative ordering as passage_count when no sludge is present (3.0 weight × N passages = 3N, which is monotonically related to N).

## Evidence: Restaurant tour scores differently

```
OLD 5-stop selection (by -passage_count):
  1. Chez Palmyre (pc=5)
  2. La Merenda (pc=5)
  3. La Rossettisserie (pc=4)      ← selected
  4. Le Bistro du Port (pc=4)
  5. Olive & Artichaut (pc=4)      ← selected

NEW 5-stop selection (by -quality_score):
  1. La Merenda (quality=2.5)
  2. Le Bistro du Port (quality=2.0)
  3. Chez Palmyre (quality=2.0)
  4. La Voglia (quality=1.5)       ← replaces Olive & Artichaut
  5. La Rossettisserie (quality=1.0)← drops from rank 3 to rank 5

La Rossettisserie: rank 3 → 5
Olive & Artichaut (3 sludge/4 passages): dropped from top-5
La Voglia (0 sludge/3 passages): promoted into top-5
```

## Evidence: Tests fail against unfixed code

1. `test_directory_breadcrumb_listing`: Without Signal 5, `is_sludge("La Rossettisserie - Restaurants near me...")` returns `(False, "")`. Test asserts True → **FAILS**.

2. `test_selection_uses_quality_score_not_passage_count`: Asserts `'compute_quality_score' in source` and `'SELECT stop_title, passage_count' not in source`. Before wiring → **FAILS** (old SELECT pattern present, compute_quality_score absent).

3. `test_rossettisserie_directory_listing_caught`: Runs against live DB, finds the "Restaurants near me" passage, asserts `is_sludge=True`. Without Signal 5 → **FAILS**.

## Verification summary

| Check | Result |
|-------|--------|
| `stop_corpus` row count | 112 (unchanged) |
| `git status --short` | Clean (empty) |
| museum_official false positives | 0 |
| wikipedia false positives | 0 |
| Total sludge flagged | 30/430 (7.0%) |
| Tests passing | 24/24 |
| `generate_tour_text.py` uses quality_score | ✓ (verified by test) |
| `stop_corpus_reader.py` filters sludge | ✓ (verified by test) |
| No container rebuilds | ✓ |
| No rows deleted | ✓ |
| No phrase blocklist | ✓ (all signals are structural) |

## Limitations

1. **Passage #1 ("You will see two signs...")** is promotional/wayfinding copy but is not structurally detectable as sludge. It has a complete sentence structure and no breadcrumb/delimiter patterns. A "promotional language" signal would require NLP beyond structural analysis and risks the proper-noun trap (D236).

2. **The `external_verified` false positive** (1 passage: "Matisse Museum Nizza: A Deep Dive into Henri Matisse's Enduring Legacy on the French Riviera ... opened as the Matisse Museum in 1963. ...") is a genuine search snippet — it IS a truncated scraped result, not authored prose. It happens to contain one fact. This is borderline-correct rather than a false positive.

3. **Restaurant 5-stop rubric score impact** cannot be measured without running a full generation (which costs API calls and risks exceeding the $0.60 ceiling). The selection order change is proven; the rubric score difference will manifest on next generation run. Honest expectation: the score may drop slightly because La Rossettisserie's remaining 2 passages produce fewer facts than the 5-passage raw count suggested, but La Voglia (promoted) has 3 clean passages that may compensate.

4. **The quality score signal only activates in the museum deterministic-fill path** (generate_tour_text.py line ~4115). Non-museum tours that go through Phase 3A (GPT-generated POI list) don't use this ranking. The filter_passages_for_generation in stop_corpus_reader.py still helps those tours by removing sludge from the prompt.
