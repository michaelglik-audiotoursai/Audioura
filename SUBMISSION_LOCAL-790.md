# SUBMISSION — LOCAL-790: Walking tours outside the US/Europe no longer reject every real place

**Branch:** `LOCAL-790-walking-gate-intl`
**Base:** `subscribed` @ `65ff03c3` (LOCAL-788B merged) — `git merge-base --is-ancestor 65ff03c3 HEAD` exits 0.

## Problem

Two Ho Chi Minh City walking requests failed twice each with "no stops could be
generated" (GCloud_Storied P4, 2026-10-27; ClickUp wdvrdaz6u5):

- `French colonial architecture and Vietnamese culture walk, District 1 and 3, Ho Chi Minh City` (5)
- `Pagodas and temples of Ho Chi Minh City (Jade Emperor Pagoda, Thien Hau Temple)` (5)

The walking-tour existence gate rejected EVERY candidate — including Notre-Dame
Cathedral Basilica of Saigon and Ben Thanh Market, both real with addresses —
because outside the US/Europe Wikidata gave 0 in-area hits and **places_search /
Serper was never called**. Six root causes, all fixed here.

## The six causes and fixes

| # | Cause | Fix | File |
|---|-------|-----|------|
| 1 | Walking existence gate called only Wikidata + Nominatim; `places_search`/Serper never ran, and the proximity anchor was geocoded from the first capitalised token ("Ho" of "Ho Chi Minh City"). | `_check_walking_stop_existence` now takes `scope`, geocodes the FULL scope (`_geocode_scope_center`/`_geocode_scope_bbox`, LOCAL-783/786) as the anchor+bbox, and routes the map lookup through `_places_lookup` (Serper Places first, Nominatim fallback). Logs `[LOCAL-790] evidence <title> <source> <km>`. `scope` threaded through `verify_stop_existence` and `run_existence_gate`. | `stop_existence_gate.py` |
| 2 | Replenishment never ran from 0 candidates for a landmark/walking tour — only business/dining had a from-zero refill — so an emptied list hit "All POIs were filtered out; cannot continue". | The LOCAL-290 GPT→gate replenishment loop now runs FROM ZERO for place-based landmark/walking tours (`classify_business_vs_landmark == 'landmark'`), places-first via the now-fixed gate. | `generate_tour_text.py` |
| 3 | D571 VENUE-PARTS treated "Pagodas and temples of HCMC" as ONE venue (`pagoda`/`temple` matched the worship-civic detector) and asked for its parts; anchor=None. | `_is_plural_category_area_request` detects a plural category bound to an area ("Pagodas and temples of <city>", "<category>s in/of <area>"); `_detect_venue_class` returns None and `_should_force_museum` returns False for it → routed as a MULTI-VENUE walking tour. Parenthetical named examples are anchors, not parts. | `generate_tour_text.py` |
| 4 | The area parser read "District 1 and 3" as a city, and comma-less "Pagodas and temples of HCMC" as a city. | `_parse_location` strips a leading plural-category "… of/in <area>" prefix and pre-joins a comma-separated district clause; `parse_districts` expands "District 1 and 3"/"Quận 1 và 3" into per-district strings; `resolve_area` geocodes each district and UNIONS the bboxes (`AreaResolution.union_bbox`). `_scope_from_request` reattaches the city when PHASE 1 returns a bare district scope. | `area_resolver.py`, `generate_tour_text.py` |
| 5 | A NAMED parenthetical anchor (Thien Hau Temple) was dropped — `named_anchors` only read "from X to Y via …" route grammar. | `named_anchors` now also extracts a trailing parenthetical list "(Jade Emperor Pagoda, Thien Hau Temple)" as anchors; they flow into `_apply_named_waypoints` and are inserted/protected. | `generate_tour_text.py` |
| 6 | "Ngoc Hoang Pagoda" (Vietnamese) and "Jade Emperor Pagoda" (English) are the same place but title-only dedup kept both (no shared tokens); the QID/bilingual dedup ran only on the museum path. | `identity_dedup.dedupe_by_location_or_qid` collapses a place pool by Wikidata QID, by geocoded location (≤ 60 m), or by title fallback; wired into the WALK-D1 path after Wikidata coordinates are assigned. | `identity_dedup.py` |

