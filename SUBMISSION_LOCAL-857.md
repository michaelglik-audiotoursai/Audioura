# SUBMISSION — LOCAL-857: "Ben Thanh Market and Saigon Opera House walk" refused because the word "house" turned a city walk into a museum tour

**Base:** subscribed @ `4ed2e3f4` — `git merge-base --is-ancestor 4ed2e3f4 HEAD` exits 0 (verified before the commit).
**Branch:** `LOCAL-857-classify-house-walk`

## The defect (GCloud_Storied_1, 2026-11-03, gen 00029-plj, request 331, job c6afda0b)

Request **"Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"** was
**refused**. Two defects chained:

1. **CLASSIFY-FIX, a bag-of-words scan.** After the classifier correctly returned
   `walking`, the CLASSIFY-FIX override (`generate_tour_text.py`) intersected the
   location's words with `_VENUE_WORDS_FOR_CLASSIFY` and promoted on the first
   hit — here **`house`** (Saigon Opera **HOUSE**):
   ```
   [CLASSIFY-FIX] Location contains venue word 'house' — overriding walking → museum
   ```
   A `.pop()` on a set took whatever word came out first; it never looked at the
   token sequence ("Opera House" is a building, not a collection) and never looked
   at the request's "walk" / "X and Y" multi-place intent.
2. **BLOCKER4b then refused.** Once on the museum path, the address-scatter guard
   saw the five real District-1 landmarks spread across distinct addresses and
   rejected them as a "city-wide museum tour, not interior rooms" — before any
   verification. Two of the best-known places in Ho Chi Minh City, refused.

## The fix — `generate_tour_text.py`

### 1. CLASSIFY-FIX matches on token sequences, not a bag of words

Three module-level helpers (unit-tested directly), and the CLASSIFY-FIX block now
gates every promotion through them instead of a blind `.pop()`:

- **`_classify_fix_requests_multi_place_walk(location, tour_type)`** — True when
  the request asks to move through several places: an explicit walk/stroll/
  ride/drive/"on foot" signal (via the existing `_request_has_walking_signal`, so
  en/vi/fr/de/es/ru all count), a ride/drive/cruise/sail verb, a "tour of …"
  phrase, a comma list of place-like segments, or an "X **and** Y" conjunction of
  two capitalised place names. A single-venue name with its own internal "and"/
  commas ("House of the Seven Gables") is **not** a list.
- **`_classify_fix_venue_word_is_compound(location, matched_word)`** — True when
  the matched venue word belongs to a **compound building name that is not a
  collection**, matched as a TOKEN SEQUENCE: `<modifier> House` for
  modifier ∈ {opera, custom(s), state, coffee, guest, public, town, court,
  chapter, …} (`_COMPOUND_HOUSE_MODIFIERS`), the `court-house` one-token form, or
  a bare "Market". A **leading** "house" ("House of the Seven Gables",
  "Gardner House Museum") is a single-venue house museum and is **not** a compound.
- **`_classify_fix_should_promote_to_museum(location, tour_type, matched_word)`** —
  returns False (keep walking) when either of the above holds, else True.

The CLASSIFY-FIX block keeps only the matched words that *justify* promotion; if
none do, it logs and stays walking:
```
[LOCAL-857] CLASSIFY-FIX held: venue word(s) ['house'] belong to a multi-place
walk or a compound building name (not a collection) — staying on the walking path.
```
`_VENUE_WORDS_FOR_CLASSIFY` is unchanged, so every existing museum case is reached
exactly as before — the guard only *subtracts* wrong promotions.

### 2. Safety net — BLOCKER4b falls back to walking instead of refusing

The pre-override category is snapshotted (`_category_before_classify_fix =
tour_category`). At BLOCKER4b, when the built museum tour scatters across **≥3**
distinct real addresses, the request was **originally classified walking**, and
the scope is not a single BUILDING/CORRIDOR, the run flips to the walking path and
logs — instead of refusing:
```
[LOCAL-857] museum→walking fallback (address scatter, N addresses)
```
The museum and walking branches converge at PHASE 4.5, so the already-discovered,
real-addressed landmarks carry straight through to delivery. A genuine museum
request that scatters (`_category_before_classify_fix == 'museum'`, e.g. Palais
Lascaris) is unaffected and still refuses — the fallback is gated on the request
having been walking to begin with.

