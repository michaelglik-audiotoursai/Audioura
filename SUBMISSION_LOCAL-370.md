# SUBMISSION_LOCAL-370.md

## Delivered Stop Headings (verbatim)

For `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA` requesting 8 stops:

1. **Le Lézard aux plumes d'or (The Lizard with Golden Feathers)** — Joan Miró, 1971
2. **Moses and Monotheism** — Salvador Dalí, 1974
3. **Au Soleil du Plafond** — Juan Gris with Pierre Reverdy, 1955

Three honest stops. Not eight. D275 requires this: an unsatisfiable scope produces
a shorter tour rather than backfilling from the venue-wide collection.

---

## Fix 1: Search term from full user phrase

**Problem**: `_exh_name_for_search` was set from `_exhibition_scope.get('requirements')`
which non-deterministically returned `"Unbound exhibition"` (truncated) instead of the
full `"Picasso, Miró, Dalí: Unbound exhibition"`.

**Fix**: Extract the search term from `location` (the raw user input), stripping the
`" at VENUE"` suffix using the venue name from intent. Falls back to `requirements`
only when stripping leaves nothing.

**Evidence**:
- `_title_similarity('Picasso, Miró, Dalí: Unbound exhibition', 'Picasso, Miró, Dalí: Unbound') = 0.80` → MATCHED
- `_title_similarity('Unbound exhibition', 'Picasso, Miró, Dalí: Unbound') = 0.23` → REJECTED (would have missed)

---

## Fix 2: Listing page must not match itself

**Problem**: `_title_similarity('Unbound exhibition', 'Exhibitions') = 0.383`, over
the 0.35 floor. The matcher accepted the index page's own heading as the exhibition
title.

**Fix (3 layers)**:
1. `_GENERIC_LISTING_TITLES` blocklist: "Exhibitions", "What's On", "Expositions", etc.
   in EN/FR/DE/ES/IT/NL — always score 0.0.
2. Self-URL rejection: if `best_match_url` equals the listing page URL, reject.
3. Name-like token requirement: when no name-like token (weight 2.0) matches, cap
   score at 0.20 (below 0.35 threshold). Safety net for novel generic titles.

**Red/green**:
```
REVERTED: _title_similarity("Unbound exhibition", "Exhibitions") = 0.3833 → ACCEPTED (BUG)
FIXED:    _title_similarity("Unbound exhibition", "Exhibitions") = 0.0000 → REJECTED
```

---

## Fix 3: Plausibility gate on structured-checklist extractions

**Problem**: `extract_works_from_exhibition_page` reported 17 "works" from navigation
labels and image captions. `structured_checklist` succeeded on garbage, so `prose_llm`
never ran.

**Fix**: `plausibility_gate(works)` checks each entry:
- Artist is a civilisation/place/people → implausible (`_NOT_ARTIST_PATTERNS`)
- Title is a gallery/section name → implausible (`_GALLERY_SECTION_PATTERNS`)
- Title begins "Detail of" / "Detail fo" → implausible (`_CAPTION_PREFIX_PATTERN`)

**Threshold**: >50% implausible → discard entire extraction, fall through to `prose_llm`.

**Justification for 50%**: A real exhibition checklist might have 1-2 ambiguous entries
(OCR artifacts, unusual attributions). But a page where the majority of "works" are
section headings is clearly mis-parsed. 50% is the strictest threshold that allows for
moderate noise in real checklists while rejecting the MFA listing page case (100%
implausible).

**Red/green**:
```
REVERTED (no gate): 6 garbage works passed through → delivered as exhibition stops
FIXED (gate active): 0 works survive → falls through to prose_llm → 3 real works
```

Entries rejected by the gate:
- ✗ 'Art of Ancient Greece' by 'Rome, and the Byzantine Empire' — gallery section + civilisation-as-artist
- ✗ 'Japanese Garden' by 'Tenshin-en' — section name
- ✗ 'Detail of painting' by 'Water Lilies, by Monet' — image caption
- ✗ 'Detail fo Chinese sculpture' by 'Guanyin' — image caption (with typo)
- ✗ 'Arts of Korea' by '' — gallery section
- ✗ 'Mask (Hudoq), made' by 'Dayak peoples in Borneo' — peoples-as-artist

---

## Fix 4: R4 replenishment suppressed for exhibition-scoped requests

**Problem**: After D1v2 correctly rejected 15/16 garbage works, R4 backfilled 7
venue-wide works to hit the 8-stop target. The final stops were alphabetical
(Adam, Adoration, An Italian, Ancient, Ankhhaf…) — an index scrape, not a show.

**Fix**: When `_exhibition_scope is not None`:
1. Set `_r4_suppressed_by_scope = True`
2. Cap `total_stops = len(poi_list)` (honest degradation)
3. Add `not _r4_suppressed_by_scope` to the R4 while-loop condition

**Red/green**:
```
REVERTED: R4 loop condition = True → R4 FIRES, backfills 5-7 venue-wide works
FIXED:    R4 loop condition = False → R4 SUPPRESSED, 3 stops delivered honestly
```

Test `test_r4_while_condition_false_when_suppressed` directly asserts the while
condition is False when scoped. Reverting the `not _r4_suppressed_by_scope` guard
makes it True.

---

## Tests

25 tests in `tests/test_local370_exhibition_listing_false_match.py`:
- `TestSearchTermFullPhrase` (3 tests) — Fix 1
- `TestListingPageRejection` (8 tests) — Fix 2
- `TestPlausibilityGate` (9 tests) — Fix 3
- `TestR4SuppressionForScopedRequests` (4 tests) — Fix 4
- `TestFullPipeline` (1 integration test) — end-to-end listing→detail

New fixture: `tests/fixtures/mfa_exhibitions_listing.html`

All 247 tests pass (exhibition-related suites + museum bounds).

---

## Limitations

1. The plausibility gate's pattern lists are not exhaustive. A museum with unusual
   gallery naming conventions could produce false positives. The 50% threshold
   provides tolerance.

2. Fix 1's venue-suffix stripping uses `" at <first-comma-segment-of-venue>"` regex.
   If a venue name starts with a word that's also part of the exhibition name (unlikely
   but possible), the stripping could be too aggressive. The fallback to `requirements`
   catches this.

3. The `_GENERIC_LISTING_TITLES` blocklist needs maintenance as new venues in new
   languages are added. Currently covers EN/FR/DE/ES/IT/NL.

4. R4 suppression is absolute for scoped requests. If a future change makes it possible
   to replenish from within the same exhibition (more works discovered later), that
   should be allowed — but venue-wide is not.
