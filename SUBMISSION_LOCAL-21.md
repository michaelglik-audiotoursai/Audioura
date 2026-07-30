##### READY FOR REVIEW

# LOCAL-21: Story-Engine Wiring, Round 2

**Branch:** `kiro/local21-story-wiring-round2`  
**Date:** 2026-07-30  
**Base:** `storied @ 04e726d` (LOCAL-19 merged)  
**Files modified:** `story_element_extractor.py`, `generate_tour_text.py`, `spine_generator.py`

---

## Fix 1: Rebase confirmed

```
$ git log --oneline -1
04e726d LOCAL-19: run R4 replenishment BEFORE UNIFIED-FILL + verified-only gate
```

Branch is based on `storied @ 04e726d`, which brings the LOCAL-16 verified-only gate and LOCAL-19's R4-before-UNIFIED-FILL ordering.

---

## Fix 2: QA gate now passes with story elements

**Problem:** LOCAL-18's wiring produced a tour with story elements, but the spine's `mode=found` caused the prolog LLM to emit dates/causal claims not traceable to the element set. G4 then flagged them as ungrounded.

**Root cause:** The prolog generation prompt received the spine's `tour_hook` (which derives from story elements) but had no constraint preventing the prolog-writing LLM from inventing additional historical claims (years, founding events, causal verbs) beyond what the elements stated.

**Fix (3 parts):**

1. **Prolog grounding constraint** (`generate_tour_text.py`): When `_story_elements` is non-empty, the prolog prompt now includes a `GROUNDING CONSTRAINT` section listing all documented facts and explicitly forbidding the LLM from inventing dates, names, or causal claims not present in the elements. Thematic/atmospheric framing is encouraged instead of specific historical claims.

2. **Spine prompt strengthening** (`spine_generator.py`): Added two lines to the `mode=found` injection requiring the `tour_hook` field to contain ONLY facts that appear verbatim in elements. When elements are sparse, instructs thematic/atmospheric framing instead of inventing history.

3. **Venue-identity founding suppression** (`generate_tour_text.py`): When story elements exist, the `venue_identity` dict's `founding` key is deleted before injection into the prolog prompt. Founding facts contain years/causal verbs that trigger G4 but aren't in story_elements. Architecture/design/programs are safe (no causal verbs).

**This does NOT weaken or widen the G4 exemption.** The G4 check runs at full strictness. The fix prevents the upstream LLM from producing claims that G4 rightfully rejects.

---

## Fix 3: Element yield improved

**Problem:** LOCAL-18 extracted only 3 elements from Chagall's Wikipedia pages because `extract_elements_from_text()` uses a work-specific prompt (asking about a specific artwork title). Museum-about pages (Wikipedia article about the museum) discuss the collection as a whole, not any single painting, so the work-specific prompt returns few/no results.

**Fix:** The adapter now detects "museum-about pages" (Wikipedia pages with museum/musée/museo in the URL, or pages at `/about`, `/history`, `/collection` paths) and uses **`extract_collection_provenance()`** for those pages. This function asks about donations, bequests, founding — exactly the facts these pages contain. Work-specific extraction is also run on these pages using venue_name as anchor (catches dates/techniques mentioned in passing).

**Additional improvements:**
- Page quality scoring now gives +2000 bonus to non-English Wikipedia (e.g. fr.wikipedia.org for French venues — often more detailed for local venues)
- Official museum "about/history/collection" pages get +5000 bonus
- Extended low-value URL patterns: `/ticket`, `/visit`, `/visite`, `/horaires`, `/tarif`, `/actualite`, `/news`, `/shop`, `/boutique`
- Page selection logging shows top-3 pages with scores and URLs for transparency

**Result:** Chagall: 1 element (first attempt) → **25 raw → 11 scored/ranked** (with collection-provenance extraction enabled).

---

## Live Evidence

### Container isolation
```
docker build -f Dockerfile.generator -t audioura-test-local21 .
docker run --rm --name audioura-test-local21-run --network development_default \
  -e OPENAI_API_KEY=... -e STORIED_MODE=true -p 5099:5000 \
  audioura-test-local21
```
Never touched `audioura-tour-generator-1`.

### Cache cleared + CACHE MISS shown
```sql
DELETE FROM tour_cache WHERE location ILIKE '%chagall%';    -- 2 rows
UPDATE venue_corpus SET story_elements_json = NULL WHERE venue_name ILIKE '%chagall%';
```
```
CACHE MISS: Musee National Marc Chagall, Nice, France / museum / 8
```

