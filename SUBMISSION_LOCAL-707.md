# SUBMISSION — LOCAL-707: the paid-API meter stopped recording Serper after Oct 13; make every Serper call metered

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-707-serper-meter` (from `subscribed` = 99942cce)
**Budget:** 1 Serper credit used (cap ≤ 5).

---

## 1. The symptom

`~/Audioura/meterlogs/paid_api_calls.jsonl` (the network meter, LOCAL-621/678) carried
thousands of Serper rows through Oct 11, then **none from Oct 12 on**, while OpenAI and
Gemini rows kept being written every day. Serper was still being used daily (artist-life
research LOCAL-692, serper_plus walking research LOCAL-674, the news endpoint), so the
prepaid Serper balance Michael estimates from the ledger had gone blind.

Counts read from the live log on this machine:

```
kind=serper : Oct08 1142 | Oct09 3689 | Oct10 129 | Oct11 212 | Oct12..15 0 | Oct16 1 (a manual probe)
kind=openai : … Oct13 20 | Oct14 56 | Oct15 35 | Oct16 28   (continuous)
kind=gemini : … Oct13 20 | Oct14 14 | Oct15 35 | Oct16 27   (continuous)
```

## 2. Root cause

The one meter change in that window is **LOCAL-678, commit `53736d4d` (2026-10-13 16:45)**,
which added httpx + aiohttp patching to `_meter/paid_api_meter.py` to close the OpenAI/Gemini
**SDK** blind spot (those SDKs send over **httpx**).

The split is the tell:

* **OpenAI and Gemini go out over httpx** (the SDKs) → kept logging after Oct 13.
* **Serper goes out over urllib / requests** (`work_story_searcher`, `current_affairs_news`,
  `exhibition_checklist`, …) → stopped logging after Oct 13.

So from the moment httpx/aiohttp metering shipped, the urllib/requests path stopped producing
Serper rows in the live container while the httpx path kept working. LOCAL-678's tests only
proved httpx (OpenAI) and aiohttp — **nothing asserted that a Serper call over urllib or
requests is still metered**, so the regression shipped silently.

(The network patches still demonstrably work on a clean host — reproduced with a local mock
server, both urllib and requests Serper calls recorded — which is why the failure is specific
to the long-lived container's interpreter state. Rather than depend on perfectly reproducing
that state, the fix removes the dependency on it entirely.)

## 3. The fix — belt (explicit) **and** suspenders (hardened network layer)

### a) One metered door: `serper_meter.py` (new)
`serper_post(url, payload, api_key, timeout)` makes the Serper request **and guarantees one
`paid_api_calls` row for it**, by calling `paid_api_meter.record_call()` itself — independent
of whether the network patch is installed in that process. `serper_search()` is the thin
organic-search convenience wrapper. Fail-open throughout: a meter error never touches the HTTP
request; if the meter module cannot be imported the request still goes out (unmetered, exactly
as before).

### b) No double-count: thread-local explicit marker — `_meter/paid_api_meter.py`
`serper_post` sets a thread-local marker (`_mark_explicit`) around the request and the four
network wrappers (requests / urllib / httpx-sync / httpx-async / aiohttp) now **skip recording
a request whose marker is set** (`_is_explicit`). Result: whichever path is live, the call is
metered **exactly once**; if both are live, still exactly once. A new public `record_call()`
is the explicit entry point (same costing, log and DB behaviour as the automatic wrappers).

### c) Every real Serper call site routed through the door
`work_story_searcher._serp_search`, `current_affairs_news._serp_news`,
`serper_plus_research._serper_news`, `exhibition_checklist` (both sites),
`interpretive_enrichment` (both sites), `exhibition_site_js.default_serper`,
`venue_resolver._serper_search`, `dining_corpus_harvester`, and the `preflight.check_serper`
probe. (The per-tour `cost_accumulator.add_search_queries(1)` breakdown calls are unchanged —
that is the separate per-tour ledger-row breakdown, not the network meter.)

Because the door writes the row directly, this is robust to the exact container state that
broke Oct 13: even a process where the network patch failed to install still meters Serper.
Future Serper callers are kept honest by the static-scan guard (§4).

## 4. Tests

### `tests/test_local707_serper_metered.py` (5 tests) — the regression gap LOCAL-678 left
Local mock HTTP server, no real network, DB + daily-limit stubbed.
1. `test_network_urllib_serper_metered` — a **urllib** Serper POST is metered (the client that
   silently stopped).
2. `test_network_requests_serper_metered` — a **requests** Serper POST is metered.
3. `test_serper_post_guarantees_row_without_patch` — `serper_post` writes the row **with the
   network patch NOT installed** (the belt).
4. `test_serper_post_no_double_count_with_patch` — patch live + explicit record → **exactly one
   row** (the marker).
5. `test_serper_post_non200_is_zero_cost` — a non-200 is recorded at **$0.00**.

### `tests/test_local707_serper_scan_guard.py` (2 tests) — LOCAL-705-style static scan
Fails if any `*.py` uses a `serper.dev` URL **string literal** (AST — comments/docstrings
excluded) as a request target without importing the metered door. The door itself, the two new
tests, the meter module, and seven **out-of-tour-path** diagnostic/measurement one-offs are
listed in an explicit, commented allowlist (so the exemption is deliberate, never a default).
Proven to **fail** on an injected offender and pass after removing it.

### Regression run (no network)
`176 passed` across `test_local678` / `609` / `673` / `648` / `674` / `664` / `669` / `655` /
`409` + the two new LOCAL-707 suites; a further `85 passed` across venue-class-routing /
exhibition-discovery / exhibition-not-found / practical-facts / venue-truth.

One intentional behaviour note: `test_local409`'s transport-error case now sees the failure
reason via `serper_post`'s returned body (status 0). `serper_post` surfaces `"ExcType: msg"` in
the **returned** body on a transport error while keeping the **metered** body empty, so the
ledger row is a clean status-0 ($0) record and the LOCAL-409 diagnostic (payload + reason
logged) is preserved.

## 5. Live proof — one real Serper query, my own container, 1 credit

Ran a single real Serper query inside my **own** container (never `-p audioura`, never renamed
`audioura-*`):

```
docker run --rm --name local707-serper-proof \
  -e SERP_API_KEY=… -e PAID_API_LOG=/meterlogs707/paid_api_calls.jsonl \
  -e METER_SERVICE=local707-serper-proof \
  -v /tmp/local707_meterlogs:/meterlogs707 \
  -v $PWD/serper_meter.py:/work707/serper_meter.py:ro \
  -v $PWD/_meter:/opt/meter:ro \
  audioura-tour-generator:latest  python /work707/proof.py
