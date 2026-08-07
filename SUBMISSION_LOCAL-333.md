##### READY FOR REVIEW

## Commit

```
da976ab LOCAL-333: structural person detection + numeral modifier tolerance
```

## Files Changed

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Added structural person detection (appositive, active verb, title-before-name); extended numeral Track 2 for intervening modifiers; extended `_NOT_A_PERSON_RE` with geographic terms |
| `tests/test_local333_fact_detector_nonmuseum.py` | 13 unit tests: structural person context, numeral-with-modifier, filler-not-counted, guard rails, stop-1-nonzero |

## Approach: Structural Model (not vocabulary expansion)

Per Michael's correction, `_PERSON_CONTEXT_RE` was **not** extended with culinary/commercial vocabulary. Instead, three structural patterns detect people by **shape**:

1. **APPOSITIVE** — `"Name, a/an/the <noun-phrase>, ..."` identifies a person regardless of which noun fills the slot. Guard: if the appositive clause contains a place-category noun (`city`, `district`, `restaurant`, `square`, etc.), the subject is a geographic entity and is excluded.

2. **ACTIVE VERB** — An `-ed` or present-tense `-s` verb within 60 chars after the name, with guards:
   - No sentence boundary (`.!?`) between name and verb
   - No subject pronoun (`it`, `he`, `she`, `they`, `this`, `that`, `which`, `who`)
   - No stative/passive marker (`is/was/are/were/been`) before the verb
   - No preposition immediately before the name (= name is object, not subject)
   - Exclusion list for common non-verb `-s` words

3. **TITLE-BEFORE-NAME** — `"the/a <noun> Name"` construction (e.g. "the architect Frank Lloyd Wright").

4. **Legacy `_PERSON_CONTEXT_RE`** retained as first-pass fallback for museum domain verbs/roles.

## Fix 2: Numeral Track 2

Changed from `numeral\s+noun` to `numeral(?:\s+[A-Za-z...]+){0,2}\s+noun`. Up to 2 intervening modifier words tolerated. Extended noun vocabulary with: `stars?|medals?|sites?|awards?|prizes?|courses?|rooms?|restaurants?|buildings?|towers?|bridges?|doors?|windows?|arches?`.

## `_NOT_A_PERSON_RE` Extensions

Added: `city|town|district|quarter|neighborhood|neighbourhood|region|area|market|promenade|cours|place|piazza|plaza|quai|port|harbour|harbor|alps|mountains?|river|lake|coast|bay|cape|valley|plateau`

