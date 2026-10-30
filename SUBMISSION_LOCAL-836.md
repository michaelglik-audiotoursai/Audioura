# SUBMISSION — LOCAL-836: dense single-named-anchor walking tour refills to N

**Branch:** `LOCAL-836-dense-walk-refill`
**Base:** subscribed — HEAD `e63000db` (`git merge-base --is-ancestor e63000db HEAD` → 0)

## The defect

> "Ben Thanh Market walking tour, Ho Chi Minh City" (4) → **2/4** on the cloud
> (Saigon Square, Ben Thanh Market), $0.096, no Gemini (GCloud_Storied wave 13
> proof 508, gen 00019-k5x / orch 00011-tjn).

District 1 around Ben Thanh is one of the densest walkable areas in Vietnam, so
2/4 is never honest. LOCAL-816/818's refill did not reach 4.

## Root cause (reproduced OFFLINE on the Mac, no network)

"Ben Thanh Market" is a **single named anchor** — a *point feature* (a market),
not a containable area. The LLM intent echoes it into `geographic_scope`
(`"Ben Thanh Market, District 1, Ho Chi Minh City"` precision DISTRICT, or the
bare `"Ben Thanh Market"` precision BUILDING). `_resolve_scope_for_check` then
hands that **market point** to the D558 containment check as the tour's scope, so
every real nearby landmark (the Opera House, Bitexco, the Post Office, the Museum
of Fine Arts) is judged *"near Ben Thanh Market but not INSIDE the market"* and
rejected. Discovery searches the whole city (`_gp_city = location`), but each
replenishment round's candidates are then validated against the market point and
dropped — so the loop reports `0/N inside` and the tour ships 2/4.

Neither prior fix covers this shape — it falls **between** them:

* **LOCAL-805** widens a `"<business> near <landmark>"` scope, but only when a
  locative connector (`near`/`around`/`in`) sits in the subject segment.
  `"Ben Thanh Market walking tour, HCMC"` has **no connector**, so
  `_near_landmark_enclosing_area` returns `None` and does not widen. (The subject
  *does* classify as business — a market — but with no connector LOCAL-805 never
  fires.)
* **LOCAL-816** widens a **list of ≥ 2** named anchors (`"Trevi, Pantheon and
  Navona, Rome"`). A single leading anchor is `< 2`, so `_anchor_list_enclosing_area`
  returns `None`.

Proven with a direct `_resolve_scope_for_check(...)` trace and a deterministic
`replenish_to_count` run: with the point-anchor scope the loop rejects every
candidate (stays 2); the enclosing-area scope accepts them (reaches 4).

## The fix (general, in the ONE place that decides the scope)

`generate_tour_text.py`:

1. **`_anchor_is_point_feature(anchor, intent)`** — True when an anchor is a named
   point feature / POI (its head's last word is a landmark **class noun**:
   *lake, market, square, fountain, cathedral, temple, pagoda, tower, bridge,
   palace, opera house, museum, station, park, gardens, …* — a broad global set
   `_POINT_FEATURE_CLASS_WORDS`), and False for a genuine administrative area.
   Guarded against known neighbourhood / region markers (via
   `places_search._NEIGHBOURHOOD_MARKERS` / `_REGION_MARKERS`) so "Hyde Park",
   "West Roxbury" etc. stay areas. **It is LOCAL to `generate_tour_text`; it does
   NOT touch `places_search._scope_precision`, so the LOCAL-805 radius canary is
   untouched.** (That classifier is too fragile here — it reads "Hoan Kiem Lake"
   and "Sydney Opera House" as NEIGHBOURHOOD — which is exactly why this is a
   dedicated detector.)

