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

---

## r2

**MassArt bounced at 1 stop of 7, and the one stop was a program.** Site discovery
(r1) was right — `maam.massart.edu` was picked — but the tour delivered a single
stop, *"Make with MAAM"*, a hands-on program in the Barkan Family Big Ideas Studio
(`/event/make-maam-222`), while the museum's own `/exhibitions` index publishes the
real shows. r2 fixes the extraction, fills to exactly N, folds in the D611 opening
section, and cleans up the pool.

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-599-no-wikidata-venue` (continued; HEAD base `a4c0a62`,
  verified `git merge-base --is-ancestor a4c0a62 HEAD` → exit 0)

### Root cause (why r1 shipped 1 program instead of the shows)

The MAAM home page links its three current exhibitions as **image-only** teaser
anchors (`<a class="…teaser-image" href="/exhibition/…"><img></a>` — no heading,
no text), so the structural extractor could not see them there; the one detail
link the home page DID surface with a title was the program *"Make with MAAM"*
(`/event/…`). And `discover_site_exhibitions` returned the **first** seed that
yielded any show — the home page is tried first — so it stopped on the program and
never reached `/exhibitions`, where all the real shows are cleanly published.

### 1 — Exhibition extraction that follows `/exhibition/<slug>` (commit 1)

`exhibition_discovery.py`
- **Title de-bleed** (`_title_from_heading`): the past-section template renders
  `<h3><a><span class="exhibition__title">Masako Miki</span></a> Past</h3>`, so the
  whole-heading text was *"Masako Miki Past"*. The title is now taken from the
  venue's own `exhibition__title` node (or the detail anchor's text), so the status
  label never bleeds into the name.
- **`classify_exhibition_status(section, page_text, subtitle, today)`** →
  `on_view` / `upcoming` / `past`, deterministic, in order of confidence: the CMS
  view-section token the show sits in (`view-display-id-on_view` vs `…-past`), then
  the show's own date range vs. today, then a subtitle suffix, else `on_view`.
- **`extract_classified_exhibitions`** returns `{title, detail_url, status, dates}`.

`exhibition_site_first.py`
- `_candidate_listing_urls` now tries the dedicated listing seeds
  (`/exhibitions`, `/current-exhibitions`, …) **before** the home page.
- `discover_site_exhibitions` / new `discover_classified_exhibitions`
  **accumulate across seeds**, scoring each listing by how many TRUE exhibition
  detail links it carries, so a dedicated index beats a home page that links one
  program. (This is the r1 bug fix.)
- `_is_exhibition_detail` drops a detail link whose first path segment is a
  program/event/class/studio/shop/membership/… root — **"Make with MAAM"
  (`/event/…`) is excluded** by a path-segment rule, not a title blocklist.

### 2 — Fill to exactly N, in the honest order (commit 1)

`build_site_first_candidates` assembles, in order:
(a) **current (on-view) exhibitions**, (b) the museum's **own named spaces** from
`/visit` and `/about` (`_discover_museum_spaces`, emitted only when a heading names
a room/gallery/floor/building feature — never page furniture), (c) **upcoming**,
(d) **past** (supplemented from the full `/exhibitions/past` archive via
`_supplement_past_exhibitions` when the index is short). Every candidate carries a
**source URL** (its own detail page, or the `/visit`|`/about` page a space was read
from) plus `status` + `kind`. Nothing is invented: MAAM's `/visit` and `/about`
name no physical galleries (it is a single-gallery museum), so zero spaces are
emitted and the past archive fills instead; if the real material cannot reach N the
list is simply shorter and the log says so.

### 3 — The D611 opening section (commit 2)

The opening section (`about_museum_stop.build_opening_section`) is folded into
Stop 1 by `stop_pool_orchestrator`. It never ran for MassArt because the orchestrator
resolved the venue only through Wikidata (`resolve_venue → None` → no site URL).
r2 adds `_discover_site_url_fallback` (reusing the LOCAL-599
`venue_resolver.discover_official_site`) to **both** `_build_opening_section` and
`_resolve_venue_address`, so the venue's own `/visit` + `/about` are reached.
- `_normalize_compact_times` rewrites MAAM's compact hours (`"12 – 8p"`, nbsp,
  `\x1e` day separators) into the `am/pm` spelling the LOCAL-592 extractor reads —
  applied to the extractor input **and** the LOCAL-584 gate's literal-comparison
  text, so a page-stated hour is never dropped. The hours merge keeps the full
  weekly schedule; `_dedupe_hours_segments` removes a grouped day-range line
  already covered by individual days.
- `visitor_facts_extractor` now also recognises *"Always free"* /
  *"admission is (always) free"* / *"free to the public"* (MAAM's wording).

### 4 — Pool hygiene (the one `Make with MAAM` row)

Against `development-postgres-2-1` (the stop-pool DB; not an `audioura-*`
container):

```
BEFORE: exact(pool_key='v2|loc:massart art museum boston ma|museum' AND
        title='Make with MAAM') = 1   total stop_pool rows = 811
