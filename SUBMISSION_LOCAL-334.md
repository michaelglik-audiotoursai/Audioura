##### READY FOR REVIEW

**Task:** LOCAL-334  
**Branch:** kiro/local334-museum-object-questions  
**Commit:** 4cee78d  

## Per-file summary

| File | Change |
|------|--------|
| `interpretive_enrichment.py` | Museum template rewritten to target the object with venue as context; `venue_name` parameter added to `build_interpretive_questions` and `enrich_stop_interpretive`; venue_name threaded from `enrich_verified_stops` down; venue name shortened (strip parenthetical, comma-suffix); museum/gallery without venue_name falls to default template. |
| `tests/test_local334_museum_object_questions.py` | 12 tests: 5 museum-specific, 5 regression (restaurant, geographic_area, cycling, default, monument), 2 parameter-threading. |

## Evidence

### Before (unfixed code)
```
Museum:
  Q: What is notable about Kannon a mille bras in Nice, France?
  Q: What are the most significant works and collections at Kannon a mille bras?
```

### After (fixed code)
```
Museum:
  Q: What is notable about Kannon a mille bras at Musee des Arts Asiatiques, Nice?
  Q: Who created Kannon a mille bras, what does it depict, and how did it come to Musee des Arts Asiatiques?
```

### All five venue kinds — no regression
```
=== MUSEUM (with venue) ===
  What is notable about Kannon a mille bras at Musee des Arts Asiatiques, Nice?
  Who created Kannon a mille bras, what does it depict, and how did it come to Musee des Arts Asiatiques?

=== RESTAURANT ===
  What is interesting about Le Safari restaurant in Nice, France?
  Who are notable people associated with Le Safari in Nice and what did they do there?

=== GEOGRAPHIC_AREA (default fallback) ===
  What is interesting or notable about Cap d Antibes in French Riviera, France?
  Who are notable people associated with Cap d Antibes in French Riviera and what is its history?

=== CYCLING (default fallback) ===
  What is interesting or notable about Eze Village in French Riviera, France?
  Who are notable people associated with Eze Village in French Riviera and what is its history?

=== UNKNOWN (default fallback) ===
  What is interesting or notable about Some Place in Paris, France?
  Who are notable people associated with Some Place in Paris and what is its history?
```

### Tests fail against unfixed code (8 failures)
```
tests/test_local334_museum_object_questions.py::TestMuseumObjectQuestions::test_museum_questions_reference_object_not_venue_as_subject FAILED
tests/test_local334_museum_object_questions.py::TestMuseumObjectQuestions::test_museum_questions_ask_about_creation_and_significance FAILED
tests/test_local334_museum_object_questions.py::TestMuseumObjectQuestions::test_museum_venue_appears_as_context_not_subject FAILED
tests/test_local334_museum_object_questions.py::TestMuseumObjectQuestions::test_museum_without_venue_name_falls_to_default FAILED
tests/test_local334_museum_object_questions.py::TestMuseumObjectQuestions::test_venue_name_stripped_to_short_form FAILED
tests/test_local334_museum_object_questions.py::TestOtherKindsNotRegressed::test_restaurant_unchanged FAILED
tests/test_local334_museum_object_questions.py::TestVenueNamePassthrough::test_enrich_stop_interpretive_accepts_venue_name FAILED
tests/test_local334_museum_object_questions.py::TestVenueNamePassthrough::test_build_interpretive_questions_accepts_venue_name FAILED
```

### Tests pass against fixed code (23 total: 11 LOCAL-332 + 12 LOCAL-334)
```
23 passed in 0.09s
```

### Non-dining regression (LOCAL-320): 8 passed
```
test_2stop_riviera_cycling_classification PASSED
test_2stop_riviera_cycling_gate PASSED
test_8stop_riviera_cycling_gate PASSED
test_museum_classification PASSED
test_8stop_museum_gate PASSED
test_geographic_area_never_calls_nominatim PASSED
test_institution_never_calls_nominatim PASSED
test_dining_does_call_nominatim PASSED
```

### Real enrichment on museum objects
Questions generated correctly for 3 stops (Kannon a mille bras, Robe de pretre taoiste, Statue de Bouddha). Search could not execute because SERP_API_KEY is not set in the environment. This is expected — the API key is not committed to the repo and must be supplied at runtime.

### stop_corpus count: 117 (unchanged)

### Verification of other kinds (geographic_area, cycling)
`geographic_area` and `cycling` are not in `kind_map`, so they fall to the `'default'` template: "What is interesting or notable about {name} in {city}, {country}?" This is correct because geographic_area/cycling stops ARE places (Cap d'Antibes, Eze Village), not objects inside a container. No change needed.

## Limitations

- Real enrichment (Serper search + verification) could not be demonstrated because SERP_API_KEY is not available in the environment. The question generation logic is fully tested and demonstrated; the search+verify pipeline is unchanged from LOCAL-332.
- The `gallery` template still asks "Who are famous artists exhibited at {name}" — this would be similarly wrong if gallery stops were individual artworks inside a gallery. However, no gallery tours exist in the database currently, and the template is appropriate if the stop IS the gallery. Left as-is per scope.
- Venue name extraction from the full venue_name string uses a simple "first part before comma, strip parentheticals" heuristic. This works for the existing data format ("Musee des Arts Asiatiques (Asian Art Museum), Nice, France") but may need refinement for other naming patterns.
