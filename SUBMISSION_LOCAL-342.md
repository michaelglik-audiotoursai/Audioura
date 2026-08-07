##### READY FOR REVIEW

## LOCAL-342: Venue-as-Stop Corpus Bridge

**Commit:** `6f16014`
**Branch:** `kiro/local342-venue-as-stop-corpus`

---

### Per-file summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | Added venue-as-stop bridge: when `_match_stop_title_first` returns None, falls back to matching stop title against `venue_corpus.venue_name`. Extracts `pages_json` text, splits into passages, filters catalogue entries. Read-time only — no rows written. |
| `tests/test_local342_venue_as_stop_bridge.py` | 8 unit tests: bridge finds Palais Lascaris (27 passages), provides sources, has passage_roles; museum objects unaffected; walking-area venues rejected; accent/apostrophe folding works; catalogue filter works; no rows inserted. |

---

### 1. Venue-as-stop bridge

**Mechanism:** In `get_stop_corpus_for_tour`, after the normal stop_corpus match
fails, the new `_bridge_venue_corpus_to_stop` function:

1. Matches stop title to `venue_corpus.venue_name` — accent-folded, city-suffix
   tolerant (e.g. "Palais Lascaris" matches "Palais Lascaris, Nice")
2. Rejects "walking area" venue names (geographic labels, not buildings)
3. Extracts `pages_json` text (Wikipedia pages about the building)
4. Splits into paragraph-sized passages (≤800 chars)
5. Filters out short catalogue-style entries about objects inside
6. Returns with `passage_roles=[{role:'about_venue_as_stop'}]`

**Justification:** The Wikipedia article about Palais Lascaris describes the
building itself — its history, architecture, noble families. A walking-tour
listener standing outside needs exactly this. The 11 stop_corpus rows under that
venue describe instruments *inside* the museum — those stay in stop_corpus for
the museum tour and are not duplicated.

**Relevance filter:** `_is_object_catalogue_passage` rejects short passages
(<200 chars) that match object-catalogue patterns (maker attributions,
dimensions). Longer passages that mention a maker in the building's historical
context pass through. This is conservative — it would rather include a borderline
passage than miss relevant content about the building.

---

### 2. Enrichment gap — answered with evidence

**Question:** Why did LOCAL-332 interpretive enrichment produce nothing for
Cours Saleya, Nice Cathedral, Place Rossetti?

**Answer:** `SERP_API_KEY` is not set in the local environment.

**Evidence chain:**

```
$ env | grep -i serp
(empty — no SERP_API_KEY or SERPAPI_KEY)
```

From `interpretive_enrichment.py:360`:
```python
def _search_interpretive(query: str) -> List[Dict]:
    serp_key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not serp_key:
        logger.warning("[INTERPRETIVE] No SERP_API_KEY — cannot search")
        return []
```

The enrichment module fires during the existence gate (verified: the gate is in
`log_only` mode and the stops pass geographic verification via Nominatim). But
`_search_interpretive` returns `[]` for every query because no API key is
available. The function `enrich_stop_interpretive` then finds zero candidate
passages, `store_interpretive_corpus` writes nothing, and the stops remain
without corpus.

**This is not a code bug.** The module works as designed — it degrades gracefully
when the search API is unreachable. The operational gap is that `SERP_API_KEY`
needs to be set for enrichment to produce results.

For Palais Lascaris specifically: even WITH a working SERP key, the enrichment
would store passages in *stop_corpus* under the walking tour's venue_name. The
venue_corpus bridge is still necessary because the 16KB of Wikipedia content
already present in venue_corpus would not be consulted by stop_corpus lookups
without it.

---

### 3. Walking tour regeneration

**Cannot regenerate.** `OPENAI_API_KEY` is not set in the local environment.
`generate_tour_text` requires it and exits with "Error: OpenAI API key is
required" when absent.

**Corpus resolution verified without regeneration:**

```
=== CORPUS RESOLUTION (with bridge) ===
  Palais Lascaris: 27 passages, 16110 bytes [VENUE BRIDGE]
  Cours Saleya: 1 passages, 147 bytes [stop_corpus fuzzy match]
  Nice Cathedral: 5 passages, 1218 bytes [stop_corpus fuzzy match → WRONG: matches Port de Nice]
  Place Rossetti: 1 passages, 55 bytes [stop_corpus fuzzy match]
```

Palais Lascaris now has material. The other three still have negligible/wrong
corpus because:
- No enrichment (SERP_API_KEY absent)
- No venue_corpus row for "Cours Saleya", "Nice Cathedral", or "Place Rossetti"
- Their fuzzy matches in stop_corpus are false positives (Nice Cathedral → Port de Nice via "nice" containment)

---

### 4. Museum scores — unchanged

```
Museum 8-stop (Asian Arts, no corpus):     75.0
Museum 8-stop (Asian Arts, with bridge):   71.875  (corpus ceiling, NOT a regression from bridge)
Museum 4-stop (Palais Lascaris, no corpus): 81.25
Museum 4-stop (Palais Lascaris, with bridge): 81.25
```

The 75.0 → 71.875 difference is the corpus-availability ceiling (LOCAL-327) that
applies when a DB connection is available, not a change from this PR. With no
conn passed, it's 75.0 before and after.

Museum object stops ("Harpe by Naderman", "Venus and Cupid", etc.) still resolve
from stop_corpus. They don't trigger the bridge because their titles don't match
any venue_corpus.venue_name.

---

### 5. Row counts

```
stop_corpus:  117 rows (unchanged)
venue_corpus:  18 rows (unchanged)
audio_tours:  153 rows (unchanged)
```

---

### Test transcript (red → green)

**Pre-fix (stash applied, original code):**
```
FAILED tests/test_local342_venue_as_stop_bridge.py::TestVenueAsStopBridge::test_palais_lascaris_found_via_bridge
  AssertionError: Palais Lascaris should be found via venue_corpus bridge.
  Pre-LOCAL-342 code returns None here.
  assert None is not None
```

**Post-fix:**
```
tests/test_local342_venue_as_stop_bridge.py   8 passed, 1 warning in 0.31s
```

**Existing suites unbroken:**
```
tests/test_local340_groundedness_misattribution.py   10 passed
tests/test_local339_corpus_and_person.py             13 passed, 2 skipped
tests/test_local341_harvest_relevance.py             16 passed
```

---

### Limitations

1. **Walking tour cannot be regenerated and rescored** — no `OPENAI_API_KEY` in
   the environment. The corpus bridge is proven to work (27 passages found for
   Palais Lascaris), but the actual scoring impact on a generated tour is
   unmeasured.

2. **Three of four stops remain unfixed** — Cours Saleya, Nice Cathedral, and
   Place Rossetti have no venue_corpus entries and no enrichment (no SERP key).
   The bridge only helps stops that ARE venues. For the other three, either:
   - Set `SERP_API_KEY` and regenerate (enrichment will fire)
   - Manually add venue_corpus entries for these well-known places
   - Add them to stop_corpus via a targeted harvest

3. **False fuzzy matches exist** — "Nice Cathedral" matches "Port de Nice" via
   containment ("nice" is in "port de nice"). This is a pre-existing issue in
   `_match_stop_title_first` unrelated to this PR. It means the scorer may
   report groundedness against wrong corpus for these stops.

4. **Museum 4-stop baseline discrepancy** — the task states 87.5, the measured
   value is 81.25 (both before and after this change). This may reflect a prior
   scoring algorithm version change. The bridge does not alter the score.
