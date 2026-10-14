# SUBMISSION — LOCAL-689: Personal "Match %" for listeners (free)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-689-match-percent` (from `subscribed` = 62f0220b)
**Base verified:** `git merge-base --is-ancestor 62f0220b HEAD` → exit 0.

> Michael, 2026-10-14: *"Match 82% — strong on history, which you like; light on
> people stories."* Free for listeners. Deterministic, no model call.

---

## What shipped

1. **Server** — `GET /tour/<id>/match?user_id=` returns
   `{match_percent, reasons:[..two phrases..]}`; a listener with fewer than
   5 swipes gets `{match_percent: null, reason: "Swipe a few stops to get
   matches"}`. `match_percent` + reasons are also attached to every
   `/tours-near` and `/search-tours` item when `user_id` is passed, via **one
   batched computation (no N+1)**, and both endpoints gained `?sort=match`.
2. **App** — a green **"Match 82%"** chip plus the two reason phrases in both the
   tour dialog and the List view, and a third List-view sort **"Best match
   first"**.
3. **Tests** — the formula against known vectors, the <5-swipe case, and a
   translation that uses the original's metrics. 13 tests, all green.

---

## The formula (deterministic, no model call)

Lives in `map_delivery/personal_match.py` as a **pure function** — no I/O, no
randomness — so it is trivially testable and identical every run.

Three inputs, all already in the database:

| Input | Source | Range |
|---|---|---|
| Listener taste `pref_k` | `user_class_prefs.pref_details / pref_historic / pref_social` (swipe engine, LOCAL-101) | `[0,1]`, neutral 0.5 |
| Tour story character `c_k` | mean of `stop_metrics.class_details / class_historic / class_social` over the tour's stops, renormalised so `Σ c_k = 1` | `[0,1]` |
| Tour quality | `audio_tours.editor_score` (D655/LOCAL-685) | `5.0–8.0` |

for the three story classes `k ∈ {details, historic, social}`.

```
taste weight    w_k   = pref_k − 0.5                      ∈ [−0.5, +0.5]
alignment       A     = Σ c_k · w_k                        ∈ [−0.5, +0.5]
                align = clamp(0.5 + A, 0, 1)               ∈ [0, 1]
quality         q     = clamp((editor_score − 5)/3, 0, 1)  ∈ [0, 1]   (missing → 7.5)

MATCH % = round( 100 · (0.75 · align + 0.25 · q) )         ∈ [0, 100]
```

- **Taste dominates** (`W_TASTE = 0.75`) because this is a *personal* match;
  quality only nudges (`W_QUALITY = 0.25`).
- A **perfectly neutral** listener (all `pref = 0.5`) gets `align = 0.5` for every
  tour — personalisation is off, which is the correct cold-start behaviour.
- A tour heavy in a **liked** class scores above 0.5 alignment; heavy in a
  **disliked** class, below.

### Reasons (two short phrases, deterministic)

- **Reason 1** describes what the tour is strongest on — its *dominant* class
  (largest `c_k`). If the listener likes it → *"strong on history, which you
  like"*; otherwise it is stated plainly → *"heavy on history, which you swipe
  past"*. "Strong on X" is therefore only ever said about a class the tour
  genuinely emphasises.
- **Reason 2** describes what the listener is missing — among the classes they
  like (`pref ≥ 0.5`), the one the tour is lightest on → *"light on people
  stories"* (only when the share is below an even 1/3 split).
- Ties broken by the fixed display order `details < history < social`, so the
  output is fully deterministic.

### Cold start / <5 swipes

`personal_match.MIN_SWIPES = 5`. Below it (or with no `user_class_prefs` row),
`compute_match()` returns `{match_percent: None, reasons: []}` and the service
surfaces `{match_percent: null, reason: "Swipe a few stops to get matches"}`.

### Translations use the ORIGINAL's metrics and score

The stops and the evaluation both live on the original tour. The service
resolves a translation to its original (`_resolve_original_id`, exactly like the
rating prior `_prior_for`) for **both** the `stop_metrics` aggregate **and** the
`editor_score` — so a translation's Match % equals its original's.

---

## Server implementation — `map_delivery/app.py`

New helpers (after `_prior_for`), all read-only and fail-soft:

