# SUBMISSION — LOCAL-815: Re-pin EXISTING stored tours without regenerating

**Branch:** `LOCAL-815-repin-stored` (base: `subscribed` = `55994cab`, contains LOCAL-813)
**Deliverable:** `repin_tours.py` + `tests/test_local815_repin_tours.py`
**Ran on:** the Mac DB (`postgresql://admin:password123@localhost:5433/audiotours`) for catalog tours **854, 855, 857, 860, 861, 862** — dry-run report, then `--apply`, with pin_proof before/after.

---

## The problem

Pins improved a lot across LOCAL-791E → 803 → 813, but **tours already generated keep their old, LLM-written pins**. Regenerating a tour costs money and can change good content. We need to apply TODAY's `pin_snap` to a tour that is **already stored**, changing nothing but the coordinates.

## What `repin_tours.py` does

For each tour id, in one transaction:

1. **Reads the stops** (title + shipped coordinate) from `audio_tours.tour_content` and the stored ZIP (`audio_tours.audio_tour` bytea, or the R2 blob when the row uses one).
2. **Derives the tour's scope / city / bbox** from the stored `request_string` the *same way the generator does* (`generate_tour_text._scope_from_request` → `geocode_stops.geocode` → `stop_existence_gate._geocode_scope_bbox`), so the snap sees the context it saw at generation. **No regeneration, no LLM.**
3. **Runs the SAME `pin_snap.snap_pin`** the generator runs (`generate_tour_text.py` ~L26528), keeping every guard — name-match, stops-centroid, off-scope, and the museum-building fallback.
4. **If a stop moves more than 50 m** (`--move-threshold-m`), rewrites **only** the `Coordinates:` line in the **three places the app reads**:
   * `audio_tours.tour_content` (DB column),
   * the ZIP's per-stop text files `audio_N.txt` — *this is what the Flutter app actually reads for pins* (`navigation_service.dart`, `treats_source_resolver.dart`, `my_tours_screen.dart`; regex `Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)`),
   * the ZIP's `tour_content.txt` (the map/index copy).
5. **Stores the updated ZIP back** to `audio_tours.audio_tour`, and — **only when the row uses an R2 blob** (`tour_blob_uri` set) — re-uploads the object to R2. (The six Mac rows have `tour_blob_uri = NULL`, so their ZIP lives in the DB bytea; the R2 path is exercised on Cloud SQL rows that use one.)
6. **Bumps the version** via the EXISTING mechanism — the append-only `audio_tour_versions` archive that map-delivery reads as `MAX(version_no)+1` — so phones see a new version and re-download.

### Where the app reads pins (why these three places)

`index.html` has **no** coordinates — it calls the Flutter host (`openMap(stopNum)`). The pins come from the per-stop `audio_N.txt` files; `tour_content.txt` is the map/index copy and `audio_tours.tour_content` is the DB source of truth. All three are rewritten and kept consistent.

## Safety

* **Dry-run by default.** Prints per-stop old → new and the distance; writes nothing. `--apply` performs the writes.
* **One transaction per tour.**
* **Backup first:** the old `tour_content` and the old ZIP are written to `--backup-dir` before any write.
* **Never changes non-coordinate text** — only the number pair on a `Coordinates:` line is replaced, in place.
* **No `DELETE` anywhere** — only `INSERT` (version snapshot) + `UPDATE` (live row). Every change is reversible with the existing `restore_tour_version.py`.
* **Writes only to the ids in `--tour-ids`.**
* **Works against Cloud SQL (GCloud_Storied):** `--db-url` or the service env vars; no Mac-only paths.
* **Absurd-move cap** (`--max-move-km`, default 20 km): refuses a rewrite that would move a pin across cities even if a guard is disabled by a missing scope centre. (This caught Venice "Palazzo Ducale" first resolving to a palace ~140 km away near Modena; with the stored tour anchor used as the scope centre, pin_snap's own off-scope guard then resolves it to the correct Venice Doge's Palace, a 316 m move — see below.)

## Paid-API cap — **$0.20 TOTAL, lookups only**

The only paid call is Serper Places (Nominatim and Wikidata are free). A hard USD ceiling (`--max-api-usd`, default **$0.20**) is enforced by a metered Serper door: every Serper attempt is counted against the cap and, once the cap is reached, the Serper leg is skipped (a stop then resolves via free Nominatim/Wikidata or stays unsnapped). The `--apply` run — which runs pin_proof **before and after** each tour — used **62 Serper calls ≈ $0.186 of $0.20**. The cap held.

## Run: dry-run → apply (Mac DB, tours 854 855 857 860 861 862)

```
python3 repin_tours.py --tour-ids 854 855 857 860 861 862 \
    --db-url postgresql://admin:password123@localhost:5433/audiotours \
    --dry-run --pin-proof            # report, writes nothing

python3 repin_tours.py --tour-ids 854 855 857 860 861 862 --apply --pin-proof \
    --db-url postgresql://admin:password123@localhost:5433/audiotours \
    --backup-dir repin_backups/LOCAL-815_apply
```

**Applied: 12 stops rewritten across 5 rows (854, 855, 857, 860, 862). Tour 861 unchanged (0 stops moved).**

