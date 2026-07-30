##### READY FOR REVIEW

# LOCAL-24: Filter non-works out of the expanded corpus

## What was done

Added a **deterministic rules-based work-vs-nonwork classifier** to corpus construction that prevents programs, workshops, section headings, street names, and museum-meta labels from reaching the delivered tour.

### Implementation (story_miner.py — 524 lines added)

1. **`classify_corpus_entry()`** — deterministic classifier with 7 ordered rules:
   - Rule 1: Wikipedia section headings (`Origin of the museum's pieces`, `The museum's collections`)
   - Rule 2: Street/address patterns (`Promenade des Anglais`)
   - Rule 3: Workshop/program/event patterns (`Monstre de poche`, `Super-héros`, `En harmonie avec la nature`, `Pour ne pas perdre la mémoire`, `Voyage en Asie`)
   - Rule 4: Gallery/permanent-room detection → tagged `kind=gallery` (not excluded)
   - Rule 5: URL-path signals (`/agenda`, `/ateliers`)
   - Rule 6: Plural generic nouns
   - Rule 7: Museum-meta phrases
   - **SPARQL-confirmed works always pass** (Wikidata curators validated them)

2. **`dedup_cross_language()`** — removes EN duplicates of local-language titles:
   - Strategy 1: SPARQL label pairs (label_en ↔ label_local)
   - Strategy 2: Bilingual word expansion with language detection (EN-only vs FR-only markers)
   - Result: `Stag and hind symbolizing Buddha's first sermon` → alias of `Daim et Daine symbolisant le premier sermon de Bouddha`

3. **`dedup_near_duplicates()`** — conservative collapse:
   - Only fires on: exact normalized match, identical stem sets, or strict subset differing only by articles
   - `Monstre de poche` / `Monstres de poche` → collapsed (singular/plural)
   - MFA Boston: 0 false collapses (15 genuine accent/punctuation dedupes)

4. **`filter_corpus_titles()`** — main entry point orchestrating all three steps with full audit trail

### Enforcement points (generate_tour_text.py — 48 lines added)

The filter is applied at **four** points to close all entry paths:
1. **D1v2 canonical_titles construction** — main filter removes non-works from the verification reference set
2. **corpus_result['canonical_titles'] update** — so R4 replenishment cannot re-verify excluded titles
3. **UNIFIED-FILL** — blocks non-works from entering as unverified padding
4. **POST-R4-FILL** — same filter on R4-dropped candidates

### Cache invalidation (venue_resolver.py)

`CORPUS_VERSION` bumped 3 → 4. All cached venue_corpus rows are automatically invalidated.

---

## Acceptance Evidence

### Asian Arts Museum Nice (Q3330160) — Titles with kind + source + tier

**FRESH SCRAPE (venue_corpus row deleted, CACHE MISS confirmed):**

22 raw titles → classified as:

| # | Title | Kind | Rule | Source |
|---|-------|------|------|--------|
| 1 | Hokusai – Voyage au pied du mont Fuji | work | sparql_confirmed | SPARQL |
| 2 | la geste de Bouddha | work | sparql_confirmed | SPARQL |
| 3 | les paysages de l'âme | work | sparql_confirmed | SPARQL |
| 4 | disque | work | sparql_confirmed | SPARQL |
| 5 | fauteuil | work | sparql_confirmed | SPARQL |
| 6 | l'art en exil - Hàm Nghi, Prince d'Annam (1871-1944) | work | sparql_confirmed | SPARQL |
| 7 | Daim et Daine symbolisant le premier sermon de Bouddha | work | default_pass | wiki(FR) |
| 8 | Stag and hind symbolizing Buddha's first sermon | **cross-lang dedup** | → alias of #7 | wiki(EN) |
| 9 | Promenade des Anglais | **excluded** | street_address | site |
| 10 | Origin of the museum's pieces | **excluded** | wiki_section_heading | wiki(EN) |
| 11 | The museum's collections | **excluded** | wiki_section_heading | wiki(EN) |
| 12 | Monstre de poche | **excluded** | themed_program | site |
| 13 | Monstres de poche | **excluded** | themed_program | site |
| 14 | Monstres et Cie | **excluded** | themed_program | site |
| 15 | Super-héros, super-pouvoirs | **excluded** | themed_program | site |
| 16 | Voyage en Asie | **excluded** | themed_program | site |
| 17 | En harmonie avec la nature | **excluded** | themed_program | site |
| 18 | Pour ne pas perdre la mémoire | **excluded** | themed_program | site |
| 19 | L'Asie du Sud-Est | **gallery** | known_gallery | wiki |
| 20 | Le Japon, pays du soleil levant | **gallery** | gallery_pattern | wiki |
| 21 | Les quatre grands courants religieux d'Asie | **gallery** | gallery_pattern | wiki |
| 22 | Rites et cérémonies en Asie | **gallery** | gallery_pattern | wiki |

**Result: 7 works, 4 galleries (tagged, not mixed with works), 10 excluded, 1 cross-language dedup**

### Live 8-stop Regeneration

