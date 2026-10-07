# SUBMISSION — LOCAL-605

**Tours delivered from the stop pool / cache have NULL lat/lng (invisible in
"tours near me", no map pin).**

- **Branch:** `LOCAL-605-pool-tour-coordinates`
- **Base:** `subscribed` @ `21b9eba` (`git merge-base --is-ancestor 21b9eba HEAD` → exit 0)
- **Agent:** Mac Mini Kiro

---

## 1. Root cause

`generate_tour_text(...)` returns a `(text, output_file, (lat, lng))` triple, but
**every non-fresh delivery path returns `(None, None)`** for the coordinate:

| Path | Return site (generate_tour_text.py) | Coords returned |
|------|--------------------------------------|-----------------|
| fresh | normal path parses Stop 1 | real `(lat, lng)` |
| stop-pool reuse (first-tour + pooled) | `return _pool_out["text"], output_file, (None, None)` | `(None, None)` |
| by-reference (LOCAL-597) | `return result["text"], output_file, (None, None)` | `(None, None)` |
| site-first / overview (LOCAL-582) | `return _ov_text, output_file, (None, None)` | `(None, None)` |
| cache hit | `return _cache_hit, output_file, (None, None)` | `(None, None)` |

`stop_pool_orchestrator.maybe_generate_with_pool(...)` returns a dict (`text`,
`reused_stops`, …) with **no coordinates at all**, so the generator hands back
`(None, None)` on reuse.

The generator **service** (`generate_tour_text_service.py`) stores whatever it
received into the job and reports it on `/status`. The orchestrator
(`tour_orchestrator_service.py`) polls that status; its coordinate fallback is
guarded by `if not coordinates or ... len(coordinates) < 2`. A `[None, None]`
list is **truthy, is a list, and has length 2**, so the fallback is **skipped**
and `lat = coordinates[0] = None`, `lng = None` are stored. `tours-near` filters
on `lat IS NOT NULL AND lng IS NOT NULL AND is_test IS NOT TRUE AND
original_tour_id IS NULL` — so the tour never appears near anyone and has no pin.

This matches the LEAD evidence (tours 400 Harvard, 399 McMullen, 398/397 WNDR:
all `lat NULL | lng NULL`).

---

## 2. Fix — real tour-level coordinates on EVERY path, fail-closed

New module **`tour_coordinates.py`** — one resolver, import-light and testable:

- `parse_coordinates_text` — parses a `Coordinates:` value in both delivered
  formats: decimal (`42.3644, -71.0558`) and hemisphere (`10.2231° N, 103.96° E`,
  with S/W negated).
- `parse_stop1_coordinates` — the first `Coordinates:` line in the delivered text
  (Stop 1 leads).
