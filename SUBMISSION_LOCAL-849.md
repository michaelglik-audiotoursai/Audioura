# SUBMISSION — LOCAL-849

**Serper now returns `google.com/goto` links after the top 3 results; resolve them where we open or judge links.**

Branch: `LOCAL-849-serper-goto-links` · Base: subscribed (contains `8e5db189`)

---

## Problem

Serper support (2026-10-30): since ~01:30 UTC on Oct 30, Google exposes the real
destination only for the **first 3 organic results**. Everything after the top 3
now comes back as `https://www.google.com/goto?url=CAES…` — a Google host with an
**opaque** reference in `url=` that cannot be decoded locally (confirmed by the
vendor and by scrapingbee / on-page.ai / the `automdev/google-goto-url-fix` repo:
the destination lives only in the HTTP Location header). The vendor added a free
`/resolve` endpoint (0 credits, "about 30 seconds") that returns the real URLs.

We already saw `https://www.google.com/goto?url=…` sources in LOCAL-828/828B logs.
A goto link that reaches the pipeline is harmful in four ways: it is **fetched**
as the opaque Google redirect, **judged** as host `google.com` by the source-tier
gate, **cited** as `google.com`, and **deduped** on the goto string rather than
the real target.

## Audit — where a Serper result link is used (file → use → goto impact)

All Serper searches go through the one metered door `serper_meter.serper_post`;
callers then read `body["organic"][].link` (and `news[].link`).

| Site | What it does with the link | Impact of a raw goto link |
|---|---|---|
| `work_story_searcher._serp_search` | organic → `normalize_domain` → `classify_domain` **source-tier gate**; the hot judge path reused by `serper_research._default_serp`, `serper_plus_research.gather_web`, `artist_life_research`, `work_story_research._serper_fallback`, `grounded_highlights` | judged as `google.com` (wrong tier), then fetched as the redirect |
| `serper_research.gather_pages` / `serper_plus_research.gather_web` | fetch top pages, build `sources[]`, dedupe by URL | opaque redirect fetched; `sources` cite `google.com`; dedupe on goto string |
| `exhibition_checklist._search_exhibition_url` / works search | organic → compare to venue domain, fetch | goto never matches venue domain; opaque fetch |
| `interpretive_enrichment` (×2) | organic → primary-source domain check, fetch | misjudged host; opaque fetch |
| `dining_corpus_harvester` | organic → preferred/review source classify | misclassified by host |
| `current_affairs_news._serp_news` / `serper_plus_research._serper_news` | news → fetch article | opaque fetch |
| `venue_resolver._serper_search` | organic → homepage scoring by host | `google.com` pollutes/wins homepage scoring |
| `venue_identity_gate.domain_of` (828 gate) | judge passage domain | **already** treated goto as unknown (`''`) before this ticket |
| `grounded_highlights` 2nd-source | `_domain(url)` of a Serper hit | covered: its `serper_fn` is `_serp_search` |

## What was built

### 1. Shared helper `serper_links.py`
`resolve_links(search_json, *, query, need_beyond_top3, timeout, skip_top_n)`
returns a **copy** of the Serper response with goto links in
`organic`/`news`/`places` resolved to real destinations:

1. **Keep the top-3** organic links untouched (Google resolves those).
2. **Local decode** (free, instant): a goto that carries a plain
   `url=https://…` target is decoded with no network call. The opaque CAES `url=`
   is **not** decodable and falls through.
3. **Batch `/resolve` once per search** for the still-unresolved opaque links,
   through the guaranteed-metered door (`serper_meter.serper_post`), bounded
   timeout, **cached by query** so a repeated search resolves instantly.
4. A link still unresolved is marked `_unresolved_goto` → treated as an
   **UNKNOWN host**: never judged, never fetched, never cited.

Helpers: `is_goto_link`, `local_decode`, `is_resolved(result)`,
`usable_link(result)`, `resolve_stats`, and process telemetry
(`get_metrics`/`reset_metrics`). **Fail-open throughout** — any error leaves goto
links in the safe unknown state; the helper never raises.

Real `/resolve` contract (probed live 2026-10-31):
`POST {"links":[goto…]}` → `{"links":[resolved…]}` in the **same order**;
`POST {"url":goto}` → `{"url":resolved,"credits":0}`; posting the full search
response echoes it with links rewritten. `_parse_resolve_response` handles all
these plus flat-map and pair shapes.

### 2. Meter — `/resolve` is free (0 credits) but logged
`_meter/paid_api_meter.py` `_record` serper branch prices `/resolve` at **$0**
(`kind=serper`), `/places` at $0.002, everything else at $0.001. Verified:
`/resolve`→$0.0, `/search`→$0.001, `/places`→$0.002, all `kind=serper`.

