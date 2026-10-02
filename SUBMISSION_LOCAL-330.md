##### READY FOR REVIEW

## Commit

`6689764` — LOCAL-330: replace category-word list with tour+preposition anchor

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Removed `_PROLOG_CATEGORY_ALTERNATION` (30-word blocklist). Replaced `_PROLOG_TOUR_PREFIX_RE` with `^.+?\btours?\s*(?:in\|of\|through\|around\|across\|along\|,)\s*` — anchors on `tour` + preposition, not category word. Replaced `_PROLOG_TOUR_SUFFIX_RE` with dash-form (` - <words> tour`) and single-word form (` <word> tour`). Updated `_prolog_place()` to apply suffix after successful prefix strip (handles compound strings like Michael's). |
| `tests/test_local330_prolog_place_name.py` | Added `TestMultiWordCategories` class (8 tests: dog sledding, horse riding, hot air balloon, food and wine, street art, plus Michael's 3 real request strings). Added edge cases: Tours France, Tour Eiffel, Museum Island, Safari Park. Total: 38 tests, all importing production `_prolog_place` directly. |

## Evidence: multi-word categories stripped correctly

```
"dog sledding tour in Big Lake, Alaska"       → "Big Lake, Alaska"
"horse riding tour of Patagonia"              → "Patagonia"
"hot air balloon tour of Cappadocia"          → "Cappadocia"
"food and wine tour of Tuscany"               → "Tuscany"
"street art tour of Lisbon"                   → "Lisbon"
"dogsled tour in Fairbanks, Alaska"           → "Fairbanks, Alaska"
```

## Evidence: place names unchanged

```
"Hyde Park, London"                → "Hyde Park, London"
"Central Park, New York"           → "Central Park, New York"
"Golden Gate Park, San Francisco"  → "Golden Gate Park, San Francisco"
"Garden District, New Orleans"     → "Garden District, New Orleans"
"Boat Quay, Singapore"             → "Boat Quay, Singapore"
"Car-free Zermatt, Switzerland"    → "Car-free Zermatt, Switzerland"
"Tours, France"                    → "Tours, France"
"Tour Eiffel, Paris"               → "Tour Eiffel, Paris"
"Museum Island, Berlin"            → "Museum Island, Berlin"
"Safari Park, Nairobi"             → "Safari Park, Nairobi"
```

## Evidence: Michael's real request strings from audio_tours

```
"Camelback riding tour in Abu Dhabi desert, UAE - museum Tour"  → "Abu Dhabi desert, UAE"
"dog ridding tour, Big Lake, AK - Dog Sledding Tour"            → "Big Lake, AK"
"Camel tour in a desert of Abu Dhabi, UAE - museum Tour"        → "a desert of Abu Dhabi, UAE"
```

## Evidence: original defect case

```
"restaurant tour in Old Nice (Vieux Nice), France"  → "Old Nice (Vieux Nice), France"
```

## Evidence: museum unchanged (LOCAL-286)

Museum prolog uses a separate branch (`_is_museum_prolog`) that does not reference `_prolog_place_name` in its Part 1 instruction. The suffix form still strips cleanly:

```
"Musée Matisse, Nice, France museum tour"           → "Musée Matisse, Nice, France"
"Uffizi Gallery, Florence, Italy museum tour"       → "Uffizi Gallery, Florence, Italy"
```

## Evidence: deliberate break turns tests red

Sabotaged `_prolog_place` by inserting `return location` at the top:

```
24 failed, 14 passed
```

Tests that pass are the "unchanged" assertions (correct — a no-op function leaves inputs alone). All stripping tests fail. Restored → 38 passed.

## Test run

```
38 passed, 1 warning in 0.16s
```

## Limitations

- The prefix regex uses `.+?` (non-greedy) which matches the *first* occurrence of `\btour` + preposition in the string. A pathological input like `"tour in tour of Paris"` would strip `"tour in "` and return `"tour of Paris"`. No real request strings have this shape.
- The suffix single-word form (`\s+\w+\s+tours?$`) handles only one word before "tour". A suffix like "food and wine tour" (multi-word suffix at end without dash) would not be stripped. In practice, Michael's multi-word suffixes always appear after a dash separator, which the dash form handles.
- `_prolog_place` strips "a " / "the " from prefix results only when they are part of the preposition chain (e.g. "tour in a desert of Abu Dhabi" → "a desert of Abu Dhabi"). The article is left in; it reads naturally in prose ("a walking journey through a desert of Abu Dhabi").
