# SUBMISSION — LOCAL-656 (fast selection: resolve the venue once per tour, overlap the preflight)

**Branch:** `LOCAL-656-fast-selection`
**Flag:** `FAST_PIPELINE` (default **OFF** — the shipped default is byte-identical to today)

LOCAL-656 adds, behind `FAST_PIPELINE=1`:

1. A per-tour memo so `resolve_venue` (Wikidata) and `fetch_venue_works` (SPARQL)
   each run **once** per tour for the same inputs — the LOCAL-651 profile saw them
   run 4× and 3× for the SAME venue in one `poi_selection`.
2. An up-front **overlap**: the venue preflight (~14 s) and the venue resolution
   (~2.7 s) are independent and today run one-after-another; with the flag ON the
   resolve runs on a worker thread while the preflight runs on the main thread, so
   `poi_selection` wall drops by the shorter wait.

When `FAST_PIPELINE` is OFF, `is_enabled()` is False, no thread pool is started,
and the memo is never consulted — every call runs exactly as before.

---

## 656B — rebase onto current `subscribed` + reconcile with LOCAL-651 and LOCAL-661

**Agent:** Mac Mini Kiro **Base:** `subscribed` = `4cc74f4d`

### Why
LOCAL-656 was built on a stale base (`8e12c846`) and its live test hung and was
killed by LEAD. Merging onto the current `subscribed` conflicted in four files
because work had landed there in the meantime:

- `fast_pipeline.py` — **add/add**: LOCAL-651 had already created it (its
  `run_parallel` + `is_enabled`, used by the OSM / knowledge-fallback / stop-editor
  prefetch call sites).
- `phase_timer.py` — LOCAL-651's `SubTimer` / `[TIMING-SUB]`.
- `venue_resolver.py` — LOCAL-661 added an **always-on** per-tour resolution memo
  for 429 safety (a Wikidata rate-limit must not make a resolved famous collection
  look like "no Wikidata entity" and flip it onto the exhibition site-first path —
  Bench AB6 tour 639, the Frick).
- `generate_tour_text.py` — LOCAL-655 current-affairs priming at the wrapper entry.

### What was delivered

**Rebased** the 4 LOCAL-656 commits onto `subscribed` (`4cc74f4d`), not
`origin/*`. `git merge-base --is-ancestor 4cc74f4d HEAD` exits 0.

**ONE `fast_pipeline.py`.** Kept LOCAL-651's `run_parallel` + `is_enabled`
(the prefetch call sites depend on them) and added LOCAL-656's per-tour memo
primitives (`memoize_per_tour`, `seed`, `recall`, `reset_tour_memo`) in the same
module. No second copy of either half.

**ONE `SubTimer`.** Took `subscribed`'s `phase_timer.py` — LOCAL-651's SubTimer is
identical to (a superset of) what LOCAL-656 step 1 added, so there is one.

**ONE per-tour venue memo.** This is the heart of the reconciliation. LOCAL-661's
**always-on 429-safety** resolution memo is kept as the single venue store, and
LOCAL-656's **FAST_PIPELINE speed** behaviour is woven INTO it — not a second
cache:

- `resolve_venue` keeps LOCAL-661's wrapper (`@_sub_timed('resolve_venue')`,
  `_resolve_memo_remember` on success, `_resolve_memo_recall` on a None returned
  *under an observed network failure / cold host*). On top of that, when
  `FAST_PIPELINE` is ON a repeated identical resolve returns the entity already
  in **that same LOCAL-661 store** before the impl runs — collapsing the duplicate
  calls (4 → 1). When OFF the fast-path is skipped and every call runs (661
  unchanged).
- `fast_pipeline.reset_tour_memo()` also clears `venue_resolver.reset_resolution_memo()`,
  so the per-tour boundary (the tour wrapper and the pytest `conftest.py` autouse
  fixture) resets the one venue store.
- `fast_pipeline.seed("resolve_venue", (venue, city), {}, entity)` — used by the
  up-front overlap to hand the prewarmed entity back to the main tour — writes to
  that same LOCAL-661 store (`_resolve_memo_remember`), so the first in-pipeline
  `resolve_venue` is a genuine HIT.
- `fetch_venue_works` keeps LOCAL-661's UNKNOWN-vs-empty failure counting in
  `_fetch_venue_works_impl`, with the FAST_PIPELINE per-tour memo over it so the
  repeated identical SPARQL (3 → 1) collapses.

**The overlap stays behind `FAST_PIPELINE=1` (default OFF).** The LOCAL-655
current-affairs priming and the LOCAL-656 per-tour memo reset both run at the
wrapper entry (both kept).

### Tests (flag OFF unchanged)

The three named suites are green (exit 0):

```
test_local651_fast_pipeline.py  test_local651_sub_timer.py
test_local656_fast_selection.py test_local661_path_flip.py
  → 46 passed
```

Broader venue/pipeline suites (LOCAL-24/583/605/618/625/627/632/636/637/639/650/
653/655, w4) all pass. The one failure observed —
`test_local589_canonical_set_chrome_free.py` — **fails identically on `subscribed`**
(it is network/cache-dependent) and is NOT introduced by this merge; verified by
checking the test out on `subscribed`.

`FAST_PIPELINE` defaults OFF (`fast_pipeline.is_enabled()` is `False`).

### Offline proof (no live run, no paid API)

`proof_local656b_offline.py` (+ `.log`) runs against the REAL merged
`venue_resolver.resolve_venue` and the merged overlap structure, with fakes timed
to the LOCAL-651 profile (resolve 2.7 s ×4, preflight 14 s). No network, DB, paid
API or live run.

| Claim | OFF | ON |
|---|---|---|
| **resolve_venue call count** | 4 resolve_venue() → **4** impl calls (byte-identical; `[TIMING-SUB]` shows 4×2.7 s) | 4 resolve_venue() → **1** impl call + 3 memo hits (0.00 s); wall 11.03 s → 2.77 s |

| Claim | SERIAL (today) | OVERLAP (ON) |
|---|---|---|
| **poi_selection wall** | preflight 14 s + resolve 2.7 s = **16.75 s** | max(14, 2.7) = **14.08 s** |

In the overlap case the in-pipeline `resolve_venue` after the join is a **memo HIT**
(the seed fed the SAME LOCAL-661 store, so impl calls stay at 1, not 2).
`poi_selection` wall dropped ≈ 2.67 s.

**Both claims PROVEN offline.** No live run. No DELETE. No GCloud.
