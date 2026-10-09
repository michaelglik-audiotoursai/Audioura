# SUBMISSION — LOCAL-650

**Walking tours: the theme must never be a stop; directions must follow the route.**

Branch: `LOCAL-650-walking-route` (from `subscribed` @ `2e420fcf`).
Base check: `git merge-base --is-ancestor 2e420fcf HEAD` → exit 0.
Walking/outdoor path only. The museum selection and assembly path is unchanged —
proven by the museum suites plus a live museum canary.

---

## 1. The evidence (tour 557, request "Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA", 5 stops, walking)

Read read-only from the dev DB (`audio_tours.id=557`):

1. **Stop 5 = "Massachusetts politics and current affairs"**, no Address — the
   request's THEME phrase had become a point of interest.
2. **Stop 4's Directions led backwards.** The Old State House stop said
   "… head north on Washington Street … until you reach the Massachusetts State
   House …" — that is Stop 1, not the next stop. The route order was correct
   (`_compute_route_order`, nearest-neighbour + 2-opt); the per-stop Directions
   PROSE named the wrong landmark.
3. The politics stop discussed scandals from 1996–2011 and a 1904 anecdote;
   whether "current affairs" was honoured depended on recency.

These are present on the Oct-6 baseline too, so they are not regressions.

---

## 2. The fixes

All three are **deterministic, pure, offline, idempotent** guards wired into the
single every-path delivery chokepoint (`_apply_delivery_hours_guard` in
`generate_tour_text.py`), the same place the existing `directions_guarantee` and
`tour_conclusion` guards run — so they fix the delivered text on **every** path
(fresh, pool, cache, by-reference, overview). Each is a **no-op on museum tours**
(`Tour-Category: museum`), so the museum path cannot change. Fix 1 is additionally
enforced at selection time (PHASE 3A), so the theme phrase never becomes a stop in
the first place.

### Fix 1 — a walking stop must be a real place, never the request theme
`theme_stop_guard.py`
- `extract_request_theme(text)` recovers the theme from the tour's own title line
  ("… dedicated to **Massachusetts politics and current affairs**").
- `is_theme_phrase_stop(name, theme)` / `topic_like_name(name)` — a stop whose
  name is the theme phrase (or a subset of it), or any topic-like name with no
  proper-noun place and no place noun (e.g. "politics and current affairs",
  "power and public engagement"), is rejected. Real places ("Old State House",
  "Boston Common", "JFK Library", "University of Massachusetts Boston") are not
  flagged.