### Story element extraction — 11 elements from 3 pages
```
[Storied] STORIED_MODE=true — generating spine + fact sheets...
  [§3-adapter] Extracting story elements from 5/8 corpus pages for 'Musee National Marc Chagall'
    page[0] score=12140 url=https://fr.wikipedia.org/wiki/musée_Marc-Chagall_(Nice)
    page[1] score=10140 url=https://en.wikipedia.org/wiki/Musée_Marc_Chagall
    page[2] score=5285 url=https://musees-nationaux-alpesmaritimes.fr/chagall/collections
  [§3-adapter] Raw elements: 25 from 3 pages
  [§3-adapter] After corroboration scoring: 11 elements
  [§3-adapter] Final: 11 ranked elements (top type: dedication)
  [§3-adapter] Persisted 11 elements → /tmp/tmpbpmd1hha_story_elements.json
  [§3] Updated venue_corpus.story_elements_json for Q3329265 (11 elements)
  [§3] Story elements injected into spine prompt (11 elements, mode=found)
SPINE_COST: category=museum venue=Musee National Marc Chagall tokens=2348 (in=1316 out=1032) cost=$0.0221 latency=7.5s
  [Storied] Spine generated: 8 arc entries (mode=found)
  [Storied] Fact sheets: 8/8 generated
```

### All 8 stops D1v2-verified — no unverified fills
```
  [D1v2] VERIFIED 'Abraham et les trois anges' → canonical: 'Abraham et les trois anges'
  [D1v2] VERIFIED 'L'Arche de Noé' → canonical: 'L'Arche de Noé'
  [D1v2] VERIFIED 'L'Exode' → canonical: 'L'Exode'
  [D1v2] VERIFIED 'La Bible : Abraham et Isaac en route vers le lieu du sacrifice' → canonical: 'La Bible : Abraham et Isaac en route vers le lieu du sacrifice'
  [D1v2] VERIFIED 'Le Cirque bleu' → canonical: 'Le Cirque bleu'
  [D1v2] VERIFIED 'Le Roi David' → canonical: 'King David'
  [D1v2] VERIFIED 'Le prophète Jérémie' → canonical: 'Le prophète Jérémie'
  [D1v2] VERIFIED 'Résurrection' → canonical: 'Resurrection'
  [D1v2] 8/8 works verified — tier: rich
  [D1] Tier: rich (8 verified works)
  [R4] Target reached: 8/8 stops
  [LOCAL-16 GATE] All 8 stops are D1v2-verified ✓
```

### Delivered stop list (full, read from tour content)
```
Stop 1: Abraham et les trois anges
Stop 2: L'Arche de Noé
Stop 3: L'Exode
Stop 4: La Bible : Abraham et Isaac en route vers le lieu du sacrifice
Stop 5: Le Cirque bleu
Stop 6: King David
Stop 7: Le prophète Jérémie
Stop 8: Resurrection
```
All 8 are D1v2-verified. No `POST-R4-FILL` entries. No unverified stops.

### QA output — PASSES (17/19, all factual checks pass)
```
============================================================
content_qa_runner.py — Automated Tour QA
============================================================
Input: chagall_local21_tour.txt
Length: 17495 chars, 2729 words

  FAIL: No forbidden phrases — 30 forbidden phrases found: ['vibrant colors of', 'dreamlike quality', 'dreamlike imagery']
  PASS: No cross-stop repetition (>0.85)
  PASS: Distinct opening sentences
  PASS: No compass bearings (museum)
  PASS: No standalone Introduction block (R2)
  PASS: Final stop has substantial content
  PASS: Word count per stop (200-500 middle, 150-800 first/last)
  PASS: Total length reasonable (1000-8000 words)
  PASS: D3(a) Stop-title sanity
  PASS: D3(b) Coordinate scatter (museum <200m)
  FAIL: D3(c) No boilerplate shingles (4-word in 3+ stops) — 5 repeated shingle(s): ['creative process shines through', 'musee national marc chagall', 'eastern european jewish folklore']
  PASS: D3(d) Grounding assertion (titles look like real entities)
  PASS: D3(e) No duplicate stops (same work under different labels) (FACTUAL)
  PASS: T6 No splice corruption (mid-token dots, stray Stop N refs)
  PASS: R3 Orientation substance (no generic filler in museum)
  PASS: Single-venue consistency (no other NAMED venues)
  PASS: Attribution grounding (consistent with venue)
  PASS: Venue coherence (stops reference correct venue)
  PASS: G4 Prolog/epilog claims trace to story elements (FACTUAL)

============================================================
Score: 17/19 (style+factual)
QA PASSED (<=3 style failures + all factual checks pass)
```

**G4 factual check: PASS.** No ungrounded claims. All dated/causal claims in prolog + epilog trace to documented story elements.

