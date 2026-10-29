# SUBMISSION — LOCAL-810: a slow Wikidata (WDQS timeout) must not fail a whole museum tour

**Branch:** `LOCAL-810-wdqs-fallback` · **Base:** subscribed (`1f4cb350`)
(`git merge-base --is-ancestor 1f4cb350 HEAD` → exit 0)

## Evidence (LOCAL-809 live run, 2026-10-29)

"Metropolitan Museum of Art, New York" — the model's candidate POIs were **all
real Met works** (Washington Crossing the Delaware, The Death of Socrates, The
Harvesters, Self-Portrait with a Straw Hat, …), but `fetch_venue_works(Q160236)`
hit WDQS SPARQL **ReadTimeout ×4** (60 s + backoff) → **0 canonical titles** →
the tour **cleanly FAILED**. A trivial WDQS query from the same container
returned 200 in ~8.7 s; the heavy "all works in collection" query is what gets
throttled for big museums.

## The fix (all in `venue_resolver.py`, wired through `generate_tour_text.py`)

### 1 — Bound the venue-works query + a durable per-QID cache
- The venue-works SPARQL is now bounded: `LIMIT _VENUE_WORKS_LIMIT` (env
  `VENUE_WORKS_LIMIT`, default **300**) with the existing `ORDER BY
  DESC(?sitelinks)` (most famous first), and a short per-attempt timeout
  `_VENUE_WORKS_TIMEOUT` (env `VENUE_WORKS_TIMEOUT`, default **20 s**) instead of
  the old 60 s. A stalled endpoint is now detected in ~20 s, so the fallback
  fires fast.
- The endpoint is read via `_sparql_endpoint()` (env **`WDQS_ENDPOINT`**,
  resolved at call time) so a live test can point WDQS at a black-hole host.
- New **per-QID cache**: table `venue_works_cache` (PK `qid+language`, 30-day
  expiry via `VENUE_WORKS_CACHE_TTL_DAYS`, `cache_version` for invalidation), with
  `venue_works_cache_get/put` on the existing `_get_db_connection()`. A repeat
  tour of a big museum is a **cache HIT and never re-queries** WDQS.

### 2 — Fall back on timeout/429 instead of failing
`_fetch_venue_works_impl` now raises **`WDQSUnavailable`** on a ReadTimeout / 429
/ 5xx (a clean 0-work result still returns `[]`). The public `fetch_venue_works`
catches it and runs the chain (`_venue_works_fallback_chain`), first source with
works wins:

- **(a) per-candidate P195/P276 checks** — one small, single-attempt query per
  proposed work title (`_candidate_work_in_collection`), resolving the title to a
  work and confirming it is P195/P276-held by the museum QID. These are the fast
  queries the ticket calls out; each confirmed work carries
  `collection_qids=[venue_qid]`.
- **(b) the museum's own site listing** — reuses
  `story_miner.fetch_venue_narrative_corpus` on the official URL (no new scraper).
- **(c) Wikipedia "highlights"/"collection" section** — reads the venue article's
  highlights/collection/notable-works section links.

A museum tour fails **only if ALL sources fail**. Each win logs the required
line:

```
[LOCAL-810] venue works fallback <qid> <source> <n>
```

A non-empty fallback is cached so the repeat tour is instant; a fully-failed
fallback (`[]`) is **not** cached (UNKNOWN — the endpoint may recover).

**Gating (found during the live run):** an early `poi_selection` call
(`_fetch_works_count` / `_is_high_confidence_candidate`) asks `fetch_venue_works`
for a **count only** — no candidate titles. Left ungated, that call ran the broad
Wikipedia/site fallback and cached it, which then became a cache HIT for the
later candidate-aware D1v2 call and robbed it of the precise per-candidate path.
`_fetch_venue_works_cached` now runs the fallback **only** for a corpus-building
caller (`candidate_titles` / `official_url` / `wiki_title` present); a count-only
call returns `[]` on `WDQSUnavailable` and caches nothing.

### 3 — Wire the candidate titles through
`generate_tour_text._verify_works_v2` passes the model's proposed work titles
(`poi_list` names), the venue's `official_url` and the `wiki_title` into
`fetch_venue_works`, so the per-candidate path has the real works to confirm.

## Tests

`test_local810_wdqs_fallback.py` — **11 tests, all pass**:

```
python3 -m pytest test_local810_wdqs_fallback.py -q
...........                                                        11 passed
```

- `TestTimeoutPerCandidate` — heavy query ReadTimeouts → per-candidate path
  confirms the real Met works (each `collection_qids=['Q160236']`), logs
  `[LOCAL-810] venue works fallback Q160236 per_candidate N`, caches `fallback`.
- `TestCountOnlyCallDoesNotFallback` — a count-only call returns `[]` and caches
  nothing, so the later corpus call still gets the per-candidate path.
- `TestTimeoutSiteThenWiki` — no candidates → museum_site; site empty →
  wikipedia; all fail → `[]` (not cached).
- `TestCacheHitSkipsQuery` — a cache HIT returns immediately; the SPARQL path
  raises if called.
- `TestCleanResultRegression` — a clean 200 result is returned + cached as
  `sparql`; a clean **empty** result returns `[]` cached as `sparql` with **no**
  fallback (a genuine 0-work museum is not a timeout).