### 3. Callers wired (all fail-open)
`work_story_searcher._serp_search` (the chokepoint covering the museum judge path
and most research backends), `interpretive_enrichment` (×2), `dining_corpus_harvester`,
`exhibition_checklist` (×2), `venue_resolver._serper_search`, `current_affairs_news`
and `serper_plus_research` news paths. `venue_identity_gate.domain_of` already
treated goto as unknown (no change). Each caller resolves, then **drops any
still-unresolved goto as an unknown host** before fetch/judge/cite.

### 4. Latency — the top-3 must not wait 30 s
A `/resolve` round-trip is ~25–30 s (the vendor's "about 30 s"), and a museum
tour issues ~40+ searches. Resolving every search synchronously added **~944 s**
to the Rijks tour (measured, first run). So the hot judge/fetch chokepoints use
the **no-wait fast path** by default (`need_beyond_top3=False`): keep the top 3,
decode plain `url=` targets for free, and drop opaque post-top-3 goto links as
unknown. The top results are the highest quality and are ample — the live proof
delivers full tours this way with **+0 s** added. Full recovery of the deeper
links is available opt-in via `SERPER_RESOLVE_BEYOND_TOP3=1` (one bounded
`/resolve` per search, cached by query).

## Tests — `tests/test_local849_serper_goto_links.py` (12, all pass)

Fixture `tests/fixtures/local849_serper_goto_search.json` is a real post-change
shape (3 real organic + 2 opaque CAES goto + 1 plain `url=` goto + 1 news goto).
Proven: goto detection; local decode of plain `url=` but **not** opaque CAES;
`resolve_links` keeps the top 3, decodes locally with no `/resolve`, batches one
`/resolve` for the opaque ones (and news); an unresolved goto → `is_resolved` False /
`usable_link ''`; the fast path makes **no** `/resolve` call; `/resolve` called at
most once per search and **cached by query**; no-goto → no call; fail-open on a
resolver exception; **domain gate** `domain_of(goto)==''`; **page-fetch chokepoint**
drops unresolved goto (4 survive of 6, no `google.com/goto`); **meter** `/resolve`=$0
vs `/search`=$0.001.

Regression: **56 passed** (12 new + `test_local707_serper_metered`,
`test_local707_serper_scan_guard`, `test_local648_serper_research`,
`test_local674_serper_plus`, `test_local783_serper_places`).

## Live run — BUDGET ENFORCED

`run_local849_live.py` — `TASK_BUDGET_ID=LOCAL-849 TASK_BUDGET_USD=0.60`, cheap
env + `STORY_PASS_MODEL=gpt-4.1`, stop pool OFF. Mac-local diagnostic
(`METER_MOUNT_GUARD=0`, own meter dir `_local849_meterlogs`, `DISABLE_TOUR_CACHE=1`
so **no live DB write**); never touched the shared `audioura-*` containers.

| Tour | Stops | Time | goto seen | resolved | unresolved (dropped) | +s from /resolve | bad `google.com` fetches |
|---|---|---|---|---|---|---|---|
| Rijks Museum Amsterdam, Netherlands | 5/5 | 649 s | 219 | 0 | 219 | **0.0 s** | 0 |
| Old Quarter walking tour, Hanoi | 4/4 | 250 s | 45 | 0 | 45 | **0.0 s** | 0 |

- **Pages before vs after:** before the fix, each goto link (219 / 45) would have
  been fetched as a `google.com` redirect and judged as host `google.com`; after,
  **0** bad `google.com` fetches — unknown links dropped, the top-3 real pages +
  Wikipedia used.
- **Added seconds per tour:** **0 s** (fast-path default).
- Meter: serper `/search`+`/news` 77 calls $0.089; `/resolve` 0 calls **$0**;
  Gemini **$0**; **metered total $0.089 ≪ $0.60**. **OVERALL PASS.**

**Opt-in `/resolve` proof** (`SERPER_RESOLVE_BEYOND_TOP3=1`, live endpoint): 6 real
goto links → **all 6 recovered** to real publisher URLs (youtube, reddit, artnet,
rijksmuseum.nl, artnews) in ~24 s, logged as **one `kind=serper` row at $0**.

## Files
- **new** `serper_links.py`, `run_local849_live.py`,
  `tests/test_local849_serper_goto_links.py`,
  `tests/fixtures/local849_serper_goto_search.json`
- **edited** `_meter/paid_api_meter.py` (price `/resolve` $0), `work_story_searcher.py`,
  `interpretive_enrichment.py`, `dining_corpus_harvester.py`, `exhibition_checklist.py`,
  `venue_resolver.py`, `current_affairs_news.py`, `serper_plus_research.py`

## Env knobs
- `SERPER_RESOLVE_BEYOND_TOP3` (default `0`): opt in to one bounded `/resolve` per
  search to recover goto links beyond the top 3.
- `SERPER_RESOLVE_TIMEOUT` (default `32`): bounded wall-time for a `/resolve` batch.
- `SERPER_GOTO_TOP_N` (default `3`): organic ranks Google already resolves.