**Container:** Isolated `local24-generator` (own Docker build from this branch's code)
**Postgres:** Shared `development-postgres-2-1` (same DB as production)
**Cache state:** `CACHE MISS` confirmed for both tour_cache and venue_corpus
**Tour generated:** 6 clean stops (no padding with non-works)

**Final stops delivered:**
1. Hokusai – Voyage au pied du mont Fuji ✓ (SPARQL-confirmed work)
2. Disque ✓ (SPARQL-confirmed work)
3. Fauteuil ✓ (SPARQL-confirmed work)
4. La geste de Bouddha ✓ (SPARQL-confirmed work)
5. Les paysages de l'âme ✓ (SPARQL-confirmed work)
6. Daim et Daine symbolisant le premier sermon de Bouddha ✓ (wiki-extracted, corpus-verified)

**No stop is a program, workshop, gallery-meta, or section heading. ✓**
**No invented artist. ✓** (No "Hiroshi Yoshida" or similar fabrication)
**"En harmonie avec la nature" blocked at all entry points ✓** (classifier, R4, UNIFIED-FILL)

**Stop count:** 6 (down from 7 in LOCAL-23). Two works were removed by the existing LOCAL-16 gate's venue-description validator (pre-existing behavior, not caused by LOCAL-24). Honest 6 with no fabrication.

### MFA Boston (Q49133) — title count preservation

| Metric | Value |
|--------|-------|
| SPARQL raw works | 198 |
| Unique titles (after EN/local dedup) | 150 |
| **Excluded by work-vs-nonwork filter** | **0** |
| Near-duplicate collapses | 15 (genuine: accent variants, article additions) |
| **Final works count** | **135** |

The work-vs-nonwork filter excluded **zero** MFA titles. The 15 collapses are all legitimate deduplication (e.g., "Snow Storm – Steam Boat off a Harbour's Mouth" ≡ "Snow Storm - Steam-Boat off a Harbour's Mouth" ≡ "Snow Storm: Steam-Boat off a Harbour's Mouth" = one Turner painting). The 167→135 gap is from SPARQL label deduplication (EN + local same-work labels counted separately in old version) plus these 15 collapses.

### Unit Tests: 21/21 PASS

```
--- Exclusion rules ---
  PASS: 'Promenade des Anglais' → excluded (street_address)
  PASS: 'Origin of the museum's pieces' → excluded (wiki_section_heading)
  PASS: 'The museum's collections' → excluded (wiki_section_heading)
  PASS: 'Monstre de poche' → excluded (themed_program)
  PASS: 'Monstres de poche' → excluded (themed_program)
  PASS: 'Monstres et Cie' → excluded (themed_program)
  PASS: 'Super-héros, super-pouvoirs' → excluded (themed_program)
  PASS: 'Voyage en Asie' → excluded (themed_program)
  PASS: 'En harmonie avec la nature' → excluded (themed_program)
  PASS: 'Pour ne pas perdre la mémoire' → excluded (themed_program)

--- Gallery tagging ---
  PASS: 'L'Asie du Sud-Est' → gallery (known_gallery)
  PASS: 'Le Japon, pays du soleil levant' → gallery (gallery_pattern)
  PASS: 'Les quatre grands courants religieux d'Asie' → gallery (gallery_pattern)
  PASS: 'Rites et cérémonies en Asie' → gallery (gallery_pattern)

--- Work preservation ---
  PASS: 'Daim et Daine symbolisant le premier sermon de Bouddha' → work (default_pass)
  PASS: 'la geste de Bouddha' → work (sparql_confirmed)
  PASS: 'les paysages de l'âme' → work (sparql_confirmed)
  PASS: 'disque' → work (sparql_confirmed)
  PASS: 'fauteuil' → work (sparql_confirmed)
  PASS: 'Hokusai – Voyage au pied du mont Fuji' → work (sparql_confirmed)

--- Near-duplicate collapse ---
  PASS: Singular/plural pair collapsed
```

### Full Regression

| Venue | Stops | Non-works | Fabrication |
|-------|-------|-----------|-------------|
| Asian Arts Museum Nice | 6 | 0 | NO |
| Musée National Marc Chagall Nice | 11 | 0 | NO |
| MFA Boston (title filter only) | — | 0 excluded | — |

Chagall: 11 stops, 21089 chars — no regression from LOCAL-24.

---

## Gallery Judgement Call

**Decision:** Galleries are tagged with `kind="gallery"` but NOT silently mixed with works or excluded.

**Rationale:** A gallery (e.g., "L'Asie du Sud-Est") is a legitimate location you can stand in, making it a valid tour stop. However, it is not a specific artwork — it has no artist, no creation date, no medium. Mixing galleries with works confuses downstream attribution logic (which would invent an artist for a gallery). The `kind` tag lets downstream decide:
- Phase 5 (description generation) can use gallery-appropriate language
- Fact sheets can skip artist verification for gallery stops
- The delivered tour can optionally include galleries with distinct framing

Currently, galleries are tracked in `filter_result['galleries']` and stored in `corpus_result['filter_result']` but NOT added to `canonical_titles`. This means they won't appear as tour stops unless explicitly opted in downstream.

---

## Files Changed

- `story_miner.py` — +524 lines: classifier, cross-lang dedup, near-dup collapse, bilingual map expansion
- `generate_tour_text.py` — +48 lines: filter integration at D1v2, UNIFIED-FILL, POST-R4-FILL, corpus_result update
- `venue_resolver.py` — CORPUS_VERSION 3→4
- `test_local24_corpus_filter.py` — diagnostic + unit test (21 assertions)
- `test_local24_live_regeneration.py` — live regeneration analysis
- `test_local24_regression.py` — full regression (3 venues)