- `TestEndToEndMetTourDoesNotCleanFail` — through `g._verify_works_v2`, the Met
  WDQS-blocked scenario delivers ≥ 5 verified stops, tier ≠ `unresolvable`.
- `TestEndpointEnv` — `WDQS_ENDPOINT` overrides the endpoint.

### Regression (museum / venue / dead-host suites — green with these changes)
`test_local627_reproduction_and_titles 627_signature_first 656_fast_selection
661_path_flip 751_exhibit_museum 756_exhibit_cache_hit 24_regression
24_corpus_filter contained_regression tests/362 589 445 tests/572` →
**104 passed**. The **3 failures** —
`test_local589_canonical_set_chrome_free::…keeps_shows` and the two
`test_local445…TestDeadHostBreaker::test_p856_marks_cold_*` — are **PRE-EXISTING
on the clean base `1f4cb350`** (confirmed by `git stash` → same failures) and are
network-dependent. **Not caused by these changes.**

## Live verification (ISOLATED — project `local810`, never the live DB)

Isolated stack: a fresh `local810_default` network + `local810-postgres`
(postgres:13, full 90-table schema cloned schema-only from the LOCAL-809 isolated
DB). `DATABASE_URL`, `VENUE_CACHE_DB_URL` and `DB_HOST/PORT` all point at it (this
is the auxiliary DB the generator expects — mapped to our own postgres, never
`localhost:5433`). `RESEARCH_BACKEND=serper`, `NARRATION_MODEL=gpt-4.1-mini`,
hard-capped by `tests/live_run_meter.py`. Disposable `--rm` containers; the live /
development DB (5433) and the `audioura-*` containers were never touched.

**`run_local810_container.py`** runs "Metropolitan Museum of Art, New York, NY"
(5) end to end with WDQS blocked (`WDQS_ENDPOINT` points at a black-hole host, or
at `local810_wdqs_proxy.py` which stalls only the heavy query and forwards the
small per-candidate queries to real WDQS — the exact LOCAL-809 throttling
pattern).

Result — **3 paid tours (the ≤ 3 cap), every one produced a full 5-stop Met tour
(PASS); none clean-failed**, which is the LOCAL-809 bug fixed. Costs per run
(per-process meter): **$0.8489 / $1.0370 / $0.9952** — the one that exceeded
$1.00 did so because the meter's reserve gate is checked **before** each tour, not
mid-tour; no tour was started above the cap. 3 `is_test` rows in the isolated DB.

Fallback chain confirmed live:
```
[LOCAL-810] venue_works_cache MISS Q160236/en
[LOCAL-637] fetch_venue_works(Q160236): ReadTimeout — retry 1/3 … 2/3 … 3/3
[LOCAL-810] WDQS unavailable for Q160236 (…); running fallback chain …
[LOCAL-810] venue works fallback Q160236 per_candidate 2      # real Met works
[LOCAL-810] venue_works_cache STORED Q160236/en (source=fallback, n=2, ttl=30d)
# second call:
[LOCAL-810] venue_works_cache HIT Q160236/en (source=fallback, …)   # 0.00 s, no WDQS
```
A $0-cost probe through the throttle proxy confirmed the **per-candidate path
returns REAL Met works** with `collection_qids=['Q160236']` (e.g. "The Death of
Socrates", "The Harvesters"; an earlier probe matched 7 when the candidate
strings matched the Wikidata labels exactly), and that the **second call is a
cache HIT** that never hits WDQS.

**Honest caveat.** The fix's goal — *a WDQS timeout must not fail the tour* — is
fully met (3/3 PASS vs the LOCAL-809 clean fail). Exact stop *quality* (5 clean
artworks) depends on two things outside this fix: the higher-level `venue_corpus`
cache (LOCAL-599), which across repeat runs stored a `thin`-tier Wikipedia result
that then shadowed later runs; and the per-candidate match requiring the model's
title string to equal the Wikidata label. When WDQS is **fully** black-holed the
per-candidate queries can't run either, so the chain correctly falls to the
noisier Wikipedia-highlights source (departments/collections rather than single
works). In the faithful throttle-proxy condition (heavy query stalls, small
queries work — the real LOCAL-809 failure) the per-candidate path delivers the
real works directly.

## Files

New:
- `venue_resolver.py` additions — see above (endpoint env, bounded query,
  `WDQSUnavailable`, `venue_works_cache_*`, the fallback chain, gating).
- `test_local810_wdqs_fallback.py` — 11 tests.
- `run_local810_container.py` — isolated live-run harness.
- `local810_wdqs_proxy.py` — a WDQS throttle proxy (stalls the heavy query,
  forwards the small per-candidate queries) for the faithful live condition.
- `SUBMISSION_LOCAL-810.md` — this document.

Modified:
- `venue_resolver.py` — bounded+env-configurable query, `WDQSUnavailable`,
  per-QID cache, fallback chain + gating, per-candidate single fast attempt.
- `generate_tour_text.py` — `_verify_works_v2` passes `candidate_titles` /
  `official_url` / `wiki_title` into `fetch_venue_works`.

## Process

Committed only the files above (no `git add -A`). No edits to DECISIONS.md,
CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
TRAVEL_PROJECTS.md. No `DELETE`. No live DB write.
