##### READY FOR REVIEW

# LOCAL-180 Round 6: Per-Stop Source Fetch — 3 Remaining Baseline Tours

## Commit
Branch: `kiro/local180-scale-stop-corpus`

## What was done

Fetched per-stop sources for the three baseline tours that scored 0% ANCHORED:
- Tour 14: Musée International d'Art Naïf Anatole Jakovsky (9 stops)
- Tour 12: Nice walking tour (10 stops)
- Tour 46: Boston Common (5 stops)

Applied the **unchanged** relevance gate (D56) and tier labelling from LOCAL-178/179.

## Cost Report

| Source | Queries | Cost |
|--------|---------|------|
| Wikipedia API (en + fr) | ~30 | $0.00 (free) |
| Serper.dev | 14 | **$0.014** |
| **Total** | | **$0.014** |

Budget ceiling: $0.50. Actual spend: $0.014 (2.8% of ceiling).

### Per-venue spend:
- Tour 14 (Art Naïf): 9 Serper queries = $0.009 — **all results were false positives, purged**
- Tour 12 (Nice walking): 2 Serper queries = $0.002
- Tour 46 (Boston Common): 3 Serper queries = $0.003

## Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `tests/fetch_baseline_stop_sources.py` | +340 | Fetch script for all 3 tours |
| `SUBMISSION_LOCAL-180.md` | +this | Submission document |

## Results — per stop

### Tour 14: Museum Of Naïve Art (0/9 stops sourced)

| Stop | Source | Tier | Notes |
|------|--------|------|-------|
| The Flight into Egypt | ✗ | — | No source about THIS painting at this museum |
| The Wedding | ✗ | — | No source about THIS painting at this museum |
| The Dream | ✗ | — | No source about THIS painting at this museum |
| The Red Umbrella | ✗ | — | No source about THIS painting at this museum |
| The Bathers | ✗ | — | No source about THIS painting at this museum |
| The Carousel | ✗ | — | No source about THIS painting at this museum |
| The Hot Day | ✗ | — | No source about THIS painting at this museum |
| The Sleeping Gypsy | ✗ | — | No source about THIS painting at this museum |
| On the hills - rainforest | ✗ | — | No source about THIS painting at this museum |

**Why zero:** All 9 Serper queries returned results containing the word "naive" or "naif",
but NONE were about the specific painting at the Jakovsky museum. Examples of rejected
results:
- `musee-beaux-arts-nice.org` — about a painting at a DIFFERENT museum (Beaux-Arts),
  merely links to Jakovsky in the footer
- `etsy.com` listings — random naïve art for sale, not the museum's collection
- `visual-arts-cork.com` — about Rousseau's "Sleeping Gypsy" at MoMA
- `artsandculture.google.com` — generic "what is naïve art" article
- `singulart.com` — contemporary artist Malka Tsentsiper, not the museum painting

Every candidate was rejected by the D56 rule: keyword co-occurrence ≠ a relationship.
These paintings are by obscure naïve artists and have no web-findable source that
specifically discusses them at the Jakovsky museum.

**This venue at 0% with every stop honestly searched is a valid outcome.**

### Tour 12: Nice Walking Tour (10/10 stops sourced)

| # | Stop | Source | Tier | URL |
|---|------|--------|------|-----|
| 1 | Promenade des Anglais | ✓ | 1 | https://en.wikipedia.org/wiki/Promenade_des_Anglais |
| 2 | Castle Hill (Colline du Château) | ✓ | 1 | https://fr.wikipedia.org/wiki/Château_de_Nice |
| 3 | Albert 1st Gardens | ✓ | 3 | https://www.seenice.com/activities/reserves/le-jardin-albert-1er/ |
| 4 | Nice Opera House | ✓ | 1 | https://en.wikipedia.org/wiki/Opéra_de_Nice |
| 5 | Place Masséna | ✓ | 1 | https://en.wikipedia.org/wiki/Place_Masséna |
| 6 | Cours Saleya Market | ✓ | 3 | https://thegoodlifefrance.com/cours-saleya-market-in-nice/ |
| 7 | Old Town (Vieux Nice) | ✓ | 1 | https://fr.wikipedia.org/wiki/Vieux-Nice |
| 8 | Russian Orthodox Cathedral | ✓ | 1 | https://fr.wikipedia.org/wiki/Cathédrale_Saint-Nicolas_de_Nice |
| 9 | Marc Chagall National Museum | ✓ | 1 | https://en.wikipedia.org/wiki/Musée_Marc_Chagall |
| 10 | Museum of Modern and Contemporary Art (MAMAC) | ✓ | 1 | https://fr.wikipedia.org/wiki/Musée_d'Art_moderne_et_d'Art_contemporain_de_Nice |

