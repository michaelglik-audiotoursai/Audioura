# SUBMISSION — LOCAL-824: /geocode (and the map-delivery parity gap) reached the cloud

**Branch:** `LOCAL-824-map-delivery-parity` (base `subscribed` = `7984988a`)
**Bug:** `GET /geocode` → **404** on `subscribed-api.audioura.com`. LOCAL-793 added
the server-side place geocoder to the repo-root `map_delivery_service.py` only.
Cloud Run's map-delivery image runs **`map_delivery/app.py`**, which had no
`/geocode`, so the Home place-search fallback silently did nothing on the cloud.

---

## 1. Root cause — two map-delivery files, one deployed

There are two Flask apps for map-delivery:

| File | Role | Who runs it |
|------|------|-------------|
| `map_delivery_service.py` (repo root) | the Mac dev monolith | `docker-compose.yml` (`command: python map_delivery_service.py`) — an older/alternate compose used on the Mac |
| `map_delivery/app.py` | the service image | **Cloud Run** and `docker-compose-master.yml` (`build: ./map_delivery` → `Dockerfile` `CMD ["python","app.py"]`) |

This split is already documented in SUBMISSION_LOCAL-88/89/117 and UNWIRED_AUDIT.md.
A LOCAL fix proven on the Mac against the root file does **not** reach the cloud
unless it is also made in `map_delivery/app.py`. LOCAL-793 is exactly that: it
landed in the root file (`_geocode_via_serper`, ~line 741) and nowhere else.

A second, quieter trap: `map_delivery/Dockerfile` builds from context
`./map_delivery` with `COPY . .`, so a repo-root-only module (`serper_meter.py`)
is **not** in the image. Porting the route alone would still have lost the paid
Serper path in the container.

---

## 2. Audit — every route, change → in root? → in app.py? → action

Routes present in exactly one file (converter types normalised, `<int:x>`≡`<x>`):

| Route / change | in root? | in app.py? | Action |
|---|---|---|---|
| **`/geocode` (LOCAL-793)** | ✅ | ❌ | **PORTED** — the bug |
| `?track=` filter + `VALID_TRACKS` + `normalize_track` (LOCAL-737/D708) | ✅ | ✅ | parity — none |
| `safe_headers` secret redaction (LOCAL-782) | ✅ | ✅ | parity — none |
| token-based multi-word name search (LOCAL-798) | ✅ | ✅ | parity — none |
| `/tour/<id>/update-stop`, `/edit-info`, `/create-custom` | ✅ | ❌ | allowlist — served on the cloud by **`tour_editing_service.py`** (`Service.tourEditing`, :5022, `/tour-editing`); the app routes stop edits there, not to map-delivery |
| `/tour/<id>/resolve` | ✅ | ❌ | allowlist — served by **`tour_id_resolution_service.py`** (`Service.tourIdResolution`, :5025, `/tour-id`) |
| `/tour/<id>/version`, `/tours/check-versions`, `/version-test` | ✅ | ❌ | allowlist — no app consumer (grep of `audio_tour_app/lib` finds none); legacy / dev smoke routes |
| `/tour-by-code/<code>`, `/report-tour`, `/tour/<id>/preview-audio`, `/tour/<id>/download-failed`, `/tour/<id>/score-explanation`, `/tour/<id>/match`, `/tour/<id>/rescore-request`, `/how-we-score` | ❌ | ✅ | allowlist — cloud-era features (LOCAL-657+/688/689/785); served by map-delivery on the cloud, never added back to the dev monolith |

**Conclusion:** the only genuine *app-facing* map-delivery parity gap was
`/geocode`. Every other one-file-only route is either owned by a dedicated cloud
service the app calls directly, or has no app consumer. The behavioural LOCAL-7xx
changes (737, 782, 798) were already in both files.

---

## 3. The fix

### `map_delivery/app.py` — ported `/geocode` (same behaviour as the root monolith)
- `GET /geocode?q=<place>` → `{lat,lng,name}` 200, or `{error}` 404, `{error:"missing q"}` 400.
- **Serper Places first**, metered via `serper_meter.serper_post` — typo-tolerant;
  first result with usable lat/lng wins. **Cap: one paid query per lookup** (`num=5`).
- **Nominatim fallback** (free), preferring a PLACE class over a nearer POI — the
  LOCAL-793 point ("Saigon Vietnam" must not open a Paris restaurant). Implemented
  with **stdlib `urllib`** so no `requests` dependency is added to the lean cloud
  image (the root file used `requests`; the call shape is identical).
- **Cache:** a bounded in-process LRU (`_GEOCODE_CACHE`, 256) keyed on the folded
  query returns a previously resolved place **without a second paid call** — a
  repeat lookup for the same place costs **$0** (cap-friendly). Per-process, resets
  on restart (no stale global state).
- The `serper_post` import uses the same belt-and-suspenders pattern as
  `safe_headers`/`failure_log`: import the sibling module, with a repo-root
  `sys.path` fallback for host/test runs. Fail-open — a missing module leaves the
  Serper path off and `/geocode` still serves via Nominatim.

### `map_delivery/serper_meter.py` — vendored (new file)
An identical copy of the repo-root `serper_meter.py`, exactly as `map_delivery/`
already vendors `safe_headers.py` and `failure_log.py`. Required because the image
builds from `./map_delivery` — without it the container would lose the metered
Serper path. It uses only stdlib and finds the paid-API meter via
`/opt/meter` (PYTHONPATH) at runtime.