- `_user_prefs(cur, user_id)` → `(prefs|None, swipe_count)` — **one** query.
- `_tour_characters(cur, ids)` → `{tour_id: {details,historic,social}}` for many
  tours in **one** `AVG(...) GROUP BY tour_id WHERE tour_id = ANY(%s)` query.
- `_match_block(...)` → the `{match_percent, match_reasons, match_reason}` shape.
- `_attach_match(cur, user_id, tours_list, editor_scores)` → adds that block to
  every list item in place. **Two queries total** regardless of list length
  (prefs once + characters once) — no N+1.
- `_single_tour_match(cur, user_id, tour_id)` → the per-tour endpoint payload,
  resolving a translation to its original.

Routes / list endpoints:

- `GET /tour/<id>/match?user_id=` (new) — public, free; fails **soft** to a
  cold-start shape, never 500.
- `/tours-near` and `/search-tours` — call `_attach_match(...)` and honour
  `?sort=match` (best match first; null-match items sink to the end).

`personal_match.py` lives inside `map_delivery/` because that service deploys as
its own image (`Dockerfile: COPY . .`).

## App implementation — `audio_tour_app/lib/screens/home_screen.dart`

- Sort is now **tri-state** `_sortMode ∈ {nearest, top_rated, match}`, persisted
  under `home_sort_mode`; the legacy `home_top_rated` bool is migrated on first
  load and kept in sync, and a `_topRated` getter / `_setTopRated` setter keep
  the AppBar sort icon and the Search filter-row working unchanged.
- `_filterQueryParams()` attaches `&sort=match` and `&user_id=<device id>`
  (`DeviceService.getUserId`, cached in `_loadAppMode`) so every tour carries a
  personal Match % in all sorts.
- `_visibleTours()` sorts by `match_percent` desc (null last, then nearest) in
  match mode; keeps the server rank order for top_rated; nearest otherwise.
- New `_matchChip` ("Match 82%", green) + `_matchReasonsLine` (two phrases, or
  the cold-start line) render in **both** the tour dialog and each List row.
- The List view's sort chips now offer **Nearest first / Top rated first / Best
  match first**.

---

## Verification

- **Unit/integration tests** — `tests/test_local689_match.py`, **13 passed**
  (`python3 -m pytest tests/test_local689_match.py -q` → `13 passed`). Also runs
  as a plain script. Coverage:
  - Formula known vectors → exact %: history-lover + history tour + 8.0 → **81**;
    neutral listener + fallback score → **58**; social-lover + history tour +
    6.5 → **40**; bounds → **100** and **0**; plus a determinism check. Each
    expected value has its arithmetic worked out in the test docstring.
  - `aggregate_tour_character` mean + even-split-on-empty.
  - **<5-swipe** → `match_percent` null + the exact sentence; threshold
    inclusive at 5; no-prefs-row is cold too.
  - **Translation** (tour 200) scores **identically** to its original (tour
    100) for both metrics and score, including the cold-start case. DB-free via
    a tiny fake cursor, so it is deterministic anywhere.
  - **Batched / no N+1** — `_attach_match` over 3 items issues exactly **one**
    prefs query and **one** `stop_metrics` aggregate, proven by counting
    `execute()` calls.
- **Compile** — `python3 -m py_compile map_delivery/app.py
  map_delivery/personal_match.py` → OK.
- **App analyze** — after `flutter pub get`, `dart analyze
  lib/screens/home_screen.dart` → **0 errors**.

### Not proven (honest status)

- **Not run against the live dev DB / containers.** The design reads only
  existing columns (`user_class_prefs`, `stop_metrics`, `audio_tours.editor_score`)
  with the same translation-resolution and fail-soft patterns the service
  already uses for ratings and the score explanation (LOCAL-670/685/688), and
  every DB access is wrapped to roll back and degrade to a neutral/cold result
  rather than 500. A live read-only smoke test on the dev DB is the natural next
  step but was not performed in this session. Unproven — not claimed proven.

---

## Process

- Own files only; no edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `WORK_QUEUE.md`, or `.continuous_dev/*`.
- Committed per step:
  - `77a9b948` server (formula + endpoint + batched list attach + ?sort=match)
  - `3b702320` tests (13 green)
  - `59407a3f` app (chip + reasons + tri-state sort)
  - this submission doc.
- Pushed to `origin LOCAL-689-match-percent`.
