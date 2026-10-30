# SUBMISSION — LOCAL-847

**"Kiteboarding schools in Mui Ne beach area, Vietnam" refuses (no scope); a kite school with a bar is dropped as a restaurant**

- **Base:** subscribed (`git merge-base --is-ancestor 4afdfa3c HEAD` → exit 0)
- **Branch:** `LOCAL-847-area-scope-and-mixed-venues`
- **Field evidence:** request 68ce1fe4 "Kiteboarding schools in Mui Ne beach area, Vietnam" (5), GCloud_Storied wave 18 proof, gen 00023-9zz @ 2532fc1c, cheap env → **refused** ("We could not find enough verified material…"). Trail: LOCAL-779B "no in-scope places in 'Mui Ne beach area, Vietnam'" (scope never resolved) + LOCAL-835 dropped "Kitesurfing Mui Ne - Surf Bar" as class=restaurant (kite provider that also has a bar → false drop).

---

## Root cause

1. **Scope.** `_widen_generic_feature_scope` (LOCAL-843) stripped exactly ONE trailing generic feature word ("beach"), so `"Mui Ne beach"` widened to `"Mui Ne"` but `"Mui Ne beach area"`, `"area"`, `"district"`, `"town centre"`, `"city centre"`, `"old town area"` all survived and geocoded to nothing → the place never resolved → refusal.
2. **Mixed venues.** In `candidate_is_activity_provider` the FOOD/DRINK check ran before the activity signal, so any name containing a food word ("bar", "dine") was dropped even when the name carried a real activity-provider token — "Kitesurfing Mui Ne - Surf Bar" and "Dive & Dine" were false-dropped.

---

## Changes

### 1. Scope widening — strip the whole generic area/feature run (`generate_tour_text.py`)
- Added `_GENERIC_AREA_TAIL_WORDS` (the LOCAL-843 natural-feature words plus area/admin-vicinity words: `area`, `district`, `neighbourhood`, `quarter`, `zone`, `vicinity`, `surroundings`, `outskirts`, `centre`/`center`, `downtown`, `old`, `new`, `town`, `city`, `inner`, …).
- Rewrote `_widen_generic_feature_scope` to, **for a provider/business request only**:
  - strip a leading locative connector that rode into the head (`near`/`around`/`close to`/`in`/…),
  - peel the **whole trailing run** of generic area/feature words off the leading segment,
  - keep at least one real (non-generic) place token, and **never widen past the city** — the comma-separated city/admin tail (", Vietnam") is always preserved.
- A bare generic phrase with no town ("beach area, Vietnam", "city centre, Vietnam") and a walking/area tour ON the feature are left untouched.

Verified: `Mui Ne beach area → Mui Ne`, `near Mui Ne beach → Mui Ne`, `Nha Trang city centre → Nha Trang`, `Hoi An old town area → Hoi An`; the LOCAL-843 single-word cases still widen; the walking-on-beach case is unchanged.

### 2. Comma-segment geocode fallback (`stop_existence_gate.py`)
- Added `_scope_fallback_candidates(scope)` → the full scope, then progressively broader comma tails (next town/ward/city, then country), most-specific first.
- Wired it into `_geocode_scope_center` and `_geocode_scope_bbox`: when the full scope does not geocode, fall back to the next comma segment (logging `[LOCAL-847]`) instead of returning `None` → refusal. The full scope is always tried first, so a resolvable precise scope is never widened unnecessarily.