### `map_delivery/Dockerfile` — a comment
Documents why `serper_meter.py` sits in this directory, so the next maintainer
does not "clean it up".

---

## 4. Recurrence guard — `tests/test_local824_route_parity.py`

AST-parses every `@app.route('<path>')` from **both** files, normalises converter
types, and **FAILS when a route exists in one file but not the other** unless the
difference is in an explicit allowlist that carries a per-entry reason
(`ROOT_ONLY_ALLOWLIST` / `APP_ONLY_ALLOWLIST`, matching the audit table above).
A fourth test (`test_allowlists_are_not_stale`) fails if an allowlisted route is
no longer one-file-only, so the allowlist cannot rot.

Proven to bite: simulating the LOCAL-824 drift (remove `/geocode` from `app.py`)
makes the guard report `unexplained=['/geocode']` and fail.

### Long-term single source (out of scope here — what it would take)
The real cure is **one** source of truth, two options:
1. **Delete the root monolith** and point the Mac dev stack at the same
   `map_delivery/app.py` image (change `docker-compose.yml`'s
   `command: python map_delivery_service.py` to the map-delivery build). Risk: the
   dev stack's muscle memory and any Mac-only route in the monolith.
2. **Extract shared handlers** into a module both apps import, leaving each file a
   thin entrypoint.

Both touch the Mac dev workflow and every future LOCAL fix's habits, so they are a
deliberate refactor. Until then, the parity guard holds the line.

---

## 5. Tests

```
tests/test_local824_geocode_parity.py  ... 7 passed
  route registered · Serper one-call cap · cache prevents 2nd paid call ·
  Nominatim prefers PLACE over POI · Serper-miss→Nominatim · 404 · 400
tests/test_local824_route_parity.py    ... 4 passed
  /geocode in both · no unexplained root-only · no unexplained app-only ·
  allowlists not stale
```

Both files' existing suites (run together): **80 passed**
(`test_local798` exercises the search logic in *both* files; `test_local737`
track filter; `test_local687/688/689` the app.py cloud features; plus the 11
above). The only failures anywhere were the 4 in
`tests/test_local88_tour_pollution.py` — a **live-production-DB** test that imports
no map-delivery code and asserts data invariants (null lat/lng on prod rows
41–53). It fails **identically with my edits reverted**, so it is pre-existing and
unrelated.

---

## 6. Live proof — the ACTUAL cloud image, metered, under budget

`./run_local824_live.sh` builds the map-delivery image from **its own Dockerfile**
(`./map_delivery` → `CMD python app.py` — the exact image the cloud runs), tags it
`local824-map-delivery:latest` (**never** an `audioura-*` tag), and runs it as its
**own** disposable container `local824-md` on spare port **5824** with its **own**
throwaway postgres (the live DB is never touched). Meter contract per
`meter_container_env.docker_meter_args`: `PYTHONPATH=/opt/meter`,
`PAID_API_LOG=/meterlogs/paid_api_calls.jsonl`, `METER_SERVICE=LOCAL-824`,
`-v _meter:/opt/meter:ro`, `-v ~/Audioura/meterlogs:/meterlogs`.
`TASK_BUDGET_ID=LOCAL-824 TASK_BUDGET_USD=0.05`.

```
########## GET /geocode?q=Mui Ne ##########
{ "lat": 24.2918414, "lng": 116.1171428, "name": "Meizhou, Guangdong, China" }

########## GET /geocode?q=Venice, FL ##########
{ "lat": 27.0998315, "lng": -82.4442832,
  "name": "Venice, Sarasota County, Florida, 34285, United States" }
```

Both return **200** — the bug was **404**. The endpoint is reachable on the cloud
image, which is the parity proof.

**Metered Serper path is live** (2 rows on the host meterlog, `service=LOCAL-824`,
`status=200`, `$0.002` each):

```
$ python3 meter_report.py --since 2026-10-30 --kind serper
BY SERVICE
LOCAL-824        2    0.0040    ...
```

**Total $0.0040 for 2 Serper calls — under the $0.05 budget, and ≤ 4 calls.**
Both lookups resolved via Nominatim: Serper *was* called and metered (200), but
its `/places` response for these bare queries had no usable lat/lng, so the code
fell through to Nominatim — byte-identical to the root monolith's
`_geocode_via_serper`. Containers were auto-removed on exit (trap).

### Note on `task_budget_report.py LOCAL-824`
```
$ python3 task_budget_report.py LOCAL-824
No ledger for task LOCAL-824 (~/.audioura_task_budgets/LOCAL-824.json). No runs recorded yet.
```
`task_budget_report.py` reads the ledger that **`LiveRunMeter`** writes — the
in-process harness used by tour-generation runs. This task's paid calls were made
by a **container** (`/geocode`'s Serper request), which is attributed through the
canonical **meterlog** per the LOCAL-822 contract, not the LiveRunMeter ledger.
The authoritative spend for this task is therefore the `meter_report.py` line
above: **LOCAL-824 = 2 requests, $0.0040**.

---

## 7. Files changed (only these; no `git add -A`)
- `map_delivery/app.py` — ported `/geocode` (+ Serper/Nominatim helpers, cache, import)
- `map_delivery/serper_meter.py` — vendored metered Serper door (new)
- `map_delivery/Dockerfile` — comment documenting the vendored module
- `tests/test_local824_geocode_parity.py` — `/geocode` behaviour (new)
- `tests/test_local824_route_parity.py` — the recurrence guard (new)
- `run_local824_live.sh` — the live proof harness (new)
- `SUBMISSION_LOCAL-824.md` — this document