## Trace (Do item 3) — deterministic, offline (mirror calls the real helpers)
```
"Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City" → walking  (walk signal + "X and Y" list; 'house' held)
"Sydney Opera House"                                             → walking  (compound "Opera House"; never refused)
"Palais Lascaris, Nice"                                          → museum   (unchanged)
"Isabella Stewart Gardner Museum"                                → museum   (unchanged)
"Frick Collection"                                               → museum   (unchanged)
"Hearst Castle"                                                  → museum   (unchanged)
"House of the Seven Gables"                                      → museum   (single-venue house museum; 'house' leads, promotes)
```

## Tests
- **`test_local857_classify_house_walk.py`** (new, 24 cases): the exact field
  string → walking; "Sydney Opera House" never promoted to museum; a batch of
  compound `<X> House`/`Market` names never museum; the five ticket museum cases
  unchanged incl. the single-venue house museum; the multi-place-walk detector
  (walk/stroll/tour-of/ride-drive/"X and Y"); the BLOCKER4b fallback decision
  truth table; source assertions that the CLASSIFY-FIX block consults the guard,
  the blind `.pop()` is gone, the venue-word set and snapshot ordering hold, and
  the fallback log is wired; and a break-the-guard test that regresses the field
  request to `museum` when the guard is neutralised (proves it is load-bearing).
- **Regressions all green:** 485 (venue class), 805 (near-landmark), 838 (walk
  beats 805), 791 (Vietnam round 2), 474 (empty tour_type), 480
  (`TestFacilityClassification`). **181 passed** across these files + the new suite.
  (The 6 `test_local480::TestWiring` failures are **PRE-EXISTING on the clean
  base** — they `inspect.getsource` the thin `generate_tour_text` wrapper for
  strings that live in `_generate_tour_text_impl`; unchanged by this task,
  confirmed by `git stash`.)

## Live — BUDGET ENFORCED
`TASK_BUDGET_ID=LOCAL-857 TASK_BUDGET_USD=0.40`, LOCAL-820/827 meter contract
(`meter_container_env.docker_meter_args` env, canonical `paid_api_calls.jsonl`,
shared task-budget ledger), OWN disposable container (`-p local857`, throwaway
`local857-postgres` from `local778-initdb/`, **never** the shared `audioura-*`
containers, **never** the live DB), cheap arm (`NARRATION_MODEL=gpt-4.1-mini`,
`STORY_PASS_MODEL=gpt-4.1`, `RESEARCH_BACKEND=serper`), cache off, pool off.
Runners: `run_local857_container.py`, `run_local857_live.sh`.

**Tour 1 — the exact request (3 stops), tour_type=walking — PASS:**
```
[LOCAL-857] CLASSIFY-FIX held: venue word(s) ['house'] belong to a multi-place
            walk or a compound building name (not a collection) — staying on the walking path.
Detected tour category: WALKING          (NOT refused)
Stop 1: Ben Thanh Market      — Chợ Bến Thành, Quận 1, HCMC   — 10.7761, 106.6951
Stop 2: Saigon Opera House    — 7 Lam Son Square, District 1  — 10.7763, 106.6955
delivered 2/3 (honest shortfall)   GEO-CHECK: all within walking distance
```
Both headline landmarks delivered as stops **with correct pins** — the PASS
criterion. The 3rd candidate (War Remnants Museum) was dropped by the existence
gate as outside the named walk area (`[LOCAL-790] no evidence … none in area`),
so the tour honestly reports 2 stops rather than padding — correct behaviour, not
the refusal the ticket describes.

**Tour 2 — "Palais Lascaris, Nice" (3 stops), museum regression — holds:**
```
[S15] Forced tour_category=museum from venue_name='Palais Lascaris'
Detected tour category: MUSEUM
[venue_resolver] Resolved: 'Palais Lascaris' → Q34653010   Coords: 43.6977, 7.2773
delivered 1/3 (honest shortfall)   still museum, still delivered
```
Still museum, still delivered (the 1/3 is a pre-existing cheap-arm verification
limit for this venue, not a regression — my change does not touch the single-venue
museum path).

**Cost (append-only whole-task ledger, combined all providers):**
```
run 1  $0.1431      run 2  $0.1314      total  $0.2745   ≤ $0.40 cap
```
Two additive `is_test` rows stored in the isolated DB; no DELETE; live DB
untouched; all 14 shared `audioura-*` containers left running and untouched.

## Process
Committed only the intended files to `LOCAL-857-classify-house-walk`
(`generate_tour_text.py`, `test_local857_classify_house_walk.py`,
`run_local857_container.py`, `run_local857_live.sh`, this submission) — **no
`git add -A`** (live-run artifacts and incidental debug files were left
uncommitted). Did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md. No `DELETE`.
