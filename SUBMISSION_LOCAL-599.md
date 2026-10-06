# SUBMISSION — LOCAL-599

**Museums with no Wikidata entity: find the official site by web search, then run the site-first path**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-599-no-wikidata-venue`
- **Base:** `subscribed` @ `70f821e` (verified: `git merge-base --is-ancestor 70f821e HEAD` → exit 0)

---

## Problem

`MassArt Art Museum, Boston, MA`, 7 stops, clean-failed in seconds. The museum
has **no Wikidata item of its own** — only its parent, `Q4381563 Massachusetts
College of Art and Design`, has one. Official-site discovery ran **only** through
Wikidata `P856` or the venue's own Wikipedia article
(`venue_resolver._discover_site_from_wikipedia`), so `resolve_venue()` returned
`None`, no site was found, no corpus was built, and the run failed:

```
[venue_resolver] No Wikidata candidates for 'MassArt Art Museum'
[D1v2] Venue resolver returned None — falling back to heuristic
[D1v2] No official site discovered — will rely on Wikipedia + SPARQL
[D1v2] Canonical titles union: 0 … tier: unresolvable → clean fail (rung 4)
```

Gemini answered the same request at once from the museum's own site. Many small /
university / teaching museums look like this.

---

## What changed

### 1. Wikidata-independent official-site discovery — `venue_resolver.py`

New `discover_official_site(venue_string, city, *, serper_searcher,
homepage_fetcher, parent_searcher) -> SiteDiscovery`. Deterministic, no LLM.

- **Web search (Serper):** `"<venue>" <city> official site`, top 10
  (`cost_rates.SERPER_COST_PER_QUERY` = $0.001/query, env `SERP_API_KEY`).
- **Aggregator rejection, before fetch:** `tripadvisor, yelp, wikipedia,
  facebook, instagram, culturetrip, timeout, google, youtube, eventbrite,
  tiktok, pinterest, …` (`_AGGREGATOR_DOMAINS`), plus open-data hosts
  (`loc.gov`, `viaf.org`, `archive.org`, …).
- **Deterministic scoring** of each remaining homepage:
  `+3` the `<title>`/`og:site_name` token-overlaps the venue name;
  `+2` a distinctive venue token is in the host; `+2` the city appears in the
  page/footer; `+2` a US street-address pattern appears; `-5` HTTP ≠ 200.
  A pick needs **score ≥ 3 AND a NAME signal** (title or host) — a page that
  only mentions the city cannot win on its own.
- **Parent-org route (fallback):** Wikidata-search the institution named in the
  venue string (MassArt → `Q4381563`), take its `P856` site (reuses
  `_search_entities` + `_fetch_entity_properties`).
- Every candidate and the pick are logged.

### 2. Wiring — `generate_tour_text.py`

Two additive integration points, both guarded so **Wikidata venues are
untouched**:

- **Resolver-None point** (D1v2 corpus path): when the resolver returns `None`
  and no `P856` site is known, run `discover_official_site` to set
  `_base_site_url`.
- **Site-first eligibility gate** (deterministic-fill block): added the
  `else` branch for *no Wikidata entity* — run discovery and, when a site is
  found, set `_museum_site_first_eligible` + `_museum_site_url`, reusing the
  **existing** LOCAL-589 site-first extractor (`exhibition_site_first`). No
  second extractor was written.

The **tier becomes `exhibit_museum`** (not `unresolvable`) because the
exhibit-museum grounding branch keys on
`_exhibition_stops_source == 'site_exhibition'`, **not** on a resolved
`_venue_entity`.

**No invention:** if the site is found but yields `< N` verifiable stops, the
run delivers what is verified (existing fill rules), and logs an honest
shortfall. Clean fail only when **no site is found at all** — the current
actionable message is kept for that case.

### 3. Pre-existing latent bug found & fixed

`UnboundLocalError: local variable '_pre_d1v2_candidates' referenced before
assignment` in UNIFIED-FILL. The `site_exhibition` path sets
`tier='exhibit_museum'` but never ran D1v2 (where `_pre_d1v2_candidates` was
assigned). Griffin never hit it because Griffin publishes ≥ `total_stops`
exhibitions, so the fill block's `len(poi_list) < total_stops` guard was always
False. MassArt (1 show vs 7 requested) exposed it. Fix: initialise
`_pre_d1v2_candidates = []` alongside `_d1v2_result`, and set it to the
site-sourced stops in the `exhibit_museum` branch.

---

## Tests — `tests/test_local599_official_site_discovery.py` (Serper + HTTP stubbed)

7 tests, all pass:
- MassArt picks `maamboston.org` over tripadvisor / wikipedia / facebook.
- Aggregators rejected *before* fetch.
- Parent-org fallback (MassArt → `Q4381563` → `massart.edu`) when web search is
  inconclusive.
- A venue with no discoverable site returns `.found == False` (caller keeps the
  clean fail — no invention).
- Deterministic scoring: a city-only page cannot win; HTTP ≠ 200 is penalised
  below threshold.

### Suite exits (all 0)

```
tests/test_local599_official_site_discovery.py ....... 7 passed      EXIT=0
tests/test_local593_*.py                              30 passed      EXIT=0
test_local589_*.py                                    25 passed      EXIT=0   (incl. Griffin site-first + no-invention — unchanged)
test_local592_*.py                                    51 passed      EXIT=0
test_local580_site_first_candidates.py + test_venue_identity.py
  + test_local485_venue_class_routing.py              42 passed      EXIT=0   (Griffin/Harvard Wikidata venues unchanged)
