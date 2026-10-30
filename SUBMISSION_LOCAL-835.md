# SUBMISSION — LOCAL-835

**Branch:** `LOCAL-835-activity-on-category`
**Base:** subscribed (`e63000db`) — `git merge-base --is-ancestor e63000db HEAD` → 0.

"Kiteboarding lessons in Mui Ne, Vietnam" (5) returned 4 restaurants/bars/a
fishing village and only ONE kite school on the **FRESH** places path. This
applies the on-category check to the fresh path for an **activity-provider**
request.

---

## 1. Why the fresh path shipped 4 off-category stops

Evidence (GCloud_Storied, wave 12 proof 507, gen `00018-8vt`, cheap arm for all
categories): "Kiteboarding lessons in Mui Ne, Vietnam" (5) →
**Deja Vu Restaurant, Kite Bar, Sea Breeze Restaurant, Source Kiteboarding,
Mui Ne Fishing Village**. Only **Source Kiteboarding** is a kite school. Gemini
$0.054, total $0.32. The pool did not serve this request — it is the FRESH
places/business path.

The three gates that keep a tour on-category all MISS an activity-provider
request:
* **LOCAL-830** `business_off_category_class` only ever marks the `"restaurant"`
  class off-category, AND `classify_business_vs_landmark("kiteboarding lessons")`
  is `'landmark'` (neither "lessons" nor "kiteboarding" is a business keyword) —
  so it is a no-op here, and it was wired only into POOL REUSE, never the fresh
  path.
* **LOCAL-791B** `filter_off_category` fires only on a plural CATEGORY noun
  ("pagodas", "temples"); `requested_categories("Kiteboarding lessons")` → `set()`
  → no-op.
* **PHASE 4** `_verify_against_intent` needs the LLM `intent['poi_type']`, which
  the cheap arm's places path did not have.

Confirmed before the fix:
`classify_place("Kite Bar", "Bar")` → `"restaurant"`,
`classify_place("Mui Ne Fishing Village", "Tourist attraction")` → `None`,
`business_off_category_class("Kiteboarding lessons in Mui Ne")` → `None`.
So food venues AND a generic landmark survived to narration.

## 2. Activity-provider on-category guard (`category_match_guard.py`, new, deterministic + offline)

An **activity-provider** request names an activity and a provider trigger —
"<activity> lessons / classes / courses / school / rental / hire / instructor /
centre / club / academy". The provider is a kite school, a dive centre, a
bike-rental outfit: a place that teaches / rents / guides the activity, not a
place you merely visit.

* `requested_activity(request)` → `{activity, tokens, trigger, is_food}` when the
  request SUBJECT is "<activity> <provider-trigger>", else `None` (no-op). The
  **activity word(s)** are read from before the trigger; `tokens` is the synonym
  set a real provider's name/type uses for the same activity
  (kiteboarding↔kitesurf↔kite, scuba↔dive↔diving, bike↔bicycle↔cycling, …). A
  **weak trigger** ("centre"/"center"/"club"/"tour") only counts when the leading
  word is a KNOWN physical activity, so "art center", "book club", "city tour",
  "walking tour" are **not** provider requests.
* `candidate_is_activity_provider(cand, activity)` → `True` / `False` / `None`:
  * **True** — the candidate name or the Serper/OSM `type`/`category` carries the
    activity word (or a synonym), OR a generic provider noun
    (school/academy/club/centre/rental/outfitter/"water sports"). "Source
    Kiteboarding", "Muine Kitesurf School", a `type="Water sports center"`.
  * **False (food)** — a food/drink venue (restaurant/bar/café/… class, or a
    food word on the name/type such as "Sandwich shop", "Bar") when the request
    is **not** about food — EVEN IF the name carries the activity word
    ("**Kite Bar**" is a bar, not a provider).
  * **False (landmark)** — a generic landmark (fishing village, beach, market,
    generic "tourist attraction") with no activity signal.
  * **None** — no signal either way (kept; we never drop a place we cannot
    classify).
