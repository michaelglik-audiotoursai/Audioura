# SUBMISSION — LOCAL-600: a show's works follow the show, and an honest shortfall is told to the listener

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-600-exhibit-order-shortfall`
**Base:** `subscribed` @ `b8738d1`
(`git merge-base --is-ancestor b8738d1 HEAD` → exit 0)

## Why (LEAD, from the LOCAL-599 r3 live run, 2026-10-06)

MassArt delivered 5 verified on-view stops for 7 requested (correct per D615: no
past shows, no padding). Two listener-facing problems remained:

1. **Order.** The delivered stops were
   `Stop 1: Robert Lazzarini: American flag` (a WORK) … `Stop 3: Robert Lazzarini`
   (its SHOW) — the work came before its own show, two stops apart. Stop 1's
   orientation then said "Your first stop is Robert Lazzarini", which didn't match
   its title.
2. **A silent shortfall.** The listener asked for 7 and got 5 with no explanation.

The site-first candidate builder already emits show→its-works per exhibition
(`exhibition_site_first.build_site_first_candidates`), but the delivery reordered
them by KIND — the two WORK stops led and their shows came after.

## Ruling implemented (D616, LEAD)

> When verified on-view material can't reach N, deliver the verified stops and
> **say so in Stop 1's opening section** — one plain sentence from the real counts:
> "MassArt Art Museum currently has 3 exhibitions on view, so this tour has 5 stops
> rather than the 7 you asked for." The app's stop count shows the delivered number.
> This is the only exception to D611's exact N, and applies only to the
> exhibition-museum (site-first) path.

## Deliver

### 1 — Grouping: each exhibition first, then its works (commit 1)

`generate_tour_text.py`:
- Each site-first POI is tagged at creation with `_sf_kind`
  (`exhibition`/`work`/`museum_space`), `_sf_status`, `_sf_group_key` (the show's
  `detail_url` — a work shares its show's key) and `_sf_order` (its original
  site-first position).
- A new pure `_regroup_site_first_stops(poi_list)` runs just before the stop text
  is rendered **and before the headroom trim**: it groups by `_sf_group_key` so
  each exhibition stop leads, then its works in original order, with groups ordered
  by the earliest `_sf_order` — preserving the existing route/story order BETWEEN
  shows. Only the pure site-first path is touched (every POI
  `source == 'site_exhibition'`); a mixed/other tour is returned unchanged; a stop
  is never dropped or duplicated. Because the orientation names `poi_list[0]`,
  Stop 1 is now always a show and the orientation names it.

### 2 — The honest shortfall sentence (commits 1–2)

`about_museum_stop.py`:
- `build_shortfall_sentence(venue, exhibitions_on_view, delivered_stops,
  requested_stops)` — one plain sentence from the real counts; **present only when
  delivered < requested** (D611 exact N otherwise), with singular/plural grammar
  and guards for bad counts. Pure, no network.
- `build_opening_section(about, shortfall_sentence="")` places that sentence as its
  own paragraph **right after the About story and before the practical notes**, so
  the listener hears the scope up front. The artwork-framing fallback keeps the
  shortfall note.

`generate_tour_text.py` records the real counts for the delivery in
`_LAST_SITE_FIRST_COUNTS` (`exhibitions_on_view` = distinct on-view SHOWS,
`delivered_stops`, `requested_stops`), computed from the FINAL re-grouped/trimmed
list.

`stop_pool_orchestrator.py` builds the sentence after generation and folds it into
Stop 1 — in the **first-tour** path and, because the LOCAL-599 r3 run already
pooled MassArt works-first, in the **pooled** paths too (commit 2):
- `_regroup_pooled_units` groups each pooled show ahead of its own works (a work's
  title is `Artist: Work`, the show is the bare `Artist`), applied in the N≤K, N>K
  and pool-only paths; in N≤K the regroup runs BEFORE selecting N so slicing never
  splits a group.
- `_site_first_shortfall_sentence` reads the engine counts; the N>K / pool-only
  paths fall back to counting shows (non-work titles) among delivered units.
- A new pool-only branch: when a contained exhibition museum has no more on-view
  material beyond the K pooled, it serves the K pooled stops **with the shortfall**
  instead of abandoning the pool and re-running the pipeline.

### 3 — Tests (commits 1–2)

`tests/test_local600_order_and_shortfall.py` (new):
- **grouping order** on the real MAAM fixtures (3 shows + 2 works) and on the exact
  r3 works-first failure shape — each work sits immediately after its own show,
  Stop 1 is a show, inter-show order preserved, nothing dropped/duplicated;
- **shortfall sentence present at 5/7** (verbatim D616 example) and **absent at
  7/7** (and when over-delivered, and with bad counts); singular grammar; folded
  after the About story in the opening section;
- **Griffin, which reaches N with shows alone, is UNCHANGED**: the regroup is a
  no-op and no shortfall sentence is emitted (delivered == requested);
- the pooled regroup (works-first → grouped) and safety (non-site-first list
  untouched, museum space keeps position);
- wiring assertions prove the engine calls `_regroup_site_first_stops` / records
  `_LAST_SITE_FIRST_COUNTS` and the orchestrator calls `build_shortfall_sentence`
  / `_regroup_pooled_units`.

#### Suite exits (all 0)

```
tests/test_local600_order_and_shortfall.py                        24 passed   EXIT=0
tests/test_local599b_maam_exhibitions.py
  + _opening_section.py + _official_site_discovery.py             33 passed   EXIT=0