2. **`_single_anchor_enclosing_area(scope, location, intent)`** — fires when the
   request is `"<Anchor> walking tour, <City>"` with **exactly one** leading
   anchor (`_leading_anchor_list`), the anchor is a **point feature**, and the
   scope's leading segment **is** that anchor. Returns the enclosing area (the
   scope's admin tail, e.g. `"District 1, Ho Chi Minh City"`; else the city the
   request names, e.g. `"Ho Chi Minh City"` / `"Hanoi"`); returns `''` when the
   point has no enclosing area at all (radius only — skip the stop-by-stop check,
   like LOCAL-805's point-landmark case); returns `None` (leave as is) for a
   genuine district, a ≥ 2 anchor list (→ LOCAL-816), or an empty scope.

3. **Wired into `_resolve_scope_for_check`** immediately after the LOCAL-816 block
   and before the D536 waypoint refusal, mirroring the LOCAL-805/816 widenings
   exactly (keeps the intent copy in step so the LOCAL-591 one-scope invariant
   does not then clear the widened scope). An `''` result distinctly clears the
   scope; a non-empty result becomes the DISTRICT-level containment area.

Why this is sufficient: discovery already searches the city
(`_gp_city = location`); the bug was purely the containment scope rejecting the
nearby candidates. Widening the scope lets the SAME resolver/validator/proposer
(LOCAL-576 pre-write check, the D556 replenish loop, and the LOCAL-818 post-drop
refill — all of which call `_resolve_scope_for_check`) keep real nearby landmarks
and reach N. No new pipeline stage.

## POST latency (ticket item 3): DROPPED

Cloud Run logs show the orchestrator answers `POST /generate-complete-tour` in
0.29 s; the > 60 s was the laptop's own connection (GCloud_Storied, 2026-10-30).
No code change.

## Tests

New: `tests/test_local836_single_anchor_scope.py` — **17/17 green**. Pins the
single point-feature anchor widening (Ben Thanh DISTRICT + BUILDING intents, Hoan
Kiem Lake), the three genuine districts left UNCHANGED (Westminster, Lower
Manhattan, Asakusa) + Beacon Hill, the multi-anchor hand-off to LOCAL-816, the
point-with-no-area `''` case, and — end to end — that the real `replenish_to_count`
loop reaches N with the widened scope and cannot without it.

Regressions named in the ticket (all pass):
`790, 791/791b/791c/791e, 801, 802, 805, 805b, 813, 816, 818, 830` →
**335 passed, 2 skipped**. (`835` does not exist in the repo.) Plus a wider sweep
of the scope/walking/named-place surface this change touches
(`591×2, 646, 650, 751, 799, 576, 790`) → **131 passed, 5 skipped**.
`tests/test_local820_meter_wiring.py` passes for the new wrapper
(`run_local836_live.sh`); the one failing node there (`run_local830_live.sh`) is a
**pre-existing** gap on base `e63000db`, not this change.

## Live — BUDGET ENFORCED (PASS)

Isolated container (own project `local836`, own throwaway postgres; never
`-p audioura`, never a shared `audioura-*` container, never the live DB). Cheap
arm (`NARRATION_MODEL=gpt-4.1-mini`, `RESEARCH_BACKEND=serper`), cache off, pool
off. `TASK_BUDGET_ID=LOCAL-836 TASK_BUDGET_USD=0.50`, meter contract
(`METER_SERVICE=LOCAL-836`, rows → `~/Audioura/meterlogs/paid_api_calls.jsonl`).

| Tour | Delivered | Verdict | Cost | Gemini |
|------|-----------|---------|------|--------|
| **Ben Thanh Market walking tour, Ho Chi Minh City** (4) | Takashimaya Vietnam · Saigon Square · Ben Thanh Market · HCMC Museum of Fine Arts | **4/4 PASS** | $0.1320 | $0 |
| **Hoan Kiem Lake walking tour, Hanoi** (5) | Turtle Tower · Water Puppet Theatre · Ngọc Sơn Temple · St. Joseph's Cathedral · Hang Gai Street | **5/5 PASS** | $0.2762 (run) | $0 |

Both: real nearby landmarks within the ~1.5 km walkable area, no shortfall
apology. Combined spend well under the $0.50 cap; no Gemini grounding. (The
`relation "audio_tours" does not exist` lines are only the throwaway postgres
lacking the app schema — the store/count fall back to `None`; the PASS verdict is
the delivered stop count and is unaffected.)

## Files changed

* `generate_tour_text.py` — `_POINT_FEATURE_CLASS_WORDS`,
  `_anchor_is_point_feature`, `_single_anchor_enclosing_area`, and the wiring in
  `_resolve_scope_for_check`.
* `tests/test_local836_single_anchor_scope.py` — new unit tests.
* `run_local836_container.py`, `run_local836_live.sh` — isolated, budget-enforced,
  metered live harness (LOCAL-820 contract).

Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
TRAVEL_PROJECTS.md. No `DELETE`. Live DB never written. No `audioura-*` container
touched.