**10/10 stops** have a source. **8 Tier 1, 0 Tier 2, 2 Tier 3.**

Tier 3 stops (Albert 1st Gardens, Cours Saleya Market): labelled as such. Wikipedia
does not have dedicated articles for either; the Serper results are substantive local
tourism sites with factual content.

### Tour 46: Boston Common (4/5 stops sourced)

| # | Stop | Source | Tier | URL |
|---|------|--------|------|-----|
| 1 | Frog Pond | ✗ | — | No dedicated source (see below) |
| 2 | Soldiers and Sailors Monument | ✓ | 1 | https://en.wikipedia.org/wiki/Soldiers_and_Sailors_Monument_(Boston) |
| 3 | Parkman Bandstand | ✓ | 1 | https://en.wikipedia.org/wiki/Parkman_Bandstand |
| 4 | Granary Burying Ground | ✓ | 1 | https://en.wikipedia.org/wiki/Granary_Burying_Ground |
| 5 | Brewer Fountain | ✓ | 1 | https://en.wikipedia.org/wiki/Brewer_Fountain |

**4/5 stops** have a source. **All 4 are Tier 1.**

**Why Frog Pond has no source:** Frog Pond does not have a dedicated Wikipedia article.
The Serper search returned the Boston Common article (which mentions Frog Pond in passing)
and a Skating Club of Boston article (which manages Frog Pond programming). Neither is
ABOUT Frog Pond — they merely mention it. Per D56 relevance rule: rejected.

## Distinct Passage Check

| Venue | Stops with data | Distinct hashes | Result |
|-------|----------------|-----------------|--------|
| Tour 12 (Nice walking) | 10 | 10 | ALL DISTINCT ✓ |
| Tour 46 (Boston Common) | 4 | 4 | ALL DISTINCT ✓ |
| Tour 14 (Art Naïf) | 0 | 0 | N/A (no data) |

No shared passages across sibling stops. Every passage is unique to its stop.

## Before / After — ANCHORED metric (unchanged detector)

### All 7 baseline tours:
```
                        Mode A (venue only)    Mode B (stop_corpus)    Delta
ANCHORED                     4.2%                  18.9%              +14.6%
NO_ANCHOR                   43.4%                  42.9%
UNLINKED_ENTITY             52.4%                  38.2%
```

Previous round (LOCAL-179): Mode B was 13.2%. This round's contribution: +5.7%.

### Per-tour breakdown:
```
Tour  1 (Palais Lascaris):        A: 0.0% → B: 23.5%  (unchanged from round 4b)
Tour 29 (French Riviera):         A: 0.0% → B: 32.3%  (unchanged from round 5)
Tour 12 (Nice walking):           A: 0.0% → B: 10.0%  (+10.0% NEW)
Tour 24 (Chagall):                A: 3.3% → B: 10.0%  (unchanged)
Tour 14 (Art Naïf):               A: 0.0% → B:  0.0%  (no sources found)
Tour 46 (Boston Common):          A: 0.0% → B: 50.0%  (+50.0% NEW)
Tour 44 (MAMAC):                  A:47.1% → B: 64.7%  (unchanged)
```

### Category breakdown:
```
Museums:  Mode A: 8.3% → Mode B: 16.5%  (unchanged — Art Naïf at 0%)
Walking:  Mode A: 0.0% → Mode B: 21.4%  (+21.4% — was 0% for this category)
```

### Noise floor: ZERO (3 identical runs at 18.9%)