test_local589_*.py                                                25 passed   EXIT=0
test_local592_*.py                                                51 passed   EXIT=0
test_local590_orchestrator/_assembly + test_local585_*            48 passed   EXIT=0
```

### 4 — Live run (isolated container `local600-gen`, cap $1.50) (commit 3)

`docker run --rm --name local600-gen` on `development_default`, DB `postgres-2`,
tour cache OFF, `COST_HARD_LIMIT_USD=1.50`, routed through
`stop_pool_orchestrator.maybe_generate_with_pool`. No `audioura-*` container
touched. Runner: `run_local600_massart.py` / `run_local600_live.sh`.

**`MassArt Art Museum, Boston, MA`, 7 stops. TIER: `exhibit_museum`.**
Site discovered `https://maam.massart.edu/` (web_search, score 9). The venue has 5
verified on-view stops; the pool held those 5 (from the r3 run). On-view material
honestly reaches 5, short of 7 — delivered 5, **grouped and with the shortfall
announced**.

#### The stop titles, each with its source URL

```
Stop 1: Robert Lazzarini                              https://maam.massart.edu/exhibition/robert-lazzarini  [exhibition/on_view]
Stop 2: Robert Lazzarini: American flag               https://maam.massart.edu/exhibition/robert-lazzarini  [work/on_view]
Stop 3: Banu Cennetoğlu                               https://maam.massart.edu/exhibition/banu-cennetoglu   [exhibition/on_view]
Stop 4: Baseera Khan                                  https://maam.massart.edu/exhibition/baseera-khan      [exhibition/on_view]
Stop 5: Baseera Khan: Second Skin, Half Column 3      https://maam.massart.edu/exhibition/baseera-khan      [work/on_view]
```

Each exhibition's stop comes first, immediately followed by its own works — the r3
works-first order is fixed. Stop 1 is a show, and the orientation names it ("Your
first stop is Robert Lazzarini").

#### Stop 1 opening section (in full)

```
Stop 1: Robert Lazzarini

Address: 621 Huntington Avenue, Boston, Massachusetts

Coordinates: 42.3399, -71.0942

Before we look at anything on the walls, here is the story of MassArt Art Museum
in Boston, Massachusetts itself — who created it, why it exists, and what it is
known for. The MassArt Art Museum (MAAM) is Boston's only free contemporary art
museum, a space to experience works by extraordinary artists at the forefront of
contemporary art. This account is drawn from the museum's own pages on
maam.massart.edu.

MassArt Art Museum currently has 3 exhibitions on view, so this tour has 5 stops
rather than the 7 you asked for.

The MassArt Art Museum is open Thursday, 12 PM–8 PM; Friday, 12 PM–5 PM;
Saturday, 12 PM–5 PM; Sunday, 12 PM–5 PM. Admission is FREE, as listed on
maam.massart.edu in October 2026.

Orientation: You are about to explore the MassArt Art Museum in Boston. … Your
first stop is Robert Lazzarini. …
```

The D616 shortfall sentence sits right after the About story, before the practical
notes — built from the real counts (3 exhibitions on view, 5 delivered, 7 asked).

#### BLOCKER 3 (content-QA factual gate)

```
  BLOCKER 3 line 1 — PASS checks:          19
  BLOCKER 3 line 2 — style FAIL checks:    1   (cross-stop repetition — pre-existing pooled narration, not from this change)
  BLOCKER 3 line 3 — FACTUAL FAIL checks:  0
```

#### Tour total

```
Tour total: $0.4251  cache_hit=False  wall_time=221.3s
```

Well under the $1.50 cap.

#### Pool hygiene

No DELETE. The run added **no** stray rows: the MassArt pool held 5 rows before
and after (the nested new-stop generation found no on-view material beyond the 5
already pooled, so it pooled nothing new). Delivery re-groups the pooled stops at
serve time, which is what the listener sees.

## Files changed

- `generate_tour_text.py` — tag site-first POIs; `_regroup_site_first_stops`;
  record `_LAST_SITE_FIRST_COUNTS`.
- `about_museum_stop.py` — `build_shortfall_sentence`; `build_opening_section`
  shortfall paragraph.
- `stop_pool_orchestrator.py` — `_regroup_pooled_units`;
  `_site_first_shortfall_sentence`; shortfall folded in the first-tour, N≤K, N>K
  and new pool-only paths.
- `tests/test_local600_order_and_shortfall.py` — new.
- `run_local600_massart.py`, `run_local600_live.sh` — isolated live runner.