DELETE  (guarded: abort+rollback unless exactly 1 matched)  rowcount = 1
AFTER : exact = 0   massart rows = 0   total stop_pool rows = 810
```

No other DELETE.

### 5 — Live run (isolated container `local599b-gen`, cap $2)

`docker run --rm --name local599b-gen` on `development_default`, DB `postgres-2`,
tour cache OFF, `COST_HARD_LIMIT_USD=2.00`. No `audioura-*` container touched.
Runner: `run_local599b_massart.py` / `run_local599b_live.sh`. It routes through
`stop_pool_orchestrator.maybe_generate_with_pool` (the only path that folds the
opening section).

**`MassArt Art Museum, Boston, MA`, 7 stops. TIER: `exhibit_museum`.**
Site discovered `https://maam.massart.edu/` (web_search, score 9) over
`massart.edu` / `calendar.massart.edu`; instagram / tripadvisor / facebook /
eventbrite rejected as aggregators; `cntraveler.com` (score 4, no NAME signal)
not picked.

#### The 7 stop titles, each with its source URL

```
Stop 1: Robert Lazzarini   https://maam.massart.edu/exhibition/robert-lazzarini   [on_view]
Stop 2: Nicholas Galanin   https://maam.massart.edu/exhibition/nicholas-galanin   [past]
Stop 3: Ghost of a Dream   https://maam.massart.edu/exhibition/ghost-dream        [past]
Stop 4: Banu Cennetoğlu    https://maam.massart.edu/exhibition/banu-cennetoglu    [on_view]
Stop 5: Baseera Khan       https://maam.massart.edu/exhibition/baseera-khan       [on_view]
Stop 6: Masako Miki        https://maam.massart.edu/exhibition/masako-miki        [past]
Stop 7: Press & Pull       https://maam.massart.edu/exhibition/press-pull         [past]
```

3 current (on-view) + 4 past, each a real `/exhibition/<slug>` detail page; the
program *"Make with MAAM"* is excluded. (Within-tour ordering is route/story
sequenced; the current shows and past shows are all present.)

#### Stop 1 opening section (in full)

```
Stop 1: Robert Lazzarini

Address: 621 Huntington Avenue, Boston, Massachusetts

Coordinates: 42.3399, -71.0942

Before we look at anything on the walls, here is the story of MassArt Art Museum
in Boston, Massachusetts itself — who created it, why it exists, and what it is
known for. We make this land acknowledgment to pay respect to these communities –
past, present, and future – and recognize the painful history of erasure and
ongoing violence toward indigenous people in North America and across the world.
This account is drawn from the museum's own pages on maam.massart.edu.

The MassArt is open Thursday, 12 PM–8 PM; Friday, 12 PM–5 PM; Saturday, 12 PM–5 PM;
Sunday, 12 PM–5 PM. Admission is FREE, as listed on maam.massart.edu in October 2026.

Orientation: … Your first stop is Robert Lazzarini. …
```

Address `621 Huntington Avenue`, hours **with days**, and the free admission are
all sourced from the venue's own `/visit` and `/about`; nothing is invented.

#### BLOCKER 3 (content-QA factual gate)

```
BLOCKER 3 line 1 — PASS checks:          17
BLOCKER 3 line 2 — style FAIL checks:    3
BLOCKER 3 line 3 — FACTUAL FAIL checks:  0
```

The FACTUAL line is clean (0). The 3 style FAILs are LLM-narration issues, not
extraction/wiring: a forbidden phrase ("to fully appreciate") and the single-venue
consistency check flagging three galleries the model named as the artists' OTHER
venues (Blum Gallery, Paine Gallery, James Gallery), with the attribution-grounding
flag following from that. These are narration-quality items for a prompt pass, not
the extraction/opening-section contract this ticket is about.

#### Cost + wall time

```
Tour total: $1.3133   (authoritative _LAST_GENERATION_COST; well under the $2 cap)
wall time : 562.4s
```

(The `$3.1827` line in the log is a shared cumulative accumulator print, not this
tour's cost.)

#### DB after the run

```
stop_pool (massart): 7   — the successful tour correctly seeded the pool with its
                           7 real exhibition stops (NOT the r1 'Make with MAAM' row,
                           which was deleted in step 4).
```

### Tests

New: `tests/test_local599b_maam_exhibitions.py` (14) + `tests/test_local599b_opening_section.py`
(5), both driven by saved fixtures of the REAL MAAM pages
(`tests/fixtures/maam/*.html`): classification (3 on-view + 3 past), title de-bleed,
program exclusion, discovery preferring the index, fill-to-7 current-first, past
archive supplement, no-invention; and the D611 opening section (hours-with-days,
free admission, address, no fabricated time).

#### Suite exits (all 0)

```
tests/test_local599_official_site_discovery.py                     7 passed   EXIT=0
tests/test_local599b_maam_exhibitions.py + _opening_section.py    14 passed   EXIT=0
test_local589_*.py                                                25 passed   EXIT=0
test_local592_*.py + test_local593 single-venue opening            54 passed   EXIT=0
test_local580_*.py                                                25 passed   EXIT=0
test_local585_*.py + test_local584_*.py + test_local582_*.py      78 passed   EXIT=0
test_local590_*.py + test_local370_*.py                           69 passed   EXIT=0
```

### Commits (branch `LOCAL-599-no-wikidata-venue`, base `a4c0a62`)

1. Exhibition extraction follows `/exhibition/<slug>` + fill-to-N
   (current → named spaces → upcoming → past); MAAM fixtures.
2. D611 opening section for no-Wikidata venues (orchestrator discovery fallback +
   compact-hours normalisation + "Always free") + source-URL reporting + runner
   through the orchestrator + MAAM tests.
3. `SUBMISSION_LOCAL-599.md` r2.
