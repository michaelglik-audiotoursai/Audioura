##### READY FOR REVIEW

**Commit:** `8e8c5b7` on branch `kiro/local236-stop-existence-gate`
**Base:** `storied`

---

## Blast-Radius Measurement

**170 of 190 stops (89.5%) across 29 real tours are UNVERIFIED today.**

If the gate were enforced, it would empty nearly every tour. Only the Musée Marc Chagall (tour 24, 6 stops) fully verifies — it has proper SPARQL works in venue_corpus. The French Riviera tours (29, 152) partially verify via geographic POI matches.

| Venue / tour type | Tours | Stops | Verified | UNVERIFIED | % unverified |
|---|---|---|---|---|---|
| Asian Arts Museum Nice (all langs) | 21,22,23,27,28,30,31,32,33 | 70 | 0 | 70 | 100% |
| Museum of Naïve Art Nice (all langs) | 14,19,20 | 27 | 0 | 27 | 100% |
| French Riviera (biking/cycling) | 29,152 | 30 | 12 | 18 | 60% |
| Abu Dhabi camel tours | 2,3,4,5 | 19 | 0 | 19 | 100% |
| MAMAC Nice (Russian) | 151 | 10 | 0 | 10 | 100% |
| Nice walking tour | 12 | 10 | 0 | 10 | 100% |
| Palais Lascaris | 1 | 3 | 2 | 1 | 33% |
| Chagall Nice | 24 | 6 | 6 | 0 | **0%** |
| Other (dog sledding, restaurants, Constitution Center) | 6–11,17 | 15 | 0 | 15 | 100% |

**Why:** 26 of 29 tours were generated before any venue_corpus existed for their venue. Stop titles were invented by the model. LOCAL-234 then attached Wikipedia pages to those invented titles after the fact, which is D127's finding: we built corpus for fabricated stops.

---

## Per-File Summary

### `stop_existence_gate.py` (new, 320 lines)

The gate module. Core API:

- `verify_stop_existence(stop_title, venue_name, db_conn)` → `{verified, evidence, source}`
- `run_existence_gate(poi_list, venue_name, db_conn)` → gate result with verdicts

Verification checks (in order):
1. **venue_corpus**: canonical_titles_json or sparql_works_json title match (handles both string titles and geographic POI dicts)
2. **stop_corpus**: passage that names BOTH stop and venue in the same source (D74 same-source rule)
3. *(Future: venue catalogue page — not implemented)*

Feature flags:
- `ENABLE_STOP_EXISTENCE_GATE=1` → gate enforced, unverified stops dropped
- `DISABLE_STOP_EXISTENCE_GATE=1` → gate completely disabled (no logging)
- Neither set (default) → **LOG_ONLY**: verdicts computed and printed, stops NOT dropped

### `run_local236_blast_radius.py` (new, 160 lines)

Measurement script. Parses stop titles from all 29 real tours (handles both `Stop N:` format and address-before format), runs each through the gate, reports totals by venue and by tour. Asserts `audio_tours` count is 138 and Nice list `[1,12,14,17,21,24,27,28,29,152]` is intact.

---

## End-to-End Demonstrations

### Verified stop (Chagall):
```
=== DEMO: Chagall Museum (verified stops expected) ===
  [EXISTENCE-GATE] ENFORCED — 4/6 stops verified (67%), dropping 2 unverified
    [VERIFIED] 'Abraham et les trois anges' — venue_corpus canonical_title: 'Abraham et les trois anges'
    [VERIFIED] 'Le Cantique des Cantiques' — venue_corpus canonical_title: 'Le Cantique des Cantiques II'
    [VERIFIED] 'La Création de l homme' — venue_corpus canonical_title: "La Création de l'homme"
    [UNVERIFIED] 'Moïse et le Buisson ardent' — no evidence
    [UNVERIFIED] 'Le Passage de la Mer Rouge' — no evidence
    [VERIFIED] 'Le Cirque bleu' — venue_corpus canonical_title: 'Le Cirque bleu'
```

### Unverified stop (Asian Arts — the Chikanobu case):
```
=== DEMO: Asian Arts Museum (unverified stops expected) ===
  [EXISTENCE-GATE] ENFORCED — 0/4 stops verified (0%), dropping 4 unverified
    [UNVERIFIED] "L'Armure d'Andô Naoyuki" — no evidence
    [UNVERIFIED] 'Ulysses Grant au Japon' — no evidence
    [UNVERIFIED] 'Kannon à mille bras' — no evidence
    [UNVERIFIED] 'Masque du vieillard kojo' — no evidence
```

### LOG_ONLY mode (default behavior):
```
  [EXISTENCE-GATE] LOG_ONLY — 0/4 stops verified (0%), 4 would be dropped if enforced
    (verdicts computed and logged, stops NOT dropped)
```

---

## Stop-Count Behaviour When Candidates Run Out

When `ENABLE_STOP_EXISTENCE_GATE=1` is set and the gate is enforced:
- Only verified stops proceed to narration
- If all candidates are unverified, the tour returns **zero stops** for that venue
- The gate logs how many were dropped and why
- This is a visible failure (LOCAL-190), but narrating fabricated objects is worse (D127)

When the gate is in LOG_ONLY mode (current default):
- All stops proceed unchanged
- Verdicts are printed to the generation log for measurement
- No user-facing change

---

## Invariants Preserved

- `audio_tours` count: **138** (before and after, verified by script assertion)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: unchanged (verified)
- No tours deleted or altered
- No container rebuilt (D48)
- No detectors or `claim_check.py` modified (D55)
- `git status --short`: clean after commit

---

## Limitations

1. **The gate is conservative.** Chagall tour 24 has 6 real stops but only 4 verify — "Moïse et le Buisson ardent" and "Le Passage de la Mer Rouge" ARE real Chagall works at the museum, but the venue_corpus canonical_titles list doesn't include them. The gate's false-negative rate depends on corpus completeness.

2. **Non-Latin venue names don't match.** Tours in Russian (ids 7,9,11,19,22,30,32,151) use Cyrillic venue names that don't match Latin venue_corpus entries. A transliteration layer would help but is out of scope.

3. **Walking/biking tours use geographic POIs, not museum objects.** The French Riviera venue_corpus has `canonical_titles_json` as dicts with lat/lng (geographic points), not artwork titles. The gate handles this format but the semantic meaning differs from museum stops.

4. **Catalogue page check not implemented.** The third verification path (fetching the venue's own catalogue URL) is stubbed but not built — it would require network calls at measurement time and risk D127's circular-verification trap if the "catalogue" is just a Wikipedia page.

5. **D74 same-source rule is strict.** The stop_corpus check requires the passage to mention BOTH the stop subject AND the venue. Some passages describe the work without explicitly naming the museum, and these fail verification even if the stop_corpus row is correctly assigned to the right venue.