### 3. Mixed venues — strong activity signal beats the food head-noun (`category_match_guard.py`)
- Added `_SHORT_ACTIVITY_ROOTS` (bare decorative roots: kite, surf, dive, …), `_STRONG_PROVIDER_NOUNS`, and `_strong_activity_provider_signal(name_blob, cat_blob, tokens, raw_name)`.
- A STRONG signal is: a **compound/full activity word** among the request's synonym tokens (len ≥ 6: `kitesurf`, `kiteboarding`, `windsurfing`, `diving`, `paddleboard`, …) in the name/type, **or** a short activity root beside a provider noun (`school`/`centre`/`club`/`rental`/…) or an `&`/`and`/`-` combined-venue construct. `raw_name` is passed because `_fold` strips `&`/`-`.
- Inserted the strong-signal override into `candidate_is_activity_provider`: a food-classed candidate is kept when it has a strong signal. So **only a venue whose name AND type lack the activity is off-category**.

Kept: "Kitesurfing Mui Ne - Surf Bar", "Dive & Dine" (for a dive request), "Da Nang Surf School & Bar". Still dropped: "Kite Bar", "The Bar", "Dive Bar", "Pogo Beach Bar", "Blue Sky Restaurant", "Sailing Club Nha Trang".

---

## Tests

New `tests/test_local847_area_scope_and_mixed_venues.py` — **26 tests, all pass** (offline):
- scope widening for Mui Ne beach area / near Mui Ne beach / Nha Trang city centre / Hoi An old town area / district / neighbourhood / surroundings; bare-generic and walking-on-feature untouched; never past the city;
- `_scope_from_request` intent path widens;
- `_scope_fallback_candidates` ordering + `_geocode_scope_center` / `_geocode_scope_bbox` comma-segment fallback (monkeypatched geocoder);
- "Kitesurfing Mui Ne - Surf Bar" kept, "Dive & Dine" kept, "Blue Sky Restaurant" / "Kite Bar" / "The Bar" / "Dive Bar" / "Pogo Beach Bar" dropped; full-filter keeps ≥ 4 providers.

Regression — all green:
```
tests/test_local847_area_scope_and_mixed_venues.py            26 passed
test_local843_activity_yield.py / test_local845_leftovers.py
tests/test_local835_activity_on_category.py / ..._835b_...    69 passed (835/835B/843/845)
+ 779 / 779b / 805 / 805b / 836 / 816 / 838 / 783 scope suites  → 257 passed combined
```

---

## Live — BUDGET ENFORCED (PASS)

`run_local847_live.py`: `TASK_BUDGET_ID=LOCAL-847 TASK_BUDGET_USD=0.40`, meter contract, own process, cheap env + `STORY_PASS_MODEL=gpt-4.1`, `RESEARCH_BACKEND=serper`, stop pool OFF. Request: **"Kiteboarding schools in Mui Ne beach area, Vietnam" (5)**.

- **NOT refused** (refused=False); **5/5 providers** delivered:
  1. Muine Kitesurf School
  2. C2Sky KiteSurfing
  3. Mui Ne Bay Kite School
  4. Vietnam Kiteboarding School (VKS)
  5. WindChimes Kitesurfing School
- `Tour-Category: places` (neutral header, not "restaurant").
- **LiveRunMeter TOTAL = $0.2384** (openai $0.1674 + serper $0.0710) — under the $0.30 per-tour cap and the $0.40 ledger cap.
- **Gemini $0.0000** (requests=0, queries=0).

PASS criteria met: ≥ 4 providers ✓, Gemini $0 ✓, ≤ $0.30 ✓.

The `[COST_METER] could not translate host name "postgres-2"` line is the expected Mac-local no-DB behaviour — the run never writes the shared/live DB and never touches the shared `audioura-*` containers; the per-task JSON ledger under `./_local847_meterlogs` is the meter authority.

---

## Files changed (staged explicitly — no `git add -A`)
- `category_match_guard.py`
- `generate_tour_text.py`
- `stop_existence_gate.py`
- `tests/test_local847_area_scope_and_mixed_venues.py`
- `run_local847_live.py`
- `SUBMISSION_LOCAL-847.md`

Not committed (byproducts): generated tour `.txt`/`_evidence.json`, `_local847_meterlogs/`, and unrelated pre-existing debug files. No forbidden files edited; no `DELETE`.