- `coordinates_present` — treats `None`, `(None, None)`, `(0, 0)` (the
  orchestrator's "couldn't resolve" sentinel), `NaN`, and out-of-range values as
  **absent**.
- `resolve_venue_coordinates` — a **contained** venue's own coordinates: the
  resolver's Wikidata **P625** (`venue_resolver.resolve_venue().lat/.lng`), else
  the **D611** venue street address (`stop_pool_orchestrator._resolve_venue_address`)
  geocoded.
- `resolve_tour_coordinates(content, location, coordinates, contained, path)
  → ((lat, lng), source)` — the single entry point: keep real generator coords if
  present (`generator`); for a contained venue prefer the venue's own coordinates
  (`venue`) then Stop 1 (`stop1`); for others prefer Stop 1 then venue; `none`
  when nothing resolves.

**`generate_tour_text_service.py`** calls it at the single completion choke point
(just before the job is marked `completed`), so **all paths** are covered — fresh,
cache, pool, by-reference, overview. Then it **FAILS CLOSED**: if no coordinate
resolves, the job is marked `status="error"` with `error_code=missing_tour_coordinates`
and `coordinate_path=<path>`, the temp file is removed, and the tour is **not
delivered silently**. The resolved pair is logged with its source and path.

**`generate_tour_text.py`** records a module global `_LAST_DELIVERY_PATH`
(`fresh` / `cache` / `pool` / `by_reference` / `overview`) at each return site, so
the fail-closed log and the service name the exact delivering path.

Files changed:
- `tour_coordinates.py` (new)
- `generate_tour_text_service.py` (resolution + fail-closed assertion at completion)
- `generate_tour_text.py` (`_LAST_DELIVERY_PATH` per return site)

---

## 3. Tests per path (stubbed) — lat/lng present in the returned tuple

`test_local605_tour_coordinates.py` (offline; venue resolver monkeypatched):

- `fresh` → generator coords pass through (`source=generator`).
- `cache`, `pool`, `by_reference`, `overview` → generator `(None, None)`, Stop 1
  parsed (`source=stop1`); hemisphere W negated.
- contained venue → prefers the venue's own P625 coords (`source=venue`); falls
  back to Stop 1 when the resolver is empty.
- fail-closed sentinel → no venue hit + no Stop 1 line → `(None, None)` / `none`.
- `(0,0)`, `(None,None)`, out-of-range all count as absent; parsers for both
  coordinate formats.
- wiring: the service resolves BEFORE marking `completed`, fails closed with
  `error_code=missing_tour_coordinates` + `coordinate_path`; the generator records
  `_LAST_DELIVERY_PATH` for each path.

```
$ python3 -m pytest test_local605_tour_coordinates.py -q
17 passed            exit 0
```

---

## 4. Backfill — separate, reversible, dry-run by default (NOT applied)

`backfill_tour_coords.py` lists `audio_tours` rows with NULL `lat`/`lng` whose
`tour_content` has a Stop 1 `Coordinates:` line, and the `(lat, lng)` it WOULD set.

- Default `--dry-run`; writes **only** with explicit `--apply` (LEAD decides).
  **It was NOT applied.**
- **Excludes `is_test = TRUE`** rows — these include tours deliberately hidden by
  the CLAUDE.md test-artifact rule, whose lat/lng were nulled on purpose
  (`tests/test_tour_helper.py`: cleanup UPDATEs lat=NULL, lng=NULL, is_test=TRUE —
  never DELETE). Also excludes derived/translation rows (`original_tour_id` not
  NULL).
- Lists **only rows created strictly after 2026-10-04**, so a pre-window hidden
  row is never resurrected.
- Reversible: the `--apply` UPDATE sets lat/lng only on rows that are **currently
  NULL** and never touches another column, creates, or deletes.

Dry-run against the dev DB (read-only, nothing written):

```
LOCAL-605 backfill_tour_coords — DRY-RUN (no writes)
  window: created_at > 2026-10-04
  excludes: is_test=TRUE (incl. deliberately-hidden), derived/translation rows

Found 2 NULL-coordinate candidate row(s) in the window.
  1 have a Stop 1 Coordinates line we could set.
  1 have NULL coordinates but no usable Stop 1 line (left untouched).

WOULD SET (reversible — these rows are currently NULL):
      id  created_at                    lat          lng  tour_name
     400  2026-10-07 01:14:11.210331    42.378100   -71.114200  Harvard Art Museums, Cambridge, MA - museum Tour

SKIPPED (NULL coords, no usable Stop 1 Coordinates line):
     397  WNDR museum, Boston, MA -  Tour  — no parseable Stop 1 Coordinates line

DRY-RUN complete. No rows were modified.
```

- **Row it would set:** tour **400** (Harvard Art Museums) → `lat=42.3781,
  lng=-71.1142` from its Stop 1 line.
- **Skipped:** tour **397** (WNDR, overview) — no parseable Stop 1 `Coordinates:`
  line, left untouched.

---

## 5. Regression tests (pytest) — exits

```
test_local590_assembly.py test_local590_orchestrator.py test_local590_pool_store.py
    42 passed            exit 0

tests/test_local597_by_reference.py tests/test_local597_guard.py
    22 passed            exit 0

tests/test_local599_official_site_discovery.py tests/test_local599b_maam_exhibitions.py \
tests/test_local599b_opening_section.py tests/test_local600_order_and_shortfall.py
    57 passed            exit 0

test_local591_contained_venue.py test_local591_every_stop_has_coordinates.py \
test_local591_one_scope_per_tour.py test_local591_verdict_equals_reasoning.py
    37 passed            exit 0

test_local605_tour_coordinates.py   (new)
    17 passed            exit 0
```

Total: **175 passed, exit 0** across all suites.

---

## 6. Live, isolated pool-reuse delivery (McMullen, 5 stops, cap $0.30)

Built `local605-gen-img` from `Dockerfile.generator` and ran a disposable
container **`local605-gen`** (`docker run --rm`) on the `development_default`
network (so `postgres-2` resolves), `COST_HARD_LIMIT_USD=0.30`. **No `audioura-*`
container was touched**; the container is `--rm` and the temp image was removed
afterwards.

The McMullen pool already held 10 stops, so requesting 5 (`N <= K`) served the
whole tour from the pool — the stop-pool reuse path, **zero new generation**.

```
[LOCAL-590] pool: venue=loc:mcmullen museum of art boston college boston ma type=museum
            category=museum contained=True requested=5 pooled=10
[LOCAL-590] POOL DELIVERY: reused=5 new=0 rewritten_transitions=0 about_stops=1 (pool held 10)

==========================================================================
LOCAL-605 RESULT
==========================================================================
  delivery_path         : pool
  pool_reuse            : True
  reused/new stops      : 5/0
  delivered stops       : 5
  new_cost (LLM)        : $0.0000
  wall                  : 5s
  RAW generator coords  : (None, None)   <- the LOCAL-605 bug (None,None on pooled)
  RESOLVED tour coords  : (42.3352, -71.1696)  source=venue
  coordinates present?  : True
==========================================================================
OK: pooled delivery carries real tour-level coordinates.
```

- **Before (the bug):** the pool path returned `(None, None)`.
- **After (the fix):** resolved to `(42.3352, -71.1696)` — McMullen Museum of
  Art's own Wikidata **P625** coordinates (`source=venue`). The delivered Stop 1
  also carried `Coordinates: 42.3392, -71.1675`, so the `stop1` fallback is present
  too; the contained-venue rule correctly preferred the venue's own location.
- Cost `$0.0000`, well under the `$0.30` cap.

---

## Constraints honoured

- **No DELETE. No GCloud. No UPDATE of `audio_tours`** (backfill ran dry-run only).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
- Isolated container only (`local605-gen`, `--rm`); `audioura-*` untouched.
- Branched from `subscribed` (HEAD `21b9eba`); committed after each step.