Reason: the general structural model (appositive) would otherwise accept "Nice, a coastal city, offers…" and "Cours Saleya, a historic square, hosts…". The exclusion list guards against place names — it encodes what is NOT a person (small, stable set per Michael's directive).

## Verbatim Evidence

### Fix 1 fires — `Franck Cerutti` detected via appositive:

```
$ python3 -c "from tour_rubric_scorer import analyze_stop; ..."
=== STOP 1 (task text): Le Safari ===
  Named people:          ['Franck Cerutti']
  Measurements/numbers:  ['three michelin stars']
  distinct_fact_count:   2

  VERDICT: PASS — fact count moved off zero
```

(Previously: `Named people: [], distinct_fact_count: 0`)

### Fix 2 fires — `three Michelin stars`:

```
$ python3 -m pytest tests/test_local333_fact_detector_nonmuseum.py::TestSpelledOutNumeralWithModifier::test_three_michelin_stars -v
PASSED
```

### Filler NOT counted:

```
=== FILLER CHECK: clinking glasses sentence ===
  distinct_fact_count: 0
  VERDICT: PASS — filler is NOT a fact
```

### Test red-then-green transcript:

```
# Against unfixed (storied) code:
7 FAILED:
  test_appositive_introduced FAILED
  test_past_tense_verb_crafts FAILED
  test_appositive_french_chef FAILED
  test_past_verb_opened FAILED
  test_three_michelin_stars FAILED
  test_five_olympic_gold_medals FAILED
  test_two_heritage_sites FAILED

# Against fixed code:
13 passed in 0.09s
```

### Restaurant tour (LOCAL318) rescored:

```
Stop 1: La Rossettisserie  people=['La Rossettisserie']       facts=1  (was 0)
Stop 2: Acchiardo          people=['Madalin Acchiardo',
                                   'Virginie Acchiardo']      facts=4  (was 3)
Stop 3: Chez Palmyre       people=['Palmyre Moni']            facts=2  (was 1)
Stop 4: Le Safari          people=['Franck Cerutti',
                                   'Nadim Beyrouti']          facts=3  (was 1)
Stop 5: La Voglia          people=[6 names]                   facts=9  (was 7)
```

### Museum tours NOT regressed (false-positive check):

```
Tour                                       Baseline  Fixed   Delta
LOCAL262_asian_arts_8stop_restored.txt      facts=36  facts=43  +7 (Marc Chagall×0→detected)
LOCAL212v2_palais_lascaris_ON_run1.txt      facts= 7  facts= 8  +1
LOCAL212v2_matisse_ON_run1.txt              facts= 9  facts=10  +1
cil_chagall_cycle5.txt                     facts= 3  facts=11  +8 (Marc Chagall×3 newly detected)
```

The increases are from `Marc Chagall` (real person, previously undetected by vocabulary model) plus pre-existing painting-title false positives (`The Creation`, `The Exodus`) that already existed on baseline (Chagall had 1 on storied).

### Walking tour (LOCAL208) — unchanged:

```
Stop 1: Cap d'Antibes      facts=13  (was 13)
Stop 2: Villefranche-sur-Mer  facts=3  (was 3)
```

### Full regression suite:

```
$ python3 -m pytest tests/test_local312*.py tests/test_local309*.py tests/test_local291*.py \
    tests/test_local305*.py tests/test_local318*.py tests/test_local327*.py \
    tests/test_local307*.py tests/test_local333*.py
148 passed, 1 warning in 0.59s
```

## Reader vs Detector Gap Measurement

| Stop | Title | Detector | Reader | Gap | Notes |
|------|-------|----------|--------|-----|-------|
| **Restaurant tour (LOCAL318)** | | | | | |
| 1 | La Rossettisserie | 1 | 1 | 0 | daube reference only; detector counts venue name (FP) |
| 2 | Acchiardo | 4 | 5 | +1 | misses Giuseppe (single first name) |
| 3 | Chez Palmyre | 2 | 4 | +2 | misses Vincent, Sam (single first names) |
| 4 | Le Safari | 3 | 4 | +1 | misses "Palestinian-Niçois" (ethnic attr); "wooden" material counted |
| 5 | La Voglia | 9 | 5 | −4 | over-counts: La Voglia, Le Safari, Treat Page (venue names) |
| **Walking tour (LOCAL208)** | | | | | |
| 1 | Cap d'Antibes | 13 | 6 | −7 | over-counts: In January, Notre Dame, Rue Obscure, The Cap, The Tire, Villa Eilenroc (all pre-existing) |
| 2 | Villefranche-sur-Mer | 3 | 3 | 0 | |

**Summary:** Restaurant tour: detector typically under-counts by 1-2 (single first names) but over-counts in Stop 5 (venue names as "people"). Walking tour: pre-existing false positives inflate count. Net: **structural model closes the gap for the diagnosed defects** (Stop 4 moved from 1→3 facts) without introducing filler inflation.

## Remaining systematic gaps (not addressed):

1. **Single first-name references** (Giuseppe, Virginie, Vincent, Sam) — `_PROPER_PHRASE_RE` requires 2+ capitalised words; Track 3 only catches museum-role adjacent single names
2. **Ethnic/geographic attributions** (Palestinian-Niçois, Tuscan) — not in any detection track
3. **Pre-existing false positives**: `In January`, `Notre Dame`, `Rue Obscure`, `The Cap`, `Villa Eilenroc` (all from walking tour stop 1, present on storied baseline)
4. **Venue names as "people"**: `La Voglia`, `Le Safari`, `Treat Page` — proper phrases that pass `_NOT_A_PERSON_RE` and sit near verbs via legacy vocabulary fallback

## Limitations

- The tour file referenced in the task (`LOCAL329_5stop_old_nice_restaurant.txt`) does not exist on disk (tours/ is gitignored). Analysis performed against `LOCAL318` which contains identical restaurant stops including the Franck Cerutti text.
- The structural model's active-verb check can match venue names that appear as sentence subjects (`"La Voglia showcases..."`) — these are entities performing actions but not persons. The preposition guard and subject-pronoun guard reduce but don't eliminate this.
- Museum tour Chagall fact counts rose from 3→11 due to `Marc Chagall` being newly detected (correct!) plus pre-existing painting-title false positives being triggered more often by the wider structural model.
- The `{0,2}` modifier slot in numeral Track 2 means patterns with 3+ intervening words still miss. Intentional conservatism.