| tour | city | stops rewritten | version bump | pin_proof (≤100 m) before → after |
|------|------|-----------------|--------------|-----------------------------------|
| 854 | Kyoto (Higashiyama, walking) | 1 (Eikan-do Zenrin-ji 343 m) | v1 → **v2** | 4/5 → 4/5 (Eikan-do 294 m → 109 m, closer) |
| 855 | Tokyo (Asakusa, walking) | 2 (Hozomon 259 m, Asakusa Shrine 76 m) | v1 → **v2** | 3/4 → **4/4** |
| 857 | Lisbon (Alfama, walking) | 1 (Museu de Fado 240 m) | v1 → **v2** | 4/5 → **5/5** |
| 860 | Venice (San Marco, walking) | 4 (Campanile, Palazzo Ducale, Basilica, Museo Correr) | v1 → **v2** | **1/5 → 5/5** |
| 861 | Vienna (Belvedere **Museum**) | 0 | — (unchanged) | n/a (artwork stops, see below) |
| 862 | Hanoi (Old Quarter, walking) | 4 (Bach Ma, Dong Xuan, Thang Long, Ngoc Son) | v1 → **v2** | 0/5 → **4/5** |

### Example before/after — tour 860 San Marco, Venice (1/5 → 5/5)

Before:
```
| 1 | Campanile di San Marco | 45.43720, 12.33490 | 45.43404, 12.33903 | 477 m | ❌ |
| 2 | Palazzo Ducale         | 45.43400, 12.33640 | 45.43370, 12.34039 | 313 m | ❌ |
| 3 | Basilica di San Marco  | 45.43400, 12.33580 | 45.43456, 12.33971 | 312 m | ❌ |
| 4 | Teatro La Fenice       | 45.43330, 12.33400 | 45.43364, 12.33376 |  42 m | ✅ |
| 5 | Museo Correr           | 45.43350, 12.33360 | 45.43379, 12.33721 | 283 m | ❌ |   1/5
```
After:
```
| 1 | Campanile di San Marco | 45.43403, 12.33903 | 45.43404, 12.33903 |  1 m | ✅ |
| 2 | Palazzo Ducale         | 45.43367, 12.34042 | 45.43370, 12.34039 |  5 m | ✅ |
| 3 | Basilica di San Marco  | 45.43444, 12.33972 | 45.43456, 12.33971 | 13 m | ✅ |
| 4 | Teatro La Fenice       | 45.43330, 12.33400 | 45.43364, 12.33376 | 42 m | ✅ |  (not moved, already ≤50 m)
| 5 | Museo Correr           | 45.43393, 12.33713 | 45.43379, 12.33721 | 17 m | ✅ |   5/5
```

### Tour 861 Belvedere Museum — correctly left untouched

The five stops are **artwork titles** ("Judith I", "The Evil Mothers", …) that all share the museum's single building pin (48.2031, 16.3747). None has a per-stop reference of its own, the generic geocoder's only hit ("Lower Belvedere") is refused by the name-match guard, and the museum-building fallback did not resolve for this venue. `pin_snap` therefore leaves every stop as-is — exactly the right call — so tour 861 was not rewritten and its row is byte-identical.

## Verification of the apply

Confirmed directly against the DB after `--apply`:

* **Rows changed:** 854, 855, 857, 860, 862 (`md5(tour_content)` differs; ZIP grew a few bytes from coordinate reformatting). **861 unchanged** (`md5` identical).
* **No rows created or deleted:** `audio_tours` stayed at **563** rows; `audio_tour_versions` went **86 → 91 (+5)**, one archive row per changed tour.
* **Version bump is reversible:** each changed tour now has `MAX(version_no) = 2`; the new archive row (`replaced_by_job = 'repin_tours_LOCAL-815'`) carries the **OLD** content — `md5` equals the pre-apply content `md5` for all five. No `DELETE`.
* **Backups on disk** in `repin_backups/LOCAL-815_apply/`: the old `tour_content.txt` and the original ZIP for each changed tour, sizes matching the originals.
* **Three-place rewrite is consistent (tour 860):** DB `tour_content`, ZIP `audio_2.txt`, and ZIP `tour_content.txt` all show Palazzo Ducale at `45.433667, 12.340417`; Teatro La Fenice kept `45.4333, 12.334`. Non-coordinate ZIP entries (`index.html`, every `audio_N.mp3`, `manifest.json`, `service-worker.js`) are **byte-identical** to the backup.

## Tests

`tests/test_local815_repin_tours.py` — 9 tests, fully **offline** (an injected reference door; no network, no paid API), over an in-memory stored-tour fixture (real `tour_content` text + a real ZIP with `audio_N.txt` and `tour_content.txt`):

* **AC1** — the `Coordinates:` line is rewritten in all three places for every stop that moves > 50 m.
* **AC2** — nothing else changes: exactly one content line differs; the other ZIP entries are byte-identical; `audio_1.txt` changes only on its coordinate line.
* **AC3** — a stop ~8 m off its reference is left untouched.
* **AC4** — the version is bumped via an append-only `audio_tour_versions` row (`version_no = MAX+1`) carrying the OLD content; no `DELETE`; one commit.
* **AC5** — the old content and ZIP are backed up to disk first.
* **AC6** — dry-run writes nothing (no INSERT/UPDATE, no backup, no commit).

```
python3 -m pytest tests/test_local815_repin_tours.py -q
......... 9 passed
```

## Files

* `repin_tours.py` — the tool (dry-run default; `--apply`, `--tour-ids`, `--db-url`, `--move-threshold-m`, `--max-api-usd`, `--max-move-km`, `--backup-dir`, `--pin-proof`).
* `tests/test_local815_repin_tours.py` — the unit tests.

(The `repin_backups/` folder written during the apply is local backup data and is **not** committed.)
