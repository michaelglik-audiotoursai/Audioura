# SUBMISSION — LOCAL-522: Order and connect the stops the user chose

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-522-user-stops-route`
**Base:** `storied` (`e1341e6`)

## Why

A user lists stops in the order they *remembered* them, not the order they
*walk* them. Per **D581**, Directions and Orientation are properties of a
SEQUENCE, so they must be computed for the user's own set — in the order that
set is actually travelled — and never inherited from another tour.

The existing generator (`generate_tour_text.py`) already had the pieces scattered
through an 1.1 MB module that only runs against a live OpenAI key:
`_compute_route_order` (geographic nearest-neighbour + 2-opt, D559),
`_explicit_stop_names` protection, and deterministic transition templates. What
was missing as a *testable unit* was the whole contract in one place — and, in
particular, honouring a **user-forced order** and ordering a **building** tour by
the venue's own flow rather than by straight-line distance.

## What I built

### `stop_route_sequencer.py` — a pure, offline, deterministic module

Public entry point:

```python
sequence_stops(poi_list, tour_category="walking", forced_order=None, venue_name="")
```

It returns a **new** list of **new** stop dicts (the caller's input is never
mutated) in walked order. Each stop gains:

| field        | meaning                                                        |
|--------------|----------------------------------------------------------------|
| `position`   | 1-based index in the walked order                              |
| `directions` | hand-off that **names the next stop** (absent on the last stop) |
| `closing`    | clean closing line (present **only** on the last stop)          |

Ordering strategy:

- **Walking / outdoor** (`walking`, `restaurant`, …) → **geographic** order via
  nearest-neighbour + 2-opt tried from *every* start (deterministic; ties break
  on the lower start index). This mirrors the proven `_compute_route_order`
  (LOCAL-7 / D559 "try every start" zigzag fix), lifted into a unit-testable
  module. Stops with no coordinates keep their relative place; none are dropped.
- **Building / venue** (`museum`, `building`, `venue`) → the **venue's own flow**:
  a stable sort on `(floor, flow_index)`. Inside a building, straight-line metres
  are meaningless — you move through rooms in the order the building lays them
  out. With no flow hints, the user's order stands (correct no-op).
- **Forced order** → honoured **verbatim**, with no re-optimisation. Stops the
  user did not name are appended in their original relative order, so a forced
  order can never drop a stop.

Seams (`directions` / `closing`) always draw their target from the **ordered
result list itself**, so a seam can never point at a stop that is not in the
list — acceptance criterion 4 holds by construction, not by a downstream check.
Seams are deterministic templates; `generate_tour_text.py` may still replace the
prose with richer LLM directions downstream, but the SEQUENCE and the hand-off
TARGET computed here are the contract.

### `tests/test_local522_user_stops_route.py` — one class per acceptance criterion

- **AC1** `AC1_JumbledComesBackWalkable` — a scrambled 4-stop line comes back
  shorter, resolves to the optimal line in either direction, is deterministic
  regardless of input order, loses no stop, **and** a building tour orders by
  venue flow rather than geography.
- **AC2** `AC2_DirectionsNameNextAndLastCloses` — every non-last stop's
  `directions` names its actual successor; the last stop has a `closing` and no
  `directions`; exactly one stop closes; positions run 1..N.
- **AC3** `AC3_ForcedOrderHonouredVerbatim` — a forced order is used exactly,
  overrides geographic optimisation, is case/space-insensitive, appends (never
  drops) unnamed stops, and the seams follow the forced order.
- **AC4** `AC4_NoSeamPointsOutsideTheList` — every `directions` target is a stop
  in the list; a removed stop is never referenced; forced-order seams stay
  inside the list; a single-stop tour has a closing and no dangling directions.
- Plus `InputIsNeverMutated` — the caller's dicts are left untouched.

## Verification

```
$ python3 -m pytest tests/test_local522_user_stops_route.py -v
...
19 passed in 0.12s
```

No regression in the existing route-ordering tests:

```
$ python3 -m pytest tests/test_d558_replenish_loop.py -q
18 passed, 1 warning in 0.73s
```

Module imports standalone (no network, no key required):

```
$ python3 -c "import stop_route_sequencer as s; print(bool(s.sequence_stops))"
True
```

## Acceptance criteria → evidence

| # | Criterion | Where proven |
|---|-----------|--------------|
| 1 | A jumbled list comes back in a walkable order | `AC1_JumbledComesBackWalkable` (5 tests) |
| 2 | Every stop's Directions names the NEXT stop; the last closes cleanly | `AC2_DirectionsNameNextAndLastCloses` (4 tests) |
| 3 | The user can force their own order, honoured verbatim | `AC3_ForcedOrderHonouredVerbatim` (5 tests) |
| 4 | No stop points at a stop that is not in the list | `AC4_NoSeamPointsOutsideTheList` (4 tests) |

## Files

- `stop_route_sequencer.py` (new) — the pure sequencing + seam module.
- `tests/test_local522_user_stops_route.py` (new) — 19 tests, all green.
- `SUBMISSION_LOCAL-522.md` (this file).

## Notes / scope

- The module is self-contained and side-effect-free by design; that is what
  makes the acceptance criteria verifiable without an API key or live services.
- I did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`
  or `.continuous_dev/STATUS.md`.
- Wiring `sequence_stops` into `generate_tour_text.py` to replace the scattered
  in-line ordering is a natural follow-up, but was kept out of this change to
  keep the delivered unit small, pure, and fully tested against the four
  acceptance criteria.
