##### READY FOR REVIEW

**Commit:** `cfc7451` (code), `cc07151` (this document)
**Branch:** `kiro/local339-stop-corpus-matching`

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | Rewrote `get_stop_corpus_for_tour` to match by stop_title first across all venue_names, with venue as tie-breaker. Added `_match_stop_title_first` and `_passage_count` helpers. Applied `_prolog_place` to strip tour-type prefixes. |
| `tour_rubric_scorer.py` | Three structural person-model guards: (1) locative-preposition guard before vocabulary context check, (2) leading-article guard for 2-word "The X" phrases, (3) title-exclusion strips leading prep/articles before comparing. Added "chez" to `_NOT_A_PERSON_RE`. |
| `tests/test_local339_corpus_and_person.py` | 15 tests covering both defects and D247 regression cases. All pass. |

---

## Design choice: stop-title-first vs venue-first

The old approach filtered `stop_corpus` rows by venue_name first, then matched stop titles within that set. This failed when the tour's venue string diverged from corpus venue_name values — e.g. "restaurant tour in Old Nice (Vieux Nice), France" doesn't match "Old Nice, Nice, France" even after ILIKE.

The new approach queries ALL corpus rows and matches by stop_title first (using the existing multi-strategy matching: exact, accent-folded, containment, word-overlap). Venue becomes a **tie-breaker** when the same stop_title exists under multiple venues (e.g. "Chez Palmyre" exists under 3 venues; prefer the one whose venue best matches the tour's clean venue string).

Trade-off: the new approach fetches all 117 corpus rows instead of ~10 for one venue. At 117 rows this is negligible. If corpus grows to thousands of rows, a title-indexed lookup would be better — but that's a future optimization.

---

## Verbatim evidence

### Defect 1 — Corpus found for Chez Pipo

```
BEFORE:
  Stop 4 (Chez Pipo): ground=1.0, corpus=True, people=['At Chez Pipo', 'Chez Palmyre', 'Old Nice', 'Palmyre Moni', 'The Socca']
  (corpus matched via venue 'restaurant tour in Old Nice (Vieux Nice), France' which has Chez Palmyre but NOT Chez Pipo)

AFTER:
  Stop 4 (Chez Pipo): ground=1.0, corpus=True, people=['Palmyre Moni']
  (corpus matched via title-first: found 10 passages under 'Old Nice, Nice, France', 4 after sludge filter)
```

Restaurant Stop 2 (La Tapenade) also improved:
```
BEFORE: ground=None, corpus=False  (not found under matched venue)
AFTER:  ground=1.0, corpus=True   (found via title-first across all venues)
```

Walking tour now finds corpus for 3/4 stops (was 0/4):
```
BEFORE: all stops ground=None, corpus=False
AFTER:  Cours Saleya=1.0, Nice Cathedral=1.0, Place Rossetti=1.0, Palais Lascaris=None
```

### Defect 2 — Person model

```
BEFORE Stop 4 named_people: ['At Chez Pipo', 'Chez Palmyre', 'Old Nice', 'Palmyre Moni', 'The Socca']
AFTER  Stop 4 named_people: ['Palmyre Moni']
```

Excluded by:
- `At Chez Pipo` → title-strip "At" → "Chez Pipo" matches stop title → excluded
- `Chez Palmyre` → `_NOT_A_PERSON_RE` matches "chez" → excluded
- `Old Nice` → preceded by "of" (locative preposition guard) → excluded
- `The Socca` → 2-word phrase starting with "The" (article guard) → excluded
- `Palmyre Moni` → preceded by "by" (agent preposition, not blocked) + "Established" in window → kept ✓

### D247 cases intact

```
LOCAL320_museum_8stop:
  Stop 1: people=['Andô Naoyuki']        ← detected (within longer title "L'Armure d'Andô Naoyuki")
  Stop 5: people=['Kenzo Tange', 'Toyohara Chikanobu', 'Ulysses Grant']  ← detected (within "Ulysses Grant au Japon")
```

### Filler / place guards intact

```
"Nice, a coastal city, offers…" → named_people: []     ✓
"a mix of laughter and clinking glasses…" → named_people: []  ✓
```

### Existing test suites

```
test_local333_fact_detector_nonmuseum.py: 34 passed
test_local331_groundedness_default.py: 13 passed
test_local339_corpus_and_person.py: 15 passed
```

---

## Before/after rescoring (all 4 of Michael's tours)

| Tour | Before | After | Δ |
|------|--------|-------|---|
| LOCAL336_museum_4stop | 91.0 | 91.0 | 0 |
| LOCAL336_restaurant_4stop | **62.5** | **56.25** | **−6.25** |
| LOCAL336_walking_4stop | 51.0 | 51.0 | 0 |
| LOCAL320_museum_8stop | 96.6875 | 96.6875 | 0 |

The restaurant tour drops 6.25 points because Stop 4 (Chez Pipo) was classified RICH on 8 phantom facts (5 false people); the honest classification is ADEQUATE on 4 real facts (1 person + 2 dates + 1 material). This is the correct outcome — the inflated score reflected phantom people, not real quality.

---

## stop_corpus row count

```
BEFORE: 117
AFTER:  117
```

No rows added, deleted, or modified.

---

## Limitations

1. **"Pan Bagnat" in Stop 3** remains a false person. It's a sandwich name that triggers the appositive detector ("Pan Bagnat, a classic Nicoise sandwich"). Fixing this would require either adding food terms to `_APPOSITIVE_PLACE_NOUN_RE` (food isn't a place) or a structural "thing" detector. The task scope was Stop 4 specifically; Stop 3 was not cited.

2. **Full-table scan in corpus matching.** The new approach fetches all 117 stop_corpus rows per tour. At current scale this is negligible (<1ms). If corpus grows significantly, an indexed title-lookup would be needed.

3. **"Juichimen Kannon" in museum 4-stop Stop 4** was previously counted as a person and is now excluded by the preposition guard ("the serene presence of Juichimen Kannon"). Kannon is a Buddhist deity, but the construction "presence of X" structurally marks X as an object reference, not a person-agent. The stop classification (ADEQUATE) is unchanged; overall score is unchanged.

4. **The preposition guard uses a restricted set** (locative prepositions: of, in, at, to, from, through, etc.) and deliberately excludes "by" (which identifies agents: "founded by X"). This means "stories of Palmyre Moni" would incorrectly block a person. In practice, tour text uses agentive constructions ("founded by", "created by") rather than "of" for people, so the risk is low.
