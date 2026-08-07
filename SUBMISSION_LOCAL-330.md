##### READY FOR REVIEW

**Task:** LOCAL-330  
**Branch:** `kiro/local330-prolog-phrasing`  
**Commit:** `1d706fb`

---

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Replaced inline word-blocklist `_PROLOG_CATEGORY_WORDS` (~lines 9251–9279) with a module-level `_prolog_place()` function (~line 121). The function uses two anchored regexes: `_PROLOG_TOUR_PREFIX_RE` (strips `<category> tour in/of…` from start) and `_PROLOG_TOUR_SUFFIX_RE` (strips `<category> tour` from end). If neither matches, returns input unchanged. Inline call site reduced to `_prolog_place_name = _prolog_place(location)`. Local variable renamed `_prolog_place_name` to avoid shadowing the function. Museum branch (`_is_museum_prolog`) untouched. |
| `tests/test_local330_prolog_place_name.py` | Rewritten to import `_prolog_place` directly from `generate_tour_text` (LOCAL-324 pattern — no reimplementation). 26 tests: restaurant (4), walking (2), cycling (2), animal (3), museum non-regression (2), LEAD-mandated place names (6), edge cases (5), production wiring (2). |

---

## Verbatim evidence: all categories

```
=== AFTER FIX (current state) ===
  restaurant      | 'restaurant tour in Old Nice (Vieux Nice), France'      → 'Old Nice (Vieux Nice), France'
  walking         | 'walking tour in Paris, France'                         → 'Paris, France'
  cycling         | 'cycling tour of the French Riviera'                    → 'the French Riviera'
  bike            | 'bike tour in Amsterdam, Netherlands'                   → 'Amsterdam, Netherlands'
  camel           | 'camel tour in the Sahara Desert, Morocco'              → 'the Sahara Desert, Morocco'
  dogsled         | 'dogsled tour in Fairbanks, Alaska'                     → 'Fairbanks, Alaska'
  horseback       | 'horseback tour through Patagonia, Argentina'           → 'Patagonia, Argentina'
  museum          | 'Musée Matisse, Nice, France museum tour'               → 'Musée Matisse, Nice, France'
  food            | 'food tour in Bangkok, Thailand'                        → 'Bangkok, Thailand'
  self-guided     | 'self-guided walking tour in Edinburgh, Scotland'       → 'Edinburgh, Scotland'
```

## Verbatim evidence: LEAD-mandated place names (must be UNCHANGED)

```
  Hyde Park, London                        → 'Hyde Park, London'  ✓
  Central Park, New York                   → 'Central Park, New York'  ✓
  Golden Gate Park, San Francisco          → 'Golden Gate Park, San Francisco'  ✓
  Garden District, New Orleans             → 'Garden District, New Orleans'  ✓
  Boat Quay, Singapore                     → 'Boat Quay, Singapore'  ✓
  Car-free Zermatt, Switzerland            → 'Car-free Zermatt, Switzerland'  ✓
```

## Museum opening unchanged (LOCAL-286)

The museum branch (`if _is_museum_prolog:`) uses hardcoded example shape:
```
"You are about to explore the [venue name] in [city]."
```
It never references `_prolog_place_name` in its Part 1 instruction. The TOUR DATA line carries `_prolog_place_name` for metadata, which for museum input `"Musée Matisse, Nice, France museum tour"` yields `"Musée Matisse, Nice, France"` (clean).

## Deliberate break → tests go red

Sabotaged `_prolog_place()` to `return location` (pass-through):
```
FAILED tests/test_local330_prolog_place_name.py::TestRestaurantCategory::test_restaurant_tour_old_nice
FAILED tests/test_local330_prolog_place_name.py::TestRestaurantCategory::test_restaurants_tour_old_city
FAILED tests/test_local330_prolog_place_name.py::TestRestaurantCategory::test_food_tour_bangkok
FAILED tests/test_local330_prolog_place_name.py::TestRestaurantCategory::test_culinary_tour_lyon
FAILED tests/test_local330_prolog_place_name.py::TestWalkingCategory::test_walking_tour_paris
FAILED tests/test_local330_prolog_place_name.py::TestWalkingCategory::test_walking_tour_rome_neighborhoods
FAILED tests/test_local330_prolog_place_name.py::TestCyclingCategory::test_cycling_tour_french_riviera
FAILED tests/test_local330_prolog_place_name.py::TestCyclingCategory::test_bike_tour_amsterdam
FAILED tests/test_local330_prolog_place_name.py::TestAnimalTransport::test_camel_tour_sahara
FAILED tests/test_local330_prolog_place_name.py::TestAnimalTransport::test_dog_sled_tour_alaska
FAILED tests/test_local330_prolog_place_name.py::TestAnimalTransport::test_horseback_tour_patagonia
FAILED tests/test_local330_prolog_place_name.py::TestMuseumNotRegressed::test_museum_tour_nice
FAILED tests/test_local330_prolog_place_name.py::TestMuseumNotRegressed::test_gallery_tour_florence
FAILED tests/test_local330_prolog_place_name.py::TestEdgeCases::test_accented_place_preserved
FAILED tests/test_local330_prolog_place_name.py::TestEdgeCases::test_self_guided_tour
FAILED tests/test_local330_prolog_place_name.py::TestEdgeCases::test_walking_tour_hyde_park
=================== 16 failed, 10 passed ===================
```

Restored → 26 passed.

---

## Limitations

- The prefix/suffix regex does not handle multi-word categories joined by "and" (e.g. "food and wine tour in…"). Such inputs would pass through unstripped — the full request string would reach the slot. This has not been observed in production data.
- The "the" article is preserved when it leads the place after stripping (e.g. "the French Riviera", "the Sahara Desert"). This reads naturally in "a walking journey through the French Riviera" but could be considered noise for the TOUR DATA metadata line.
- Existing tour files in `tours/` are not rewritten (per instructions) — they retain the old phrasing as historical artifacts.
