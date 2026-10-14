# SUBMISSION — LOCAL-583: Exhibition museums — the venue cache must not turn site chrome into "works"; and a museum tour must not take 13 minutes

**Branch:** `LOCAL-583-venue-cache-chrome`  **Base:** `storied` (47b0b4d)
**Agent:** Mac Mini Kiro

## The defect (Michael, 2026-10-05, local stack, "Griffin museum of photography, Winchester, MA")

LEAD's trace (generator job 797a637d → tours 391/392):

1. An earlier run wrote `venue_corpus` for Q99108607 with **23 "canonical titles"
   that are site chrome** ("Calls For Entry", "Our Team", "Terms Conditions",
   "Griffin Museum Board Of Directors 2", "Membership Levels", …).
2. The next run hit the cache: `[LOCAL-30] Deterministic selection: 23 documented
   works (0 catalogue, 0 SPARQL)` → `DETERMINISTIC BYPASS` → **LOCAL-580's
   site-first path never ran** (it requires 0 documented works) → three of five
   stops were not exhibitions (Board Of Directors 2, Arthur Griffin Archive,
   Calls For Entry).
3. **Wall time 774.8 s** for text: story_first 380.6 s, external_lookups 189.3 s,
   poi_selection 171.4 s — serial `[SQ-S2]` P856 read-timeouts against random
   third-party domains, and per-stop Overpass 504/timeout retries.

## What shipped (one commit per deliverable, pushed after each)

### D1 — Site-derived titles are not documented works  (commit 1)

In both LOCAL-30 deterministic-selection blocks (`generate_tour_text.py`), the
"documented" count is now **catalogue + SPARQL only**:

```python
_det_documented_count = sum(
    1 for d in _det_documented if d.get('source') in ('catalogue', 'sparql')
)
```

- The deterministic bypass gate is `if _det_documented_count >= total_stops:` —
  site/cache `canonical` titles can no longer trigger it on their own.
- LOCAL-580 site-first eligibility is `if _det_documented_count == 0:` — a cache
  full of site chrome no longer keeps the site-first exhibitions path from
  running. **When the museum has 0 catalogue/SPARQL works, site-first runs
  regardless of the cache.**

Canonical titles still ride along as *fill material* once a real documented base
has already earned the bypass; they just cannot drive the decision.

**Test:** `test_local583_documented_works.py` (9/9) — the exact 23 cached chrome
titles → 0 documented; no bypass; site-first eligible; real catalogue+SPARQL
still count; plus source-wiring assertions that both gates use the documented
count and the old `len(_det_documented)` gates are gone.

### D2 — The cache stores no chrome  (commit 2)

