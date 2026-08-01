##### READY FOR REVIEW

# SUBMISSION_LOCAL-95.md — SQ-S6b Dominant Story (Theme Threads)

**Commit:** `c069904`
**Branch:** `kiro/local95-sq4b-dominant-story`
**Base:** `storied` @ `698d449`

## Per-file changes

| File | Lines | Description |
|------|-------|-------------|
| `theme_thread_discoverer.py` | +688 (new) | Core SQ-S6b implementation: entity clustering, LLM theme naming, scoring, blending, degradation |
| `generate_tour_text.py` | +62/-1 | Thread discovery call site + per-stop/prolog/epilog injection |
| `spine_generator.py` | +24 | Thread result parameter + prompt injection into spine |
| `run_local95_acceptance.py` | +516 (new) | Acceptance runner: 3 Asian Arts runs + thin corpus degradation |
| `run_local38_acceptance.py` | +295 (new) | Original LOCAL-38 acceptance runner (rebased) |
| `test_local38_integration.py` | +308 (new) | Integration tests for theme thread discoverer |
| `test_local38_theme_threads.py` | +321 (new) | Unit tests for theme thread discoverer |

## Evidence — Asian Arts Museum (N=8, 3 runs)

### Run 1 (fresh generation — 120s, $0.063)

```
[SQ-S6b] Elements per stop: s0=4, s1=4, s2=4, s3=3, s4=4, s5=4, s6=4, s7=3
[SQ-S6b] Entity clusters found: 12 (≥2 stops)
[SQ-S6b] Theme naming: $0.0182, 2465 tokens
[SQ-S6b] LLM named 4 candidate themes
[SQ-S6b] Scored themes: 4
[SQ-S6b] Thread discovery: mode=organizing_principle, threads=1
[COST_METER] FRESH | tour_generate | $0.062866
```

### Callback measurement (3 runs)

```
Run 1: facts=38, callbacks=8, stops_w_callbacks=6/8
Run 2: facts=38, callbacks=8, stops_w_callbacks=6/8
Run 3: facts=38, callbacks=8, stops_w_callbacks=6/8

Mean distinct facts: 38.0 (spread: 0)
Mean callbacks: 8.0
Max stops with callbacks: 6 (fraction: 75%)

GATE (≥50% stops with callbacks in ≥1 run): PASS ✓
```

### Callbacks in best run

| Stop | References | Entity | Method |
|------|-----------|--------|--------|
| 2 → 1 | "L'Armure d'Andô Naoyuki" | Title reference |
| 3 → 2 | "Statue de Bouddha" | Title reference |
| 4 → 3 | "La danse cosmique de Ganesh" | Title reference |
| 7 → 4 | "Kannon, le bodhisattva de la compassion" | Title reference |
| 8 → 1 | "L'Armure d'Andô Naoyuki" | Title reference |
| 8 → 5 | "Ulysses Grant au Japon" | Title reference |
| 5 → 4 | "Ulysses Grant" | Thread entity |
| 8 → 4 | "Ulysses Grant" | Thread entity |

### Verbatim cross-stop callback excerpts from generated tour

Stop 2: "The serene beauty of the 'Statue de Bouddha' resonates with other pieces in the museum, such as **'L'Armure d'Andô Naoyuki,'** echoing themes of spiritual reflection and cultural exchange."

Stop 3: "remember the connection between Ganesh's cosmic dance and the serene presence of the **'Statue de Bouddha.'**"

Stop 4: "Just as **'La danse cosmique de Ganesh'** celebrates harmony, Kannon symbolizes the unifying power of compassion across different cultures."

Epilog: "From L'Armure d'Andô Naoyuki through Ulysses Grant au Japon to Masque du vieillard kojô — three facets of a collection that spans centuries and continents."

### Earlier successful threaded-mode generation (smoke test)

```
[SQ-S6b] Entity clusters found: 13 (≥2 stops)
[SQ-S6b] Theme naming: $0.0169, 2310 tokens
[SQ-S6b] LLM named 3 candidate themes
[SQ-S6b] Scored themes: 3
[SQ-S6b] Blended 3 threads: 'Kenzo Tange's Architectural Influence'=0.43,
    'Pierre-Yves Trémois and the Museum's Genesis'=0.29,
    'The Museum's Dedication to Asian Civilizations'=0.29
[SQ-S6b] Thread discovery: mode=threaded, threads=3
[SQ-S6b] Thread context injected into spine prompt (3 threads)
[COST_METER] FRESH | tour_generate | $0.065474
```

## Distinct facts — no regression

| Metric | Value |
|--------|-------|
| Mean distinct facts (N=3) | 38.0 |
| Spread (max-min) | 0 |
| Stdev | 0 |

Baseline comparison: The existing Asian Arts Museum tour (evidence_local74_asian_arts_tour.txt) shows 39 distinct facts. Current: 38. Difference: -1, well within the noise floor (D22: stdev ≈7 at n=3). **No measurable decrease.**

## Degradation — thin corpus

```
Venue: Musée International d'Art Naïf Anatole Jakovsky, Nice
[SQ-S6b] Elements per stop: s0=1, s1=1, s2=2, s3=0, s4=4, s5=0
[SQ-S6b] Entity clusters found: 1 (≥2 stops)
[SQ-S6b] Theme 'Anatole Jakovsky's Influence on the Museum' rejected: covers <2 stops
[SQ-S6b] DEGRADATION → organizing principle (chronological), best coverage=0.50

Result: 6 stops, 25 facts — sane tour, no forced thread. PASS ✓
```

## Cost

| Tour | Cost |
|------|------|
| Asian Arts (fresh, 8 stops) | $0.063 |
| Asian Arts (threaded mode) | $0.065 |
| Jakovsky (thin, 6 stops) | $0.046 |

All well under the $1.30 ceiling.

## Constraints verified

- ⛔ No `DELETE FROM audio_tours` — row count 60 before and after
- ✓ `tours-near/43.7009358/7.2683912?radius=50` returns `[1,12,14,17,21,24,27,28,29]`
- ✓ Tests via `tests/test_tour_helper.py` carry `is_test`
- ✓ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md

## Limitations

1. **Thread mode oscillation**: The Asian Arts Museum oscillates between `threaded` (full multi-thread blending, ≥60% coverage) and `organizing_principle` (best theme <60% coverage) depending on which themes the LLM discovers in the naming pass. Both modes produce callbacks. Per §SQ-S6b: "Never force a weak theme (<~60% coverage → chronological/geographic → honest mosaic)." This is correct behavior, not a bug.

2. **Deterministic venue corpus**: Because the venue_corpus cache is warm (14 story elements cached), all 3 runs get identical elements → identical themes → identical tours. The "spread: 0" is real but an artifact of caching, not a genuine measurement of variation. A cache bust + fresh SERP mining would introduce variation but also cost ($0.01–0.15 extra per run for SERP queries).

3. **work_stories table empty**: The per-work story cache (SQ-S8) has no entries. Thread discovery currently operates on the venue-level story_elements (14 elements from corpus pages), not per-work elements. When work_stories is populated (B6 path), elements_per_stop can be pre-mapped precisely.

4. **Kenzo Tange as dominant thread**: The museum's architectural identity (designed by Kenzo Tange, inaugurated 1998) dominates the discovered threads. This is factually correct (the museum's design IS its signature) but means the "dominant story" is more architectural-contextual than artwork-narrative. With richer per-work stories (from work_stories), more content-specific threads would emerge.
