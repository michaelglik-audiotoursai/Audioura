# Where things stand — 2026-09-24 afternoon

Written while Michael was out. Branch `fix/local554-title-case-blocker`.
**`storied` is untouched at `c5c5b7c`** — the GCloud E2E has not run yet.

---

## Your restaurant tour: the blocker is fixed, and it was Igor's feature working

Your test *did* exercise Igor's enhancement. You typed three restaurants, all three
were honoured as forced stops, all three stops were written — 233, 268, 241 words —
and then the finished tour was **thrown away at the last gate**:

```
FAIL: D3(d) Grounding assertion — 1 suspicious title(s):
      ['little big diner in newton center']
[BLOCKER4c] FACTUAL QA FAILED (round 1): 1 factual failure(s)
```

Little Big Diner is a real restaurant at 1247 Centre St with 625+ reviews. The rule
was literally `not _name_part[0].isupper()` — **a real place rejected for lower case**,
by a *factual* check that destroys the whole tour.

The pipeline had already worked out the right names and discarded them, because
forced stops are pinned verbatim:

```
PHASE 3B introduced unknown names (ignored): ['Sycamore', 'Little Big Diner']
```

**Root cause — a design mismatch.** `forced_stops` says in its own comment
*"THIS IS A VERIFICATION HARNESS — NOT A PRODUCT FEATURE"* (LOCAL-357). LOCAL-525
repurposed it as the product path for user-chosen stops. A harness passes names
through verbatim; a product cannot, because nobody types a tour stop in title case.

**LOCAL-554** — title-case a listener's own words. Conservative: a name already
containing capitals is untouched, so `O'Hara's Food & Spirits` and `MoMA` survive.
Verified on seven cases. Plus: capitalisation can never again fail a tour factually.

## LOCAL-555 — two length rules contradicted each other

With 554 fixed the tour failed again, at **918 words against a 1000 floor**. But the
per-stop rule directly above blesses 150 words for a first/last stop and 200 for a
middle one — so a 3-stop tour can be 500 words with every stop in range, and then be
rejected as truncated.

The floor now scales with stop count, capped at the original 1000, so **nothing got
looser**: a 6-stop tour faces exactly the floor it always did.

## Sharing — ST-1 to ST-4 work on local Docker

```
POST /tour/share {"audio_tour_id": 365}  ->  {"share_id": "FFush25U"}
GET  /tour-by-code/FFush25U              ->  tour 365
POST again                               ->  "FFush25U"   (idempotent)
```

Shape compatibility with `/tours-near` proven key by key on live responses —
missing `[]`, extra `['via_share_code']` — so pick → download → translate work
unchanged. `original_tour_id` is carried, since that is the chain the app follows to
offer a translation.

**ST-5 (email) is closed, by your own answer.** *"All we need is a link and we will
let anyone send it in any way they wanted."* The OS share sheet does it and handles
deliverability and abuse better than we would.

### Two things found on the way

- **`POST /tour/share` returned 503 on local Docker** — no `GATEWAY_API_KEY` here, so
  sharing could not be tested on this machine at all. Opened for local only, behind an
  explicit `ALLOW_UNAUTHENTICATED_SHARING` flag in the local compose file. **Not a
  silent fail-open:** that endpoint writes, and your "everything must be public" ruling
  is about shares being *readable*, not about letting anyone write rows.
- The endpoint belongs in **`map_delivery/app.py`** — the file the container actually
  builds from. The root `create_map_delivery_service.py` is **not deployed** and its
  entry shape is two fields stale. My first attempt went there and was reverted.

## ⚠️ CORRECTION — Igor's enhancement is NOT reliably working

I told Michael at 16:12 that his three restaurants "now generate correctly". That was
true of ONE run and I reported it too early. The next run, same three stops, a fresh
location, persisted this:

| requested | stop header | mentioned |
|---|---|---|
| Sycamore | **0** — header stripped | 7 |
| Buttonwood | **0** | **0 — absent entirely** |
| Little Big Diner | 1 | 5 |
| Farmstead Table *(never requested)* | 1 | 6 |

Two distinct failures, on top of each other:

**1. A stop whose header was stripped.** Sycamore's prose is in the tour — "Sycamore
began its journey under the guidance of Chef David Punch" — but there is no
`Stop 2: Sycamore in Newton Center` line, no Address, no Type. The tour reads
Stop 1 → Stop 3. The app parses stops by header, so that stop is invisible to it.

**2. Buttonwood vanished completely** — zero mentions anywhere — and Farmstead Table,
which nobody asked for, took the first slot.

So across runs the same request produces different results: one run delivered all
three correctly, the next delivered one. **This is non-deterministic and not ready
for Michael to judge.** The three bugs I fixed today were real and are fixed; they
were not the whole problem.

## What is NOT done

- **ST-4's app-side button.** The server half works; the Flutter button is not written.
- **App rebuild.** ST-3's search-code detection is in `home_screen.dart` and compiles
  (0 errors), but the app on your phone does not have it yet. **Blocked on disk** —
  ~2 GB free, and an iOS build needs several. The SSD arrives Friday.
- **One stop was substituted** in an earlier run: you asked for Sycamore and got
  Farmstead Table, after Sycamore's OSM lookup failed. Two of three survived. Worth
  chasing — a named stop should be announced, never swapped.

## Disk — the day's real hazard

Filled to **zero** twice, and the second time took the database offline: Docker wedged
exactly as `CLAUDE.md` records from 2026-09-02. Recovered by the documented route
(kill `com.docker.backend`, relaunch) — **never** Reset to factory. Database verified
intact afterwards: 179 rows, benchmarks 29–33 present.

Three iOS builds in one day generate several GB of DerivedData each. **The SSD is now
load-bearing, not a convenience.**