- **`exhibition_discovery.is_chrome_title(title, venue_name="")` /
  `reject_chrome_titles(titles, venue_name="")`** — a pure-string, structural
  chrome classifier (no HTML, no network). It is the string residue of the same
  `<nav>`/`<footer>`/widget structure the LOCAL-580 DOM pass rejects, expressed
  as page-furniture vocabulary — **not a blocklist of show names**:
  - whole-title generic/chrome labels (`_GENERIC_HEADING_LABELS` +
    `_CHROME_EXACT_LABELS`: "our team", "terms conditions", "membership levels",
    "calls for entry", …);
  - FAQ/help form (title begins with an interrogative — "When Are The Member
    Portfolio Reviews Scheduled");
  - a title whose every word is a chrome-lexicon token, a venue-name word, or a
    function/number filler **and** that carries ≥1 chrome token
    ("Griffin Travel", "Griffin Museum Board Of Directors 2").
  A title with any distinctive content word survives — real shows
  ("Intertidal : Field Notes", "Earth, Wind & Fire", "TLC", "Lua Kobayashi")
  are never touched.
- The **canonical-title union runs through `reject_chrome_titles` before it is
  written to `venue_corpus`** — at the call site in `generate_tour_text.py` and,
  defense-in-depth, inside `venue_resolver.cache_put` so no caller can write
  chrome. SPARQL works are left untouched (Wikidata-verified, not site-scraped).
- **`venue_resolver.CORPUS_VERSION` 4 → 5.** `cache_get` filters
  `WHERE … corpus_version = %s`, so **every row the old plaintext extractor
  wrote is now a cache MISS — ignored, never DELETEd.** The Griffin chrome row
  stays on disk at v4 (LEAD's backup also preserved).

**Test:** `test_local583_chrome_rejection.py` (10/10) with the **exact 23 cached
titles** from LEAD's backup `venue_corpus_Q99108607_backup_20261005_1242.sql`:
all 16 unambiguous chrome labels rejected, all 8 real LOCAL-580 shows survive,
`CORPUS_VERSION ≥ 5`, cache_get version gate + cache_put chrome filter asserted.

> Two of the 23 cached strings are genuinely ambiguous as **bare strings** —
> "Nepr 2026" (an event acronym) and the mangled real shows the old extractor
> stripped of punctuation ("Intertidal Field Notes", "Earth Wind Fire"). A
> string filter must not reject those (they would wrongly drop real shows), so
> the belt-and-braces design is: **the string filter removes the unambiguous
> furniture going forward, and the `corpus_version` bump makes the whole old row
> a miss** so none of the 23 ever reaches a tour from cache.

### D3 — Speed, without losing a quality gate  (commit 3)

**(a) P856 "official site of an institution" check not run against arbitrary
third-party domains.** `source_tier_rules.json` `reject_platforms` now includes
the UGC / aggregator / people-search / travel-booking families
(tripadvisor, yelp, idcrawl, spokeo, whitepages, viator, getyourguide, booking,
expedia, eventbrite, foursquare, yellowpages, crunchbase, glassdoor, indeed,
patch, nextdoor, wikimapia/wikitravel/wikivoyage, …). `_classify_domain_quick`
short-circuits these to `reject` **with no network call**. This is *not* a gate
removal: an unknown domain and legitimate local news (e.g. `wickedlocal.com`)
still get the P856 check. And `EXTERNAL_LOOKUP_PER_TIMEOUT` is **8 s → 3 s**
(env-overridable); a real Wikidata ASK answers in < 1 s, and the per-tour
dead-host breaker short-circuits the rest of the run after the first timeout.
The verdict is unchanged — a timeout is `unverified` (D495/LOCAL-459), never a
tier3 demotion.

**(b) No Overpass/OSM for exhibit-museum interior stops.** A temporary
exhibition has no OSM node (the D569 church-tour pattern: N doomed Overpass
calls, ~200 s). The LOCAL-355 block now detects exhibition-sourced stops
(`_stops_are_exhibitions`) and queries **OSM ONCE for the museum building**
(admission/hours apply to the whole museum) instead of once per show name.

**Test:** `test_local583_speed.py` (10/10) — aggregators quick-reject with no
P856; legit news/venue still reach it; short + env-overridable timeout;
single-museum-building OSM query wired. Source-tier regressions
(`test_sq2_fixtures`, `test_d495_source_ranking`, `test_local427_fetch_backoff`)
**43/43**.

**(c) Top 5 time sinks after the fix** (live Griffin, RUN2, `[TIMING] TOTAL`):

| # | Phase | RUN2 | RUN1 | Field trace | What it is |
|---|---|---:|---:|---:|---|
| 1 | `story_first` | 374.3 s | 377.5 s | 380.6 s | **LOCAL-432 story-sufficiency gate** — ≥3 story sentences/stop, gpt-4.1, `_max_retries=4` (11–14 retries across the thin exhibition stops) |
| 2 | `external_lookups` | 145.9 s | 171.7 s | 189.3 s | **LOCAL-410/488 story search** — 16 SERP queries, 3 providers, cross-model lead agreement |
| 3 | `site_first_exhibitions` | 34.6 s | 34.4 s | — | LOCAL-580 site-first: fetch the listing + each `/show/` detail page |
| 4 | `fact_sheets` | 10.1 s | 9.0 s | — | per-stop fact extraction |
| 5 | `poi_selection` | 7.0 s | 6.9 s | **171.4 s** | **was** the per-stop Overpass storm — now one museum-building OSM call |

The two defects this ticket named are fixed and measured:
**poi_selection 171.4 s → ~7 s** (the Overpass fix) and the P856 external-lookup
storm is gone (3 tiny parallel batches, ~3 s; the one surviving timeout is a
single real Wikidata read-timeout for an unknown domain, after which the
breaker short-circuits).

**I did not hit the 5-minute target, and per the ticket I am stopping rather
than removing a quality gate.** After the P856 and Overpass fixes, the dominant
remaining cost (≈ 520 s of 598 s) is the **LOCAL-432 story-sufficiency gate**
(ranks #1) plus the **LOCAL-410/488 story search** (ranks #2). These are the
quality gates that ground each stop's narrative; they are expensive *for an
exhibition museum specifically* because new/temporary/student shows have thin
third-party coverage, so the ≥3-stories retry exhausts its 4 retries per stop.
The ticket is explicit: "Do not remove a quality gate to get there. If one is
the cost, say so and stop." The cost is the story gate; it is left intact.
(The `STORY_RETRY_EARLY_STOP` / `STORY_RETRY_KEEP_BEST` cost switches from the
subscribed override are not wired into the storied LOCAL-432 loop this branch is
based on; wiring them is a `subscribed`-side change, out of scope here.)

### D4 — Live in the CONTAINER (D608), Griffin twice  (commit 4)

Rebuilt `tour-generator` from **this worktree** with a worktree-local
`docker-compose.subscribed-local.yml`. The canonical subscribed-local override
builds a *separate* `origin/subscribed` checkout — exactly the D358 trap for a
`storied`-based branch — so this override keeps master's `context: .` (builds
LOCAL-583 code) and layers only the cost/model switches
(`STORY_RETRY_KEEP_BEST`, `STORY_RETRY_EARLY_STOP`, `TOUR_STORY_MODEL=gpt-4.1`).

```
docker compose -p audioura \
  -f docker-compose-master.yml \
  -f docker-compose.subscribed-local.yml \
  up -d --no-deps --build tour-generator
```

In-container verification (my code is live): `git_sha = 3579fc8`,
`CORPUS_VERSION = 5`, `EXTERNAL_LOOKUP_PER_TIMEOUT = 3`,
`is_chrome_title('Our Team', 'griffin museum of photography') = True`.

Ran `Griffin museum of photography, Winchester, MA` (museum, 5 stops) **twice**
via `docker exec`, gpt-4o, **OpenAI hard cap $3.00** (`COST_HARD_LIMIT_USD`).

**RUN 1** — `LOCAL583_GRIFFIN_RUN1.txt`, log `LOCAL583_D4_RUN1.log`
```
[LOCAL-580] 0 documented works for 'Griffin Museum of Photography' — exhibition-museum site-first path ELIGIBLE
PHASE 3A: SKIPPED (LOCAL-580 site-first — 9 current exhibition(s) from the venue site)
[LOCAL-355] [LOCAL-583] Exhibit-museum: querying OSM ONCE for the museum building 'Griffin Museum of Photography' (not per-exhibition — a show has no OSM node)
[TIMING] TOTAL wall=633.1s phases: story_first=377.5s, external_lookups=171.7s, site_first_exhibitions=34.4s, packing=16.7s, fact_sheets=9.0s, poi_selection=6.9s, intent=1.9s, narration=0.0s, verification=0.0s
```
Stops (4/5): BU Masters Show 2026 | Traces: Pursuing Process · Earth, Wind & Fire ·
Tabitha Soren | An Artist Life · Lua Kobayashi | The Persistence of Memories

**RUN 2** — `LOCAL583_GRIFFIN_RUN2.txt`, log `LOCAL583_D4_RUN2.log`
```
[TIMING] TOTAL wall=598.2s phases: story_first=374.3s, external_lookups=145.9s, site_first_exhibitions=34.6s, fact_sheets=10.1s, packing=7.2s, poi_selection=7.0s, intent=1.3s, narration=0.0s, verification=0.0s
```
Stops (5/5): BU Masters Show 2026 | Traces: Pursuing Process · Earth, Wind & Fire ·
Tabitha Soren | An Artist Life · TLC · Lua Kobayashi | The Persistence of Memories

**Both runs deliver real, current Griffin exhibitions — no chrome, no "Board Of
Directors", no "Calls For Entry".** The defect is fixed: the 23 cached chrome
titles no longer count as documented works, so site-first runs; and the stops
reproduce across runs.

> Note on "fresh cache": the LOCAL-580 **site-first exhibition path does not
> write `venue_corpus`** (that write lives on the permanent-collection D1v2
> path). So no v5 row is created for Griffin — RUN 2 re-runs site-first and
> still produces the same shows (reproducible by construction). The D2 chrome
> filter + `corpus_version` bump are what protect the cache for venues that *do*
> take the collection path; both are proven by `test_local583_chrome_rejection.py`.

## Data safety

- `audio_tours`: **203 before → 203 after** (declared via
  `select count(*) from audio_tours`). The harness calls `generate_tour_text`
  directly and writes files only — no rows created, **none deleted**.
- `venue_corpus` Q99108607: the v4 chrome row is **preserved** (23 titles,
  corpus_version 4). It is a cache MISS at v5 — ignored, **never DELETEd**.

## Tests

| Suite | Result |
|---|---|
| `test_local583_documented_works.py` (D1) | 9/9 |
| `test_local583_chrome_rejection.py` (D2, 23-title fixture) | 10/10 |
| `test_local583_speed.py` (D3) | 10/10 |
| `tests/test_local30_deterministic_selection.py` (regression) | 8/8 |
| `test_local580_structural_extraction.py` / `_site_first_candidates` / `_fabrication_guard` / `_actionable_failure` | 25/25 |
| `test_local582_museum_overview.py` | all pass |
| `test_sq2_fixtures.py` / `test_d495_source_ranking.py` / `test_local427_fetch_backoff.py` | 43/43 |

**Pre-existing, NOT caused by this change:** `test_local441_concurrent_lookups.py`
has 2 failures (`test_budget_expires_treats_as_tier3`, `test_mixed_fast_and_slow`)
that assert budget-expired → `'tier3'`; the code already returns `'unverified'`
(D495/LOCAL-459). Verified these fail identically on the `storied` base with the
unmodified `work_story_searcher.py` — stale tests, out of scope for this ticket.

## Files

New: `exhibition_discovery.py` (+chrome rejection), `test_local583_documented_works.py`,
`test_local583_chrome_rejection.py`, `test_local583_speed.py`,
`run_local583_container.py`, `docker-compose.subscribed-local.yml`,
`LOCAL583_GRIFFIN_RUN1.txt`, `LOCAL583_GRIFFIN_RUN2.txt`,
`LOCAL583_D4_RUN1.log`, `LOCAL583_D4_RUN2.log`.
Edited: `generate_tour_text.py` (D1 documented-count gates; D2 canonical-union
chrome filter before cache write; D3 single museum-building OSM query),
`venue_resolver.py` (CORPUS_VERSION 4→5; chrome filter in cache_put),
`source_tier_rules.json` (reject_platforms expansion),
`work_story_searcher.py` (P856 per-lookup timeout 8s→3s, env-overridable).

No GCloud. DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
.continuous_dev/STATUS.md untouched.
