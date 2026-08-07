##### READY FOR REVIEW

## LOCAL-349: Rank COVERED candidates by expected yield

**Commit:** d9306b4  
**Branch:** kiro/local349-rank-covered-by-yield  
**Base:** storied

---

### Per-file summary

| File | Change |
|------|--------|
| `corpus_source_quality.py` | Added `get_bulk_quality_scores()` — one-pass DB fetch that computes LOCAL-328 quality scores for all candidates. Keeps best row per stop by score (not passage count per D241). |
| `generate_tour_text.py` | Replaced flat coverage sort with `(tier, -quality_score)` tuple sort. Yield is tie-breaker within tier. Added DB connection for scoring + logging. |
| `tests/test_local349_yield_ranked_selection.py` | 15 tests: unit (sort behavior, arithmetic, museum stability) + DB integration (Acchiardo vs Rossettisserie live). |

---

### Counterfactual table (against live DB)

The exact restaurant run from the task description (6 candidates, 4 stops requested):

```
Candidate                 Verdict       Yield Score
-------------------------------------------------------
Le Safari                 COVERED               3.5
Acchiardo                 COVERED               3.0
La Tapenade               COVERED               2.5
Le Tire Bouchon           COVERED               1.5
La Rossettisserie         COVERED               1.0
Le Vieux Four             VENUE_ONLY            2.5
```

**OLD selection** (flat COVERED, position order preserved):
```
Selected: [La Rossettisserie=1.0, Le Tire Bouchon=1.5, La Tapenade=2.5, Le Safari=3.5]
Dropped:  [Acchiardo=3.0, Le Vieux Four=2.5(VENUE_ONLY)]
```

**NEW selection** (LOCAL-349: coverage tier + yield sub-ranking):
```
Selected: [Le Safari=3.5, Acchiardo=3.0, La Tapenade=2.5, Le Tire Bouchon=1.5]
Dropped:  [La Rossettisserie=1.0, Le Vieux Four=2.5(VENUE_ONLY)]
```

**Delta:**
- Gained: Acchiardo (3.0) — 4 clean passages, web_search + interpretive_enrichment
- Lost: La Rossettisserie (1.0) — 2 clean passages from best row, web_search only

**Acchiardo (3.0) preferred over La Rossettisserie (1.0): ✓**

---

### La Rossettisserie corpus detail (confirms D241)

```
venue: restaurant tour in Old Nice (Vieux Nice), France
total: 4, clean: 2, sludge: 2, score: 1.0
  [KEEP]   web_search: "You will see two signs: Boulangerie de la Cathédrale and La Rossettisserie..."
  [SLUDGE] web_search: directory listing (fragment density)
  [KEEP]   web_search: "The locally sourced menu at La Rossettisserie specializes in simple dishes..."
  [SLUDGE] web_search: directory breadcrumb listing
```

### Acchiardo corpus detail

```
venue: Old Nice, Nice, France
total: 6, clean: 4, sludge: 2, score: 3.0
  [KEEP]   web_search: "Madalin Acchiardo was a widow when she opened Acchiardo in 1927..."
  [SLUDGE] web_search: directory listing
  [SLUDGE] web_search: truncated snippet
  [KEEP]   web_search: "I am Virginie Acchiardo, head chef of the Acchiardo restaurant..."
  [KEEP]   interpretive_enrichment: "A traditional Nice restaurant run by the Acchiardo family since 1927 (4 generations)..."
  [KEEP]   interpretive_enrichment: "Jeff Bezos The Acchiardo siblings and owners of Chez Acchiardo..."
```

---

### Museum stability verification

Museum stops have uniformly high scores (4.5–18.0 per object) from `museum_official` source weight (3.0). The yield sort does NOT disturb museum selection because:

1. Museum uses its own deterministic path (LOCAL-328, line ~4268) with `_depth_map` scoring — it never hits the LOCAL-212 general selection block.
2. Even if it did, equal scores within the tier → stable sort → position order preserved.

Museum bounds: 8-stop 75.0, 4-stop 81.2 — **unchanged** (museum path not touched).

---

### Verification checklist

- [x] Acchiardo preferred over La Rossettisserie (3.0 > 1.0)
- [x] Coverage tier remains primary sort key (VENUE_ONLY never beats COVERED)
- [x] Stop count preserved (always selects `total_stops` candidates)
- [x] Museum path unaffected (separate deterministic selection)
- [x] `stop_corpus` row count: 133 (unchanged)
- [x] `audio_tours` row count: 153 (unchanged, real count 29 as specified)
- [x] Tests: 15 passed (12 unit + 3 DB integration)
- [x] Existing LOCAL-328 tests: 23/24 pass (1 pre-existing stale count assertion)
- [x] `git status --short`: clean after commit
- [x] No container rebuild

---

### Limitations

1. **Regeneration required and I cannot run it** — `OPENAI_API_KEY` is not in my environment. LEAD must regenerate restaurant/walking tours to verify score changes. The counterfactual table above is the structural proof; actual scores will depend on which candidates the LLM proposes in each run (selection variance).

2. **Selection variance** — A single regenerated tour is one sample. The yield ranking improves the *expected* selection quality across runs, but any individual run may still propose different candidate sets depending on LLM output order.

3. **Walking tour impact not measured end-to-end** — Walking stops are fewer (6 in corpus) and the 8-stop request likely takes all of them. The yield ranking has most impact when candidates exceed slots (restaurant scenario with 6 candidates, 4 slots).

4. **Quality score is additive** — A stop with many mediocre passages (e.g. 5 × web_search = 2.5) can outscore one with fewer excellent passages (e.g. 1 × museum_official = 3.0 but 1 × web_search = 0.5, total 3.5). For restaurant tours this is acceptable since source types are similar across candidates.