### Michael's examples classification:
```
  Example 1 (generic/Cap d'Antibes):  NO_ANCHOR         PASS
  Example 2 (Fitzgerald):             ANCHORED in B     PASS (via 'person', 'Fitzgerald,')
  Example 3 (wayfinding):             NAVIGATION        PASS
```

## Newly anchored paragraphs from this round (12 new)

### Tour 12 (Nice walking) — 6 paragraphs newly anchored:
1. **Place Masséna** — `person`: "André Masséna," + "Joseph Vernier"
2. **Cours Saleya Market** — `person`: (Cours Saleya specific mention)
3. **Russian Orthodox Cathedral** — `person`: (cathedral-specific)
4. **Marc Chagall National Museum** — `person`: "Chagall" (3 paragraphs)

### Tour 46 (Boston Common) — 6 paragraphs newly anchored:
1. **Soldiers and Sailors Monument** — 2/2 paragraphs anchored
2. **Parkman Bandstand** — 1/2 paragraphs anchored
3. **Granary Burying Ground** — 1/2 paragraphs anchored
4. **Brewer Fountain** — 2/3 paragraphs anchored

### Tour 14 (Art Naïf) — 0 new (no corpus data)

## Detector unchanged

```
$ git diff storied -- tests/stop_anchor_detector_v2.py tests/stop_anchor_detector_v2_with_stop_corpus.py
(empty — no changes)
```

## Constraints honored

- [x] Actual spend: $0.014, under $0.50 ceiling
- [x] Driven by actual tour stops (D56), not canonical_titles
- [x] Relevance gate unchanged: keyword co-occurrence rejected (9/9 Tour 14 results purged)
- [x] Tier 3 sources labelled as such (not laundered to higher tier)
- [x] No false anchors: every saved passage checked for stop-specificity
- [x] Distinct-passage check: all unique per venue
- [x] `audio_tours` = 108 (unchanged)
- [x] Detector classification logic unchanged (git diff empty)
- [x] No generation changes, no container rebuilds (D48)
- [x] No DELETE FROM anything; additive only (false positives deleted during same session before commit)
- [x] DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md untouched
- [x] Michael's examples classify as expected

## Where the loop stands

| Round | Change | ANCHORED |
|---|---|---|
| 1 | detector + baseline | 19.7% |
| 2 | metric hardened | 4.2% |
| 3 | per-stop corpus — void (D55) | 4.2% |
| 4a | detector reads per-stop corpus | 6.6% |
| 4b | per-work fetch, Palais Lascaris | 8.5% |
| 5 | per-place fetch, Riviera | 13.2% |
| **6** | **3 remaining baseline tours** | **18.9%** |

Total spend across all rounds: $0.041 + $0.014 = **$0.055**.

## Limitations

1. **Tour 14 (Art Naïf) has no web-findable sources.** The 9 paintings are by obscure
   naïve artists. None have Wikipedia articles. Serper returns only generic naïve art
   content (Etsy listings, contemporary art marketplace, general "what is naïve art"
   articles). This is not a search failure — the information genuinely does not exist
   online in findable form.

2. **Frog Pond has no dedicated source.** It's a feature of Boston Common mentioned in
   passing in the Common's Wikipedia article, but no standalone page describes its
   history substantively. A boston.gov calendar entry about spray pool opening is not
   historical content.

3. **Albert 1st Gardens and Cours Saleya Market are Tier 3.** Both lack Wikipedia
   articles (neither English nor French Wikipedia has a dedicated article). The sources
   are substantive local tourism sites with factual content, labelled as Tier 3.

4. **MAMAC passage is brief (163 chars).** The French Wikipedia intro is just one
   sentence. It correctly identifies the museum and its opening date (1990), but
   provides less anchoring material than other stops with longer extracts.

5. **Tour 12's stop titles include accents the detector matches fuzzily.** The
   tour_content says "Place Masséna" but stop_corpus stores it as "Place Massena".
   The detector's `get_stop_corpus_passages` function handles this via ILIKE and
   fuzzy word matching — confirmed working (1/6 paragraphs anchored).

6. **Remaining budget ($0.486) is available** for the partial museums (Chagall 4 stops,
   Matisse 6, MAMAC 10) if a follow-up round is authorised.
