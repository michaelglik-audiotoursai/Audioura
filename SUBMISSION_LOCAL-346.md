##### READY FOR REVIEW

## LOCAL-346: Bridge vs thin row — merge, not suppress

**Commit:** `b56db65`  
**Branch:** `kiro/local346-bridge-vs-thin-row`  
**Base:** `storied`

---

### Per-file summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | Changed the stop lookup loop: when a stop_corpus match exists, also attempt the venue_corpus bridge. If both provide material, merge via new `_merge_stop_and_bridge()` function. Bridge passages first (tier-1 Wikipedia), then deduplicated enrichment passages. |
| `tests/test_local346_bridge_vs_thin_row.py` | 10 tests: merged content assertions, source type checks, museum object safety, museum score bounds, corpus row count invariants, degraded stop count report. All import production code and fail against unfixed version (3 passages ≤ 5 threshold). |

---

### The rule and its justification

**Rule: Always attempt the bridge. When both stop_corpus and venue_corpus provide material for the same stop, merge them.**

Why not passage count alone (D241): passage count is anti-correlated with quality; the enrichment's 3 passages are tier-3 travel blogs while the venue_corpus's 2 pages contain 16,624 bytes of tier-1 Wikipedia. Count doesn't capture this.

Why not source type alone: source type IS a better predictor (D241), but choosing one over the other discards real content. The enrichment material is independently gathered and verified — it adds detail the Wikipedia article may lack.

Why merge is safe: the bridge only fires when `_venue_name_matches_stop(stop_title, venue_corpus.venue_name)` returns True. Museum objects like "Harpe by Naderman (Paris, 1780)" never match "Palais Lascaris, Nice" — so museum tours are surgically excluded without any museum-specific code paths.

---

### Degraded stop count (blast radius)

**4 stop_corpus rows across 3 unique stops were degraded:**

```
Musee Matisse      | sc_venue='French Riviera walking area'        | sc_passages= 1 | vc_bytes=48,827
Musée Matisse      | sc_venue='French Riviera walking area'        | sc_passages= 2 | vc_bytes=48,827
Palais Lascaris    | sc_venue='walking tour of Vieux Nice, France' | sc_passages= 3 | vc_bytes=16,624
Musée Picasso      | sc_venue='French Riviera walking area'        | sc_passages= 4 | vc_bytes=6,075
```

All are now fixed by the read-time merge.

---

### Verbatim evidence

#### Palais Lascaris: before and after (thin row still present)

```
stop_corpus row:  passage_count=3, type=interpretive_enrichment (STILL IN TABLE)
venue_corpus row: Palais Lascaris, Nice | 2 pages | 16,624 bytes (UNCHANGED)

Pre-fix:  3 passages, source_types={'interpretive_enrichment'}
Post-fix: 30 passages, source_types={'venue_corpus_bridge', 'interpretive_enrichment'}
```

#### Museum object: unaffected

```
'Harpe by Naderman (Paris, 1780)' under 'Palais Lascaris, Nice':
  7 passages, source_types={'wikipedia'}
  venue_corpus_bridge in sources: False
```

#### Museum score bounds

```
Museum 8-stop (Asian Arts):         82.5625  >= 75.0  ✓
Museum Palais Lascaris (6-stop):    81.25    >= 81.2  ✓
```

#### Corpus table row counts

```
stop_corpus:  123 rows (unchanged)
venue_corpus:  19 rows (unchanged)
```

#### Test results

```
tests/test_local346_bridge_vs_thin_row.py  10 passed
tests/test_local342_venue_as_stop_bridge.py 8 passed  (was 6/8, now 8/8)
tests/test_local345_corpus_in_body.py       8 passed
Total: 26 passed, 0 failed
```

---

### Limitations

1. **Regeneration required.** I cannot run it — `OPENAI_API_KEY` is not in my environment. Expected result: Palais Lascaris returns to RICH with the 3-passage thin row still in place. LEAD must regenerate and confirm.

2. **Dedup is prefix-based (first 100 chars normalized).** If enrichment and bridge contain the same fact phrased differently beyond the first 100 chars, both copies will survive. This is acceptable — the generator's own dedup handles it, and false positives (keeping a near-duplicate) are less harmful than false negatives (dropping unique content).

3. **The bridge always runs now for stops with a corpus match.** This adds one `_venue_name_matches_stop` comparison per stop per call. For the typical 8-stop tour against 10 venue_corpus rows, this is 80 string comparisons — negligible.

4. **The 4-stop 81.2 bound:** the closest available tour file is the 6-stop Palais Lascaris museum at 81.25. The specific 4-stop Asian Arts tour file is not present in this worktree's `tours/` directory. The bound is met by the proxy; LEAD may wish to verify the exact file.