```

---

## Live run (isolated container, cap $2)

`docker run --rm --name local599-gen` on `development_default`, built from
`Dockerfile.generator`, tour cache OFF, `COST_HARD_LIMIT_USD=2.00`. No
`audioura-*` container was touched. Runner: `run_local599_massart.py` /
`run_local599_live.sh`.

**`MassArt Art Museum, Boston, MA`, 7 stops.**

### Site-discovery lines + tier

```
[venue_resolver] No Wikidata candidates for 'MassArt Art Museum'
[LOCAL-599] Official-site search: "MassArt Art Museum" Boston official site
[LOCAL-599]   candidate: maam.massart.edu  score=9 [title_match(['massart']), host_name(['massart']), city(Boston), street_address]  title='Home | MassArt Art Museum'
[LOCAL-599]   candidate: massart.edu       score=9 [title_match(['massart']), host_name(['massart']), city(Boston), street_address]  title='Home | Massachusetts College of Art and Design (MassArt)'
[LOCAL-599]   candidate: calendar.massart.edu score=6 [host_name(['massart']), city(Boston), street_address]
[LOCAL-599]   reject (aggregator): instagram.com
[LOCAL-599]   reject (aggregator): tripadvisor.com
[LOCAL-599]   reject (aggregator): facebook.com
[LOCAL-599]   candidate: cntraveler.com    score=4 [city(Boston), street_address]      ← no NAME signal, not picked
[LOCAL-599]   reject (aggregator): eventbrite.com
[LOCAL-599] PICK (web_search): https://maam.massart.edu/ score=9
[LOCAL-599] No Wikidata entity for 'MassArt Art Museum' — site discovered (route=web_search); exhibition-museum site-first path ELIGIBLE (site='https://maam.massart.edu/')
[LOCAL-580] Site exhibitions found on https://maam.massart.edu/: 1 show(s)

TIER: exhibit_museum
```

### Stop titles

The venue's own site published **1** current exhibition at run time; the tour
delivered that one verified stop and did **not** fabricate the other six (honest
shortfall, per the no-invention contract):

```
Stop 1: Make with MAAM
[LOCAL-394] Stop count invariant: OK (1 selected == 1 delivered)
[D536] ⚠️  LISTENER ASKED FOR 7 STOP(S), DELIVERING 1 — reason='stops removed by gates or filters'
```

### BLOCKER 3 (content-QA factual gate)

```
BLOCKER 3 line 1 — PASS checks:          20
BLOCKER 3 line 2 — style FAIL checks:    0
BLOCKER 3 line 3 — FACTUAL FAIL checks:  0
```

### Stop 1 opening section (in full)

```
Stop 1: Make with MAAM

Coordinates: 42.3398, -71.0942

Orientation: You are about to explore the MassArt Art Museum in Boston. Within its
walls, you will encounter the transformative power of art creation through the work
"Make with MAAM." This collaborative piece highlights the impact of shared artistic
endeavors, uniting diverse voices and perspectives into a singular expression. Witness
firsthand how art creation can bridge gaps and foster connection, inspiring both the
creator and the viewer. Experience the profound influence of collaboration and
creativity on individuals and communities alike. Your first stop is Make with MAAM. As
you approach the Barkan Family Big Ideas Studio at MassArt Art Museum, notice how the
space is lively with creative activity — visitors engrossed in art-making, using an
array of textiles and textures. Stand by the large table where different materials and
tools are displayed, inviting you to become a part of this dynamic scene. From this
spot, you can see visitors of all ages engaging directly with the exhibition,
transforming their experience from mere observation to active creation.

Make with MAAM, an initiative at the MassArt Art Museum, emerged from a mission to
engage visitors actively with its exhibitions. This program offers participants
hands-on activities inspired by exhibitions like GENERATIONS. This transformation
allows visitors to delve personally into the art, connecting them through creative
processes. Founded in 1873, MassArt is one of the nation's oldest art schools,
embodying a tradition of innovation. By hosting Make with MAAM, it extends this
legacy, merging historical artistic traditions with contemporary interactive
experiences, fostering a community of creators. This leads to unexpected
collaborations where the boundaries between artist and audience blur, inspiring new
creations that reflect shared human creativity.

If you would like to eat nearby we can build you a restaurant tour.
```

### Cost + wall time

```
Tour total: $0.1682
wall time:  174.3s
```

### DB writes (counted, confirmed via psql on postgres-2)

```
stop_pool    : 1 row   (pool_key 'v2|loc:massart art museum boston ma|museum', title 'Make with MAAM')
venue_corpus : 0 rows  (no Wikidata QID → the QID-keyed venue_corpus cache is not written)
```

No DELETE. No GCloud.

---

## Behaviour vs. before

| | before | after |
|---|---|---|
| MassArt resolve | `None` → no site | discovered `maam.massart.edu` (web search) |
| tier | `unresolvable` | `exhibit_museum` |
| outcome | clean-fail in seconds | 1 verified stop delivered, honest shortfall |
| Griffin / Harvard (Wikidata venues) | — | **unchanged** (discovery runs only when no entity) |

---

## Commits (branch `LOCAL-599-no-wikidata-venue`, 8 ahead of `origin/subscribed`)

1. Wikidata-independent official-site discovery in `venue_resolver.py`.
2. Wire discovery into `generate_tour_text.py` (resolver-None + eligibility gate).
3. Tests `tests/test_local599_official_site_discovery.py`.
4. Isolated-container live-run scripts.
5. Rename runner to avoid the `*_container.py` dockerignore exclusion.
6. Fix `UnboundLocalError _pre_d1v2_candidates` in unified-fill.
7. Fix `stop_pool` row-count query.
8. `SUBMISSION_LOCAL-599.md`.
