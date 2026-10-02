# SUBMISSION_LOCAL-461.md — Interrogation Matrix

**Agent:** Mac Mini Kiro  
**Branch:** LOCAL-461-interrogation-matrix  
**Base:** storied (cab2b76)

## What was built

`interrogation_matrix.py` — builds the interrogation matrix from a stop description alone.
No network, no API key, no corpus, deterministic.

### Design decisions

1. **`artist` (principal) extraction uses story_opportunity_scan handles** rather than regex
   patterns alone. The most-prominent proper-noun handle by sentence count IS the principal.
   This catches "Salvador Dalí" even though the text never says "artist Dalí" — it just talks
   about him the most. Regex patterns are the fallback for walking tours where "designed by"
   / "architect" phrases are the signal.

2. **`credit_line` selection imports story_opportunity_scan.measure()** and picks the
   highest-value non-DEVELOPED handle, preferring FLAT > MENTIONED > DANGLING, excluding
   handles that duplicate other filled slots (canonical_title, artist, publisher, printed_by,
   venue, medium). This prevents the credit_line from being redundant.

3. **The canonical_title ladder** is implemented: exhibit → exhibition → museum → city →
   state → country. In practice all 9 test stops resolve at "exhibit" (the stop heading).
   The `rung` field records where it landed.

4. **Provenance cells** follow story_record_extract's pattern: `{value, status, source, rung}`
   with status ∈ {STRUCTURAL, CLAIMED, DERIVED, ABSENT}. CLAIMED means "the text asserts it
   and nothing has checked it" — specifically, publisher = "The Hogarth Press" is CLAIMED, which
   is correct because it is a fabrication (D427).

5. **ABSENT is honest.** Walking tour stops correctly produce ABSENT for `printed_by`.
   Fruitlands stops produce ABSENT for `medium` (no exhibition named). The code never invents
   fillers.

6. **Handles with newlines are excluded** — story_opportunity_scan's proper-noun regex
   sometimes captures multi-line structural artifacts (e.g. "Pub Atmosphere\n\nOperational
   Details") from the walking tour format.

7. **Non-English title detection** uses a simple heuristic: common French/German/Italian words
   (du, de, les, au, plafond, etc.) in the title indicate it's not English, so english_title
   becomes ABSENT rather than repeating the foreign title.

## Acceptance criteria verification

### Criterion 1: MFA stop 2 worked example

```
canonical_title = Moses and Monotheism          STRUCTURAL [exhibit]
english_title   = Moses and Monotheism          STRUCTURAL
artist          = Salvador Dalí                  CLAIMED
publisher       = The Hogarth Press              CLAIMED
printed_by      = (ABSENT)
credit_line     = Sigmund Freud                  DERIVED (story_opportunity_scan/FLAT)
medium          = Picasso, Miro, Dali: Unbound   STRUCTURAL
venue           = Museum of Fine Arts, Boston     STRUCTURAL
```

Both artist and publisher are CLAIMED — the text asserts them, nothing has checked them.
Publisher "The Hogarth Press" is the known fabrication (D427/D435).

### Criterion 2: Fruitlands (no exhibition scope)

All 3 stops: `medium = ABSENT`, `canonical_title` resolves at exhibit rung.
The matrix does not require an exhibition to exist.

### Criterion 3: Beacon Hill (walking tour)

All 3 stops: `canonical_title` = the place, `artist` = person in charge (architects),
`venue` = "Beacon Hill, Boston", `printed_by` = ABSENT (correct, not invented).

### Criterion 4: credit_line is real and never DEVELOPED

All 9 stops that produce a credit_line have it sourced from story_opportunity_scan handles.
State is FLAT or MENTIONED or DANGLING, never DEVELOPED.

### Criterion 5: Coverage table

```
  museum_exhibition         avg=1.0 ABSENT per stop  [0, 1, 2]
  museum (no exhibition)    avg=4.3 ABSENT per stop  [4, 5, 4]
  walking                   avg=3.0 ABSENT per stop  [3, 3, 3]
```

High ABSENT count for Fruitlands is honest — those stops genuinely don't name publishers,
printers, venues, or exhibitions.

## Test outputs

### Passing (21 of 21):
```
  PASS  test_all_slots_have_provenance
  PASS  test_beacon_artist_is_person_in_charge
  PASS  test_beacon_canonical_title_is_place
  PASS  test_beacon_printed_by_absent
  PASS  test_beacon_venue_is_city
  PASS  test_build_matrix_callable_plain_string
  PASS  test_credit_line_never_developed_all_stops
  PASS  test_fruitlands_artist_claimed
  PASS  test_fruitlands_canonical_title_at_exhibit
  PASS  test_fruitlands_generalises_without_exhibition
  PASS  test_fruitlands_medium_absent
  PASS  test_mfa_stop1_gloss
  PASS  test_mfa_stop2_artist_is_claimed
  PASS  test_mfa_stop2_canonical_title
  PASS  test_mfa_stop2_credit_line_not_developed
  PASS  test_mfa_stop2_english_title
  PASS  test_mfa_stop2_medium_is_exhibition
  PASS  test_mfa_stop2_publisher_is_claimed
  PASS  test_mfa_stop2_venue
  PASS  test_mfa_stop3_french_title_no_english
  PASS  test_no_network_no_key
```

### Neutralized (15 fail, proving the suite can fail):
```
  PASS  test_all_slots_have_provenance
  FAIL  test_beacon_artist_is_person_in_charge: artist should be populated for walking tour
  FAIL  test_beacon_canonical_title_is_place: Expected a place name, got ''
  PASS  test_beacon_printed_by_absent
  FAIL  test_beacon_venue_is_city: Beacon Hill stop 1: venue should be city, got ''
  PASS  test_build_matrix_callable_plain_string
  PASS  test_credit_line_never_developed_all_stops
  FAIL  test_fruitlands_artist_claimed: Fruitlands stop 1: artist should be populated
  FAIL  test_fruitlands_canonical_title_at_exhibit: rung should be 'exhibit', got ''
  FAIL  test_fruitlands_generalises_without_exhibition
  PASS  test_fruitlands_medium_absent
  FAIL  test_mfa_stop1_gloss
  FAIL  test_mfa_stop2_artist_is_claimed: artist should be CLAIMED, got ABSENT
  FAIL  test_mfa_stop2_canonical_title: Expected 'Moses and Monotheism', got ''
  FAIL  test_mfa_stop2_credit_line_not_developed: credit_line should not be ABSENT
  FAIL  test_mfa_stop2_english_title
  FAIL  test_mfa_stop2_medium_is_exhibition: Expected 'Unbound', got ''
  FAIL  test_mfa_stop2_publisher_is_claimed: publisher should be CLAIMED, got ABSENT
  FAIL  test_mfa_stop2_venue: Expected MFA venue, got ''
  FAIL  test_mfa_stop3_french_title_no_english
  PASS  test_no_network_no_key

  6 passed, 15 failed, 21 total
```

## Files created

- `interrogation_matrix.py` — the module (CLI + library)
- `test_local461_interrogation_matrix.py` — acceptance suite
- `SUBMISSION_LOCAL-461.md` — this file

## Files NOT modified

- Tour files (fixtures)
- story_opportunity_scan.py, story_record_extract.py, story_material_check.py
- story_writer.py, story_sweep.py, story_claim_lab.py
- DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md
- story_lab_state/ directory
