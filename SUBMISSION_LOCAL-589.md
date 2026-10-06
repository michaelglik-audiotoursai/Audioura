# SUBMISSION — LOCAL-589: Griffin exhibition tours made robust

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-589-exhibition-robust`
**Base:** `storied` = `af19b18` (`git merge-base --is-ancestor af19b18 HEAD` → exit 0)
**Commits ahead of storied:** 5 (`git rev-list --count storied..HEAD` = 5)

## The field defect (tour 394, 2026-10-05 22:43 UTC, Griffin, 7 stops → 5 delivered)
1. Site-first logged `ELIGIBLE`, then 90 s later `found no current exhibitions` with
   **nothing in between** — a `ReadTimeout` was swallowed, so a transient network
   failure looked identical to an empty site. (Ten minutes later the same call
   returned 9 shows.)
2. On that silent "empty", the pipeline **fell through to PHASE 3A** and GPT
   **invented** 7 shows; D1v2 dropped 6.
3. R4 refill then "VERIFIED" **site chrome** (`Function Rentals`, `Calls For Entry`,
   `Griffin Salon`, `Griffin Travel`, `Exhibitions Closed`, `Arthur Griffin Archive`,
   `Griffin Museum Board Of Directors 2`) because LOCAL-583's chrome rejection was
   applied only to the copy written to the cache, **not** to the canonical set R4 /
   D1v2 verify against.
4. 7 requested → 5 delivered.

## What shipped (one commit per deliverable, all pushed)

| # | Deliverable | Commit | Files |
|---|---|---|---|
| 3 (chrome) | Catch the two chrome names that escaped LOCAL-583 | `52d67a7` | `exhibition_discovery.py` |
| 3 (wiring) | One chrome filter on the canonical SET everyone verifies against | `bbea3ea` | `generate_tour_text.py` |
| 1 | Observable, retried site-first | `c02173f` | `exhibition_site_first.py` |
| 2 | No invention for exhibition museums on a fetch failure | `7b3a951` | `generate_tour_text.py` |
| 4 | Fill the count from real exhibitions | `24b18b9` | `generate_tour_text.py` |

### #1 — Observable, retried site-first (`exhibition_site_first.py`)
- `_default_fetcher` now **logs every fetch**: `[LOCAL-589][fetch] <URL> -> status=<s> bytes=<n> <secs>s[ EXC=<exception>]`, and returns a 3-tuple `(html, links, meta{status,error,bytes,seconds})`.
- `_fetch_with_retry` **retries the listing fetch once** on a transient failure
  (status ∈ {0,408,429,500,502,503,504}) with a **longer timeout** (15 s → 30 s).
  A single `ReadTimeout` can no longer masquerade as an empty site.
- `discover_site_exhibitions` / `build_site_first_candidates` populate a
  `diagnostics` dict with the **honest reason**: `ok` / `parsed_zero` /
  `no_listing_found` / `fetch_failed`, plus `fetch_failed: bool` and the per-attempt
  `fetches` records. Backward compatible: legacy `(html, links)` fetchers still work
  (`_normalize_fetch`), so the LOCAL-580 suite stays green.

### #2 — No invention for exhibition museums (`generate_tour_text.py`)
- Pure helper `_site_first_empty_action(reason, fetch_failed)` → `'overview'` on a
  fetch failure, `'fall_through'` on a reachable-but-empty site.
- The site-first consumption block now passes `diagnostics` to the builder; when
  candidates are empty it reads the reason. On `fetch_failed` (after the retry) it
  **does NOT fall through to PHASE 3A** — it takes the LOCAL-582 sourced-overview
  rung, and if even that is impossible it clean-fails with structured evidence.
  **GPT may only ever choose among real site exhibitions, never originate them.**
  A reachable site that genuinely lists zero shows still falls through (D577 — never
  turn a working tour into no tour); downstream GPT candidates remain gated by D1v2
  against the chrome-free canonical set from #3.

### #3 — One chrome filter everywhere (`exhibition_discovery.py` + `generate_tour_text.py`)
- `is_chrome_title` extended to catch the two field names LOCAL-583 missed, **without
  rejecting real shows**:
  - plural exact labels (`exhibitions closed`, `exhibitions archive`, …) and `closed`
    / `archives` chrome tokens → **"Exhibitions Closed"** is furniture;
  - a **terminal institutional-section rule**: a venue-branded title whose last word
    is a section token (`archive`, `salon`, `travel`, `rentals`, `bulletin`,
    `directors`, …) **and** that carries a venue-name word is a section of the venue,
    not a show → **"Arthur Griffin Archive"** (founder name + venue word + `archive`).
- `reject_chrome_titles` is now applied to the **canonical SET itself** — right after
  the LOCAL-24 work/non-work filter and **before** `corpus_result['canonical_titles']`
  is set — so D1v2 verification, R4 replenishment, UNIFIED-FILL, POST-R4-FILL and
  LOCAL-577's refill **all** verify against a chrome-free set. (The cache-write filter
  from LOCAL-583 remains as defense-in-depth.) Verified live: `[LOCAL-589] chrome
  rejected from the canonical SET (verified-against)`.

### #4 — Fill the count from real exhibitions (`generate_tour_text.py`)
- Pure helper `_site_fill_effective_cap(source, n_candidates, total_stops)`: for the
  `site_exhibition` path only, when **more real current shows exist than requested**,
  carry **one spare real exhibition** through narration. If a selected show's
  narration later comes back empty and the LOCAL-292 empty-stop gate removes it, the
  tour still delivers the requested count — then it is **trimmed back to exactly the
  ask** after that gate, and the LOCAL-394 invariant counter is re-based so a consumed
  spare is not mis-reported as a lost stop. The spare is always a REAL extra show;
  nothing is invented; all non-site paths keep the plain cap.

## #5 — Tests (red→green for 1–4) and suite exits

New (all red before the change, green after):
- `test_local589_chrome_field_names.py` — the two escaped names caught, real shows survive.
- `test_local589_canonical_set_chrome_free.py` — drives `_verify_works_v2`; the canonical
  set R4/fills verify against is chrome-free (11 → 4, all 7 field names dropped, 4 real shows kept).
- `test_local589_site_first_observable.py` — reason reporting, the retry recovers an
  intermittent failure, every fetch is logged, legacy 2-tuple fetcher still works.
- `test_local589_no_invention_on_fetch_failure.py` — the decision contract + real
  diagnostics + block wiring (overview rung, returns, no fall-through).
- `test_local589_fill_the_count.py` — the cap helper + the trim-back / invariant re-base wiring.

Required suites (all `EXIT=0`):

```
LOCAL-589 (5 files) ... 25 passed   EXIT=0
LOCAL-576 ............. 10 passed   EXIT=0
LOCAL-577 .............  9 passed   EXIT=0
LOCAL-580 (4 files) ... 25 passed   EXIT=0
LOCAL-582 ............. 20 passed   EXIT=0
LOCAL-583 (3 files) ... 26 passed   EXIT=0
LOCAL-584 (2 files) ... 24 passed   EXIT=0
LOCAL-586 ............. 12 passed   EXIT=0
```

## #6 — Live, ISOLATED (Griffin, 7 stops, three runs)

Isolated per CLAUDE.md: image `local589-gen:latest` built from this worktree
(`Dockerfile.generator`), run as one-shot `docker run --rm --name local589-gen
--network development_default --env-file /Users/micha/Audioura/.env` with the driver
`run_local589_griffin.py` and `tours` bind-mounted to the SSD. **No `audioura-*`
container was created, replaced, or stopped** — `audioura-tour-generator-1` stayed
`Up (healthy)` throughout.

Request: `Griffin museum of photography, Winchester, MA`, `museum`, 7 stops.
Every run: site-first found **9 real shows**, 12 `[LOCAL-589][fetch]` lines, **no GPT
invention, no chrome**.

### RUN4 (final code, post-#4) — the authoritative run

`[LOCAL-589][fetch]` lines:
```
[LOCAL-589][fetch] https://griffinmuseum.org/ -> status=200 bytes=246537 2.41s
[LOCAL-589][fetch] https://griffinmuseum.org/current-exhibitions -> status=200 bytes=277541 4.68s
[LOCAL-589][fetch] https://griffinmuseum.org/current-exhibitions -> status=200 bytes=277543 4.63s
[LOCAL-589][fetch] https://griffinmuseum.org/show/tlc/ -> status=200 bytes=340720 2.31s
[LOCAL-589][fetch] https://griffinmuseum.org/show/lua-kobayashi/ -> status=200 bytes=276797 3.10s
[LOCAL-589][fetch] https://griffinmuseum.org/show/bu-masters-show-2026-traces-pursuing-process/ -> status=200 bytes=296255 2.55s
[LOCAL-589][fetch] https://griffinmuseum.org/show/intertidal-field-notes/ -> status=200 bytes=439498 2.46s
[LOCAL-589][fetch] https://griffinmuseum.org/show/robertfrank_homage/ -> status=200 bytes=482744 2.64s
[LOCAL-589][fetch] https://griffinmuseum.org/show/earth-wind-fire/ -> status=200 bytes=266963 2.25s
[LOCAL-589][fetch] https://griffinmuseum.org/show/ultrasound/ -> status=200 bytes=266517 2.47s
[LOCAL-589][fetch] https://griffinmuseum.org/show/soren_fantasylife/ -> status=200 bytes=303501 2.53s
[LOCAL-589][fetch] https://griffinmuseum.org/show/nepr_0926/ -> status=200 bytes=347785 2.52s
```
```
[LOCAL-580] Site exhibitions found on https://griffinmuseum.org/current-exhibitions: 9 show(s)
[LOCAL-589] site-first fill headroom: carrying 8 real exhibition(s) through narration for a 7-stop request (spare 1 covers an empty-narration drop)
[LOCAL-394] Stop count invariant: OK (7 selected == 7 delivered)
[D536] Listener asked for 7 stop(s), delivering 7 — request met
[TIMING] TOTAL wall=787.6s phases: story_first=513.0s, external_lookups=197.9s, site_first_exhibitions=35.2s, ...
```
Stops delivered (all REAL Griffin shows):
```
Stop 1: BU Masters Show 2026 | Traces: Pursuing Process
Stop 2: Intertidal : Field Notes
Stop 3: Earth, Wind & Fire
Stop 4: Tabitha Soren | An Artist Life
Stop 5: TLC
Stop 6: Lua Kobayashi | The Persistence of Memories
Stop 7: Homage | Robert Frank: The Americans
```

### RUN2 and RUN3 (also 7/7)
Both delivered **7 real exhibitions** — `[D536] Listener asked for 7 stop(s),
delivering 7 — request met`. `[TIMING] TOTAL` wall = 707.7 s (RUN2), 749.4 s (RUN3);
`site_first_exhibitions` = 34.3 s / 35.1 s; 12 `[LOCAL-589][fetch]` lines each; no
invention, no chrome.

### RUN1 — the diagnostic that motivated #4 (pre-#4 image)
6/7: site-first found 9 real shows, all 9 cleared the gate, 7 were selected, then one
stop's narration came back empty and the LOCAL-292 empty-stop gate correctly removed
it → `[D536] … DELIVERING 6`. This is an intermittent model narration failure, not a
site-first / invention / chrome defect. Deliverable #4 (the one-spare headroom) closes
exactly this gap — confirmed by RUN4 above (`carrying 8 … spare 1`, delivered 7/7).

### Cost
OpenAI `Total API cost` per run: $0.7582 + $0.8582 + $0.8105 + $0.8612 = **$3.29**
across all four runs — **under the $4 cap**. (SERP/grounding is a separate line,
~$2.1/run, not OpenAI.) Nothing was ever DELETEd.

## Process
- `SUBMISSION_LOCAL-589.md` written. **Not** edited: `DECISIONS.md`, `CLAUDE.md`,
  `BACKLOG.md`, `WORK_QUEUE.md`, `.continuous_dev/STATUS.md`.
- `git add` + `git commit` after each step; `git push -u origin
  LOCAL-589-exhibition-robust`.
- `git rev-list --count storied..HEAD` = 5 (≥ 1). Base ancestry verified.