### venue_corpus.story_elements_json
```sql
SELECT venue_name, jsonb_array_length(story_elements_json) FROM venue_corpus WHERE story_elements_json IS NOT NULL;
```
```
                venue_name                 | jsonb_array_length
-------------------------------------------+--------------------
 Musee National Marc Chagall, Nice, France |                 11
(1 row)
```

**Before: 0 of 16 venues. After: 1 venue with 11 elements (up from 3 in LOCAL-18).**

### Story elements persisted (sample)
```json
[
  {"id": "se_001", "type": "dedication", "text": "Marc Chagall offered a series of seventeen paintings illustrating the biblical m..."},
  {"id": "se_002", "type": "dedication", "text": "In 1972, the painter donated all the preparatory sketches for the Biblical Messa..."},
  {"id": "se_003", "type": "origin", "text": "Le musée Marc-Chagall est situé à Nice dans les Alpes-Maritimes."},
  {"id": "se_004", "type": "dedication", "text": "Le musée est dédié à l'œuvre d'inspiration religieuse de Marc Chagall."},
  {"id": "se_005", "type": "reference_work", "text": "Le musée abrite une série de dix-sept toiles illustrant le message biblique..."},
  {"id": "se_006", "type": "provenance", "text": "En 1972, le peintre a donné au musée toutes les esquisses préparatoires..."},
  {"id": "se_007", "type": "intention", "text": "Marc Chagall began working on the Biblical Message in the early 1950s..."},
  {"id": "se_008", "type": "provenance", "text": "In 1986, the museum acquired the complete suite of sketches and gouaches..."},
  {"id": "se_009", "type": "date", "text": "Le musée a été inauguré en 1973."},
  {"id": "se_010", "type": "intention", "text": "Chagall wanted an annual exhibition to be held on a topic related to the spiritu..."},
  {"id": "se_011", "type": "technique", "text": "Chagall created the mosaic which overlooks the pond and the blue stained glasses..."}
]
```

### Asian Arts Museum — 0 elements (investigated)
```
  [§3-adapter] Extracting story elements from 5/6 corpus pages for 'Asian Arts Museum'
    page[0] score=2400 url=https://maa.departement06.fr/les-oeuvres-commentees
    page[1] score=1675 url=https://maa.departement06.fr/
    page[2] score=1105 url=https://maa.departement06.fr/publications?categories%5B220%5D=220
  [§3-adapter] No elements extracted from 5 pages
  [§3] No story elements available — spine will use invented arc (mode=invented)
```

**Investigation result:** The Asian Arts Museum has no Wikipedia article (in any language). Its cached corpus pages are:
- `/les-oeuvres-commentees` — short listing page, no prose
- `/` — homepage, nav-heavy
- `/publications` — publications index

None contain story-worthy narrative content (founding history, donations, provenance). The improved source selection correctly assigns low scores to these pages and correctly attempts extraction. The pages simply have no extractable story facts. This is a data quality limitation of the free path (no relevant Wikipedia coverage for this venue).

**The spine falls back to `mode=invented` for this venue, which does NOT trigger G4** (invented mode doesn't emit `grounded_on` claims, so QA passes vacuously for this path).

---

## Regression Suite — 11/11 PASS

```
test_palais_fix_lead_fixture.py:  23/23 assertions hold. All tests passed.
test_b6_generation_wiring.py:     RESULTS: 14/14 PASS, 0 FAIL. ALL TESTS PASSED.
test_f4_cache_roundtrip.py:       ALL TESTS PASSED.
test_g4_false_positives.py:       G4 FAIL-CLOSED SCOPING: ALL PASS.
test_sq2_fixtures.py:             ALL TESTS PASSED.
test_sq3_fixtures.py:             ALL TESTS PASSED.
test_sq4_merge.py:                ALL TESTS PASSED.
test_w4_matcher.py:               All W4 tests completed.
test_w7_wiring.py:                ALL TESTS PASSED.
test_w9_collection_anchor.py:     ALL TESTS PASSED.
test_tier_computation.py:         ALL TESTS PASSED.
```

### test_attestation_log_only.py — Pre-existing failure (gateway not running)
```
test_attestation_log_only.py
Gateway: http://localhost:8080
Endpoint: http://localhost:8080/health
  FAIL: Valid API key + valid attestation token — connection refused (is gateway running?)
  FAIL: Valid API key + NO attestation token — connection refused (is gateway running?)
  FAIL: Valid API key + malformed attestation token — connection refused (is gateway running?)
  FAIL: Valid API key + wrong platform header — connection refused (is gateway running?)
Results: 0 PASS, 4 FAIL
```
Pre-existing: requires attestation gateway on port 8080 which is not deployed locally. Not a regression.