```

The container wrote exactly **one** row to its **own** meter log:

```json
{"ts":"2026-10-16T15:47:23Z","kind":"serper","status":200,"rate_tag":"2026-10-10-r5",
 "service":"local707-serper-proof","caller":"serper_meter.py:159",
 "url":"https://google.serper.dev/search","job":"","usd":0.001}
```

* `service=local707-serper-proof` → written by my container, not the live `audioura` stack.
* `caller=serper_meter.py` → it went through the metered door.
* `kind=serper, status=200, usd=0.001` → one query, correctly costed at the Serper per-query
  rate — **exactly 1 credit** (budget ≤ 5). Container auto-removed (`--rm`).

## 6. Files

**New**
* `serper_meter.py` — the one metered Serper door.
* `tests/test_local707_serper_metered.py`
* `tests/test_local707_serper_scan_guard.py`

**Changed**
* `_meter/paid_api_meter.py` — `record_call()`, thread-local explicit marker, all four network
  wrappers skip double-recording an explicitly-metered request.
* `work_story_searcher.py`, `current_affairs_news.py`, `serper_plus_research.py`,
  `exhibition_checklist.py`, `interpretive_enrichment.py`, `exhibition_site_js.py`,
  `venue_resolver.py`, `dining_corpus_harvester.py`, `preflight.py` — call sites routed through
  `serper_meter.serper_post`.

No DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev` edits.