## Tests

`tests/test_local790_walking_gate_intl.py` — 28 offline deterministic tests (causes
2, 3, 4, 5, 6, each with the exact field request text) + 2 live-gated existence
tests (cause 1, `LOCAL790_LIVE=1`; Serper is paid so CI stays offline). All 28
offline pass.

**Regression (only NEW failures count).** The 29 affected test files (LOCAL-662,
LOCAL-571/D571, LOCAL-786, LOCAL-788/788B, LOCAL-779/779B, LOCAL-320, LOCAL-485,
LOCAL-576, LOCAL-669b/c, LOCAL-751, …): **385 passed, 45 skipped**. The only
non-passes are `test_local293`/`test_local294` (live Wikidata SPARQL) which crash
or skip on HTTP 503 at a PRE-EXISTING print line (`area_resolver.py` "City
resolved:", NOT in this diff) — pure network flakiness, present on the baseline
tree. Deterministic/offline affected subset: **257 passed, 10 skipped, 0
failures**. No new failures attributable to this change.

## Live test (isolated, own containers, cap $2.00)

Own postgres aliased `postgres-2` on an own network `local790_net`, the
`audioura-tour-generator:latest` image with this worktree mounted (so the live run
measures THIS code). The 14 shared `audioura-*` containers were never touched;
the isolated stack was torn down afterwards. `run_local790_container.py`.

**Total task spend: $1.56 / $2.00** (pagodas $0.577, architecture $0.552, Boston
$0.431), enforced by `tests/live_run_meter.py`.

| Request | Result |
|---------|--------|
| Pagodas and temples of HCMC (Jade Emperor Pagoda, Thien Hau Temple), 5 | **Jade Emperor Pagoda, Thien Hau Temple, Vinh Nghiem Pagoda, Ba Thien Hau Pagoda, Giac Lam Pagoda** — both named anchors present. Log: `[LOCAL-790] evidence 'Chùa Ngọc Hoàng (Jade Emperor Pagoda)' serper_places 2.9km`, gate REPLACED an inconclusive stop with the Serper-verified one. |
| French colonial architecture, District 1 and 3, HCMC, 5 | **Saigon Notre-Dame Basilica, Saigon Central Post Office, People's Committee Building, Museum of Fine Arts, Reunification Palace** — all real District 1/3 landmarks. |
| Boston Freedom Trail walking tour, Boston MA, 4 | **Boston Common, Massachusetts State House, Park Street Church, Granary Burying Ground** — US canary unchanged. |

Both HCMC requests previously clean-failed ("no stops could be generated") and now
deliver 5 real places each. Delivered tours were stored as additive `is_test`
rows in the isolated DB; no `DELETE`.

## Files changed

- `stop_existence_gate.py` — cause 1 (walking existence via places_search + scope geocode/bbox; `scope` threaded through `verify_stop_existence`/`run_existence_gate`; `_serper_enabled` helper).
- `generate_tour_text.py` — causes 2 (replenish from 0), 3 (plural-category detector), 5 (parenthetical anchors), 4 (scope reattach of city), and gate `scope` wiring.
- `area_resolver.py` — cause 4 (plural-category prefix strip, `parse_districts`, district union bbox, `_nominatim_bbox`).
- `identity_dedup.py` — cause 6 (`dedupe_by_location_or_qid`).
- `tests/test_local790_walking_gate_intl.py` — new unit tests.
- `run_local790_container.py` — live acceptance runner.

No protected files were edited (DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md). No `git add -A`; no `DELETE`.