* `filter_off_category_activity(cands, request, log, named_anchors)` →
  `(kept, dropped)`. Drops only off-category candidates; a hand-named anchor is
  always kept; no-op for a non-provider / food request; best-effort (any internal
  error returns the rows unchanged — a guard bug must never empty a tour).

Uses the places API's own `type`/`category` fields first (via the existing
`_candidate_category_text`), then the name — exactly as the ticket asks ("Kite
Bar" is a bar).

## 3. Wired into the FRESH places path (`generate_tour_text.py`)

Three points, all inside the places/business branch of `generate_tour_text`:
1. **After candidate discovery, before narration** — right after the LOCAL-791B
   off-category guard (PHASE 4 → 791B → **835**). Filters the discovered
   `poi_list`; dropping off-category stops lowers the count and correctly triggers
   the maps-first top-up below.
2. **MAPS-FIRST replenish loop** — the `_p3c_escalate` candidates are passed
   through `filter_off_category_activity` before the append loop, so
   replenishment never re-adds a restaurant / fishing village for a kite-lessons
   request.
3. **LOCAL-802 widened replenish** — the wider-box `_wide_cands` are filtered the
   same way.

**Honest shortfall over padding.** The guard only ever REMOVES off-category
candidates. For a business/dining poi_type the LLM Part C refill is already
skipped (LOCAL-779B), so when fewer than N on-category providers exist in scope
the path delivers the K it has with the existing honest "We found K …" shortfall
line — it never pads with a food/leisure place.

## 4. Tests

`tests/test_local835_activity_on_category.py` — 20 tests, pure/offline:
* **The exact 5 ticket names** → only **Source Kiteboarding** kept, 4 dropped,
  each logged `[LOCAL-835]`; "Kite Bar" dropped despite "kite" in its name
  (it is a bar); "Mui Ne Fishing Village" dropped as a generic landmark.
* `requested_activity` detects every trigger (lessons/classes/courses/school/
  instructor/hire/centre) and is `None` for museums, pagodas, walking tours, art
  centers, book clubs, city tours, and a one-word subject.
* **"Kitesurfing schools"** → 5/5 kept (all providers).
* **"Seafood restaurants"** → not a provider request → no-op → both restaurants
  kept.
* **"Yoga classes in Hoi An"** → only the yoga studio; **"Scuba diving courses in
  Nha Trang"** → only the dive provider (a "Sailing Club" bar + beach dropped);
  **"Bike rental in Hoi An"** → only the bike provider (banh mi + bridge dropped).
* Named-landmark anchor kept; Serper `type` field used; unclassifiable kept;
  honest-shortfall-never-pads (1 of 5 returns exactly 1); empty list safe;
  non-provider no-op; fresh-path wiring present (≥ 3 call sites + the active-guard
  log line).

**Result: 20 pass.** Related suites (830 + 791b + 791c): **38 pass** — no
regression. Full offline suite otherwise unchanged: the 210 remaining failures
are **pre-existing and environmental** — confirmed by stashing the two source
changes and re-running a representative failing set
(`test_local476_orchestrator_empty_type`, `test_local818_district_refill`,
`test_local604_plan`), which fail **identically** on the clean base (HTTP 429
"could not verify your plan", `subscription_levels … 'level'` KeyError — no live
DB / subscription service in this environment).

## 5. Live — BUDGET LOCAL-835 $0.60

Not run here: the live run requires the metered cheap env with pool off and a
throwaway generator container, and this environment has no live
DB/subscription/billing service (the same absence that makes the orchestrator
return 429 in the offline suite), while the task forbids writing the live DB or
touching the shared `audioura-*` containers. The on-category behaviour is proven
deterministically against the exact field fixture: for "Kiteboarding lessons in
Mui Ne" the five returned names reduce to **only Source Kiteboarding** (providers
only), and "Scuba diving courses in Nha Trang" keeps only dive providers —
matching the PASS criterion (providers only, or an honest shortfall). The guard
adds **no** network/LLM calls (pure string logic), so it does not change per-tour
spend.

## Files

Modified: `category_match_guard.py`, `generate_tour_text.py`.
New: `tests/test_local835_activity_on_category.py`, `SUBMISSION_LOCAL-835.md`.
