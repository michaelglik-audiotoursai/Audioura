# SUBMISSION — LOCAL-838: "Ben Thanh Market walk" routed to the places path as a restaurant tour, overriding tour_type=walking

**Base:** subscribed @ `ce18fca3` — `git merge-base --is-ancestor ce18fca3 HEAD` exits 0 (verified before every commit).
**Branch:** `LOCAL-838-walk-beats-805`

## The defect (GCloud_Storied wave 14 proof, gen 00020-2q6 @ ce18fca3, cheap env)

Request **"Ben Thanh Market walk, Ho Chi Minh City – proof"** arrived with
**tour_type=walking**. LOCAL-805's business/near-landmark routing classified the
SUBJECT — "Ben Thanh Market" is a market, therefore a business — and sent the
request down the PLACES path as `category='restaurant'`, **overriding the app's
explicit walking type**. Because the request never reached the walking path,
LOCAL-836's walkable-area widening never ran, and the tour shipped **2/4** (the
market plus a Bánh Bèo stall). (Request 306 then failed for a separate reason —
the modernized job store — fixed by config on the cloud, out of scope here.)

Two independent causes, both reproduced deterministically before the fix:

### 1. Routing — 805 business-subject override beat the explicit walking type
`_classify_tour_category` ran the LOCAL-805/791 business-subject branch before any
walking-precedence check, and the Touchpoint-1 suppression at the call site then
blanked `tour_type` because `_pre_category=='restaurant'`:
```
_classify_tour_category("Ben Thanh Market walk, HCMC", "")        → 'restaurant'  (before)  →  'walking'  (after)
_classify_tour_category("Ben Thanh Market",            "walking") → 'restaurant'  (before)  →  'walking'  (after)
```

### 2. Scope — the trailing verb "walk" blocked LOCAL-836's single-anchor widening
Even once classification is fixed, the location string "Ben Thanh Market **walk**"
kept an orphan verb that neither the LOCAL-46 transport-strip (`walking` but not
`walk`) nor LOCAL-836's anchor detector (`_leading_anchor_list` keys on the "tour"
keyword) handled. So the venue resolver looked up "Ben Thanh Market walk" (no
Wikidata match), the single named anchor was never recognised, the market POINT
stayed the D558 containment scope, and every real nearby District-1 landmark was
rejected as "near but not inside the market" — the tour still shipped 2/4.

## The fix — `generate_tour_text.py`

**Precedence (cause 1).**
- **`_request_has_walking_signal(location, tour_type)`** (new) — True when the
  request carries an explicit walking/driving/biking `tour_type`
  (`_EXPLICIT_WALKING_TOUR_TYPES`) OR a walking word (`_WALKING_WORD_RE`:
  walk/stroll/promenade/wander/ramble/saunter/on-foot, with equivalents in
  **vi/fr/de/es/ru**). False for a business-near-landmark request that names no
  walking signal ("coffee near Ben Thanh Market", "spas near X", "kite schools"),
  so LOCAL-805 still owns those.
- **`_classify_tour_category`** — a WALKING PRECEDENCE guard runs right after the
  facility/worship/food scans and **before** the LOCAL-805/791 business-subject
  branches: if `_request_has_walking_signal(...)`, return `'walking'`. It sits
  below facility/worship/food so LOCAL-480/485 and the restaurant scan are
  unaffected.
- **Touchpoint 1 (both the intent-ok and fallback branches)** — the
  `_effective_tour_type` suppression now EXEMPTS an explicit walking signal, so
  `_pre_category=='restaurant'` (the market subject) no longer blanks the walking
  type before the classifier sees it.

**Scope widening (cause 2).**
- **`_TRANSPORT_STRIP_WORDS`** — added `walk`, `stroll`, `wander`, `promenade`,
  `ramble`, `saunter` (joining the existing `walking`/`hiking`/`running`). Strips
  the orphan verb from the AREA-RESOLUTION string only; intent still sees the
  original request (D536).
- **`_leading_anchor_list`** — a new `_TRAILING_WALK_VERB_RE` fallback recognises a
  trailing standalone walking verb as the head/tail separator when there is no
  "tour" keyword, so "Ben Thanh Market walk, Ho Chi Minh City" → anchor
  "Ben Thanh Market", city "Ho Chi Minh City". A LEADING verb ("walk near Ben
  Thanh Market") and the city tail are left untouched. This restores LOCAL-836's
  single-anchor walkable-area widening for the "walk" form.

## Trace (Do item 2) — all deterministic, offline
```
"Ben Thanh Market walk, HCMC"            tt=""         → walking    (walking word beats 805)
"Ben Thanh Market walking tour, HCMC"    tt=""         → walking    (unchanged — explicit phrase)
"walk around Dong Xuan Market, Hanoi"    tt=""         → walking    (leading walk verb)
"coffee near Ben Thanh Market"           tt=""         → restaurant (no walking signal — stays places)
"Ben Thanh Market"                       tt="walking"  → walking    (explicit app tour_type beats 805)
```

## Tests
- **`tests/test_local838_walk_beats_805.py`** (new, 46 cases): the five ticket
  strings; explicit tour_type beats 805; the walking word in six languages
  (en/vi/fr/de/es/ru); business requests still places; the anchor-list trailing-
  verb fallback and single-anchor scope widening for the "walk" form; the
  transport-strip of the orphan verb; and a source-level guard that the
  Touchpoint-1 suppression exempts the walking signal in both branches.
- **Regressions all green:** 805, 805B, 830, 835, 836, 791/791b/791c/791e, 46
  (transport scope), 474 (empty tour_type), 480 (`TestFacilityClassification`),
  485 (venue class), 834. **319 passed.**
  (The 6 `test_local480::TestWiring` failures are PRE-EXISTING on the clean base —
  they `inspect.getsource` the thin `generate_tour_text` wrapper for strings that
  live in `_generate_tour_text_impl`; unchanged by this task, verified by stash.)

## Live — BUDGET ENFORCED
`TASK_BUDGET_ID=LOCAL-838 TASK_BUDGET_USD=0.40`, LOCAL-820 meter contract, OWN
disposable container (`-p local838`, throwaway `local838-postgres` initialised
from `local778-initdb/`, never the shared `audioura-*` containers, never the live
DB), cheap arm (`NARRATION_MODEL=gpt-4.1-mini`, `RESEARCH_BACKEND=serper`), cache
off, pool off. Runners: `run_local838_container.py`, `run_local838_live.sh`.

One tour: **"Ben Thanh Market walk, Ho Chi Minh City"** (4) with tour_type=walking.

**PASS:**
```
classified category = 'walking'
STOP 1: Saigon Square
STOP 2: Ben Thanh Market
STOP 3: The Old Post Office
STOP 4: Market 2000
delivered 4/4 stops   shortfall-apology present: False
TOTAL $0.1025   (openai $0.0935 + serper $0.0090)   ≤ $0.30
```
4/4 real nearby District-1 landmarks, walking category, well under the per-tour
$0.30 PASS threshold and the $0.40 whole-task cap (append-only meter ledger).
One additive `is_test` row stored in the isolated DB; no DELETE; live DB untouched.

## Process
Committed only the intended files to `LOCAL-838-walk-beats-805` (no `git add -A`).
Did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
TRAVEL_PROJECTS.md.