- `rename_theme_phrase_stops(text)` renames an offending stop to a real place its
  **own narration** names (557's Stop 5 narrates "University of Massachusetts
  Boston", exactly where its coordinates sit), else a theme-appropriate curated
  place. Coordinates and body are preserved; only the misleading header changes.
- Wiring: PHASE 3A prompt constraint + deterministic candidate rejection
  (`stop_name_is_not_a_place`), and the every-path text guard (chokepoint section
  "3a-ter").

### Fix 2 — directions lead to the NEXT stop, by name, with a distance
`walking_directions_guard.py` + `directions_generator.py`
- `ensure_walking_directions_lead_to_next(text)` — for each non-last walking stop,
  if the `Directions:` line presents a *different* delivered stop as the
  destination (the 557 Stop-4 → Stop-1 defect), it is **replaced** with a
  deterministic hand-off naming the correct next stop; a right/generic line is
  kept. An approximate straight-line distance (haversine from the two stops'
  coordinates) is appended when known. The route order itself is already handled
  by `_compute_route_order` (NN + 2-opt).
- `directions_generator._directions_name_destination` + a TARGET guard in
  `generate_walking_directions`: if the LLM prose never names the next stop, it is
  rejected (returns "") so the deterministic "Continue to {next}." fallback — which
  names the correct stop — is used.
- Wiring: every-path text guard (chokepoint section "3a-quater"), walking only,
  before the directions guarantee.

### Fix 3 — current-affairs honesty
`current_affairs_coverage.py`
- `request_wants_current_affairs(text)`, `has_recent_item(text, window=5)`,
  `most_recent_year(text)`.
- `ensure_current_affairs_coverage(text)` — when the request asked for current
  affairs and NO stop carries a recent (≤ 5 years) grounded year, append ONE
  honest note before Sources ("… we found no verified developments from the past
  five years to include …"). It **never invents** a recent fact. A no-op when a
  recent item is already present.
- Wiring: every-path text guard (chokepoint section "5"), after the conclusion
  rebuild so the note lands at the true end of the spoken text.

### Files
| File | Change |
|---|---|
| `theme_stop_guard.py` | **new** — fix 1 detectors + rename guard |
| `walking_directions_guard.py` | **new** — fix 2 target + distance guard |
| `current_affairs_coverage.py` | **new** — fix 3 recency honesty guard |
| `directions_generator.py` | target guard in `generate_walking_directions` |
| `generate_tour_text.py` | 3 delivery-chokepoint wirings + PHASE 3A theme constraint & candidate rejection |
| `test_local650_walking_route.py` | **new** — 25 tests on the real 557 fixtures |
| `run_local650_container.py`, `run_local650_live.sh` | **new** — isolated live harness |

---

## 3. Tests (exit codes pasted)

New suite on the real 557 inputs plus the museum suites:

```
test_local650_walking_route.py        -> exit=0   25 passed
test_local646_walking_regressions.py  -> exit=0   13 passed
test_local638_directions_between_stops.py -> exit=0  12 passed
test_local585_about_museum_stop.py    -> exit=0   24 passed
test_local582_museum_overview.py      -> exit=0   21 passed
tests/test_local522_user_stops_route.py -> exit=0  19 passed
test_local644_pool_structured.py      -> exit=0    5 passed
test_local590_assembly.py             -> exit=0   16 passed
```

`test_local650_walking_route.py` covers, on the verbatim 557 stop blocks:
fix 1 (theme recovered, Stop 5 flagged and renamed to the UMass place its own
narration names, real places not flagged, idempotent, museum no-op); fix 2 (Stop 4
wrong-target detected after the rename and corrected to name the next stop +
distance, headers unchanged, no glued headers, idempotent, the directions-generator
target guard rejects the 557 Stop-4 prose, museum no-op); fix 3 (557 already carries
a 2024 item so no note; an old-years tour gets one honest note; idempotent; museum /
non-current-affairs no-op); and composition of all three.

One idempotency bug was found **by** the new test and fixed:
`walking_directions_guard._DISTANCE_RE` did not recognise the "a minute's walk away"
phrase it emits for very short legs, so a second pass re-appended a distance. Fixed;
557 is now byte-for-byte idempotent.

Not a LOCAL-650 regression: `test_local592_about_in_stop1.py` has one failure
("12 dollars" vs "8 dollars" admission). That file is **unchanged since the base
`2e420fcf`** and imports none of the LOCAL-650 modules — a pre-existing data/fixture
issue.

---

## 4. Live run — own disposable container (cap $1.20)

Built `Dockerfile.generator` from this branch and ran two FRESH tours (tour cache
OFF, stop pool OFF) in a container I own:

```
docker run --rm --name local650-gen -p 5115:5000 --network development_default …
```

Never `docker compose -p audioura`; no `audioura-*` container was renamed, replaced,
or touched (13 still running after the run); the container was removed on exit.
Metered + HARD-CAPPED at **$1.20 combined** by `tests/live_run_meter.py` with a
$0.55 reserve gate before each tour.

### WALKING — `audio_tours.id=571` (5 stops, fresh)

Generation log:
```
[LOCAL-650 fix1] Stop 5: renamed theme/topic stop 'Massachusetts politics and current affairs'
                 -> 'University of Massachusetts Boston' (narration)
[LOCAL-650 fix2] walking directions: corrected 1 wrong-target line(s), added 4 approximate distance(s)
```
Detectors:
```
[FIX1] request theme: 'Massachusetts politics and current affairs'  theme/topic stops: []   -> ok=True
[FIX2] wrong_target=0  missing_directions=0  legs_with_distance=4/4                          -> ok=True
[FIX3] wants_current_affairs=True  has_recent_<=5y=True  most_recent_year=2025  honest_note=False -> ok=True
WALKING RESULT: fix1=True fix2=True fix3=True
```
Stored row 571 — stop headers and directions (each hand-off names the NEXT stop with
a distance; Stop 5 is a real place, not the theme):
```
Stop 1: Massachusetts State House   Directions: … Boston City Hall … roughly 400 meters away.
Stop 2: Boston City Hall            Directions: … reach Faneuil Hall … roughly 350 meters away.
Stop 3: Faneuil Hall                Directions: … Continue to Old State House — roughly 200 meters away.
Stop 4: Old State House             Directions: From here, make your way to University of Massachusetts Boston — roughly 300 meters away.
Stop 5: University of Massachusetts Boston
```

### MUSEUM CANARY — `audio_tours.id=573` (The Courtauld Gallery, 3 stops, fresh)
```
[canary] run-on header: False   missing_directions: 0   LOCAL-650 guards no-op: True
MUSEUM RESULT: run_on=False missing_directions=0 guards_noop=True
```
The museum path is unchanged: every LOCAL-650 guard is a verified no-op; the stop
headers are the works (Manet's A Bar at the Folies-Bergère, Georges Seurat, Christ
and the Woman Taken in Adultery); 0 directions missing; no run-on header.

### Cost (metered, combined, all providers)
```
openai            $0.7495
gemini_grounding  $0.2310  (requests=6, queries=7)
gemini_tokens     $0.0350
serper            $0.0440
preflight         $0.0726
TOTAL             $1.0595   (< $1.20 cap)
```

### Rows (additive is_test only — NO DELETE)
```
audio_tours total:   376 -> 378   (+2)
audio_tours is_test: 312 -> 314   (+2, the two live rows 571 and 573)
```

### Spend from paid_api_calls (by host)
The run's container host was `01f2a436681a` (a fresh host, $0 before):
```
host 01f2a436681a  BEFORE: $0.0000   AFTER: $1.3862
```
The DB figure ($1.3862) includes TTS and other provider rows beyond the
combined-cap meter's scope ($1.0595); both are reported for transparency. No other
host's spend changed from this run.

---

## 5. Process

Committed after each step; `git rev-list --count origin/subscribed..HEAD` ≥ 1 at
every step (final count 6 with this submission). `DECISIONS.md`, `CLAUDE.md`,
`BACKLOG.md`, `WORK_QUEUE.md` and `.continuous_dev/STATUS.md` were not edited.
Pushed to `origin/LOCAL-650-walking-route`.
