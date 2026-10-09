# SUBMISSION — LOCAL-655: Current affairs means NEWS

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-655-current-affairs-news`
**Base:** `subscribed` @ `8e12c846` (verified: `git merge-base --is-ancestor 8e12c846 HEAD` → 0)

## The problem (Michael, 2026-10-09)
Tour 557 ("Walking tour in Boston dedicated to Massachusetts politics and current
affairs") ended with *"we found no verified developments from the past five years."*
Michael: *"How can it be? The current affairs happen every day when the state senate
is in session!"* He is right. **No code in the pipeline searched news at all**
(`grep` for `google.serper.dev/news` → nothing). Research was Wikipedia/Wikidata/
venue-corpus + Gemini grounding on HISTORY questions, so the LOCAL-650 "honest note"
reported a gap we had created ourselves.

## What I built

### 1. `current_affairs_news.py` (new, self-contained)
Mirrors the proven `serper_research.py` shape (deterministic queries → Serper →
shared page-fetch → source-constrained cheap model).

- **`wants_current_affairs(request)`** — intent gate. Phrases ("current affairs",
  "in the news") and political words (politics, election, governor, legislature,
  senate, "state house", …) qualify. A history-only request does **not**.
- **`derive_theme_queries` / `derive_stop_queries`** — theme + per-stop news
  queries. Every stop query is **city-anchored** (`_city_token`): e.g. "Old State
  House" → `"Old State House Boston news"`, `"Old State House politics Boston"`.
- **`_serp_news`** — POSTs the Serper **NEWS** endpoint
  `https://google.serper.dev/news` with `tbs=qdr:m` (past month), **widening to
  `qdr:y`** when the month is empty (`news_for_query`). Keeps title/source/date/
  snippet. Metered automatically at $0.001/query (the network meter prices every
  `serper.dev` host).
- **`_fetch_article`** — the 2–3 best article pages via the existing polite,
  cached, robots-aware `exhibition_checklist._fetch_page`.
- **`compose_news_sentences`** — `gpt-4.1-mini`, constrained to the fetched
  articles: **DATED** ("On October 8, 2026, …"), **attributed** ("according to
  WGBH"), **politically balanced** (each side reported, no side-taking adjective),
  **no invented quotes/numbers**, and a **locale relevance guard** (ignore a
  same-named place elsewhere).
- **`inject_news_into_text`** — additive, idempotent injection of an
  `In recent news:` paragraph into the matching `Stop N:` block (before any
  `Directions:`/`Sources:`), with a "Reported by …" attribution line.
- **`append_honest_note`** — appended **only** when a search **ran** and returned
  nothing usable. The queries and per-query counts are always logged.

### 2. Wiring in `generate_tour_text.py` (museum path byte-identical)
- Current-affairs intent is detected **after `tour_category` converges**
  (post VENUE-CLASS GUARD), **gated to non-museum / non-facility** tours, and
  stashed in a thread-local context.
- The dated-news pass runs at the **single delivery choke point**
  (`_apply_delivery_hours_guard`), after every other guard and **before the
  delivered-file write**, so it reaches every delivery path (fresh/cache/pool/
  by-reference). The wrapper also primes/resets the context from the raw request
  so a museum tour never inherits a prior current-affairs flag.
- A museum / non-current-affairs tour is a **strict no-op** (context flag `False`).
- Kill-switch: `DISABLE_CURRENT_AFFAIRS_NEWS=1`.

### 3. 7-day freshness TTL (DELETE-free, mirrors `venue_preflight`)
- **`stop_pool_store.py`**: additive `news_generated_at TIMESTAMPTZ`; the writer
  stamps `NOW()` for a stop whose narration carries the news marker; `get_pool_stops`
  **ignores** (does not delete) a news-bearing row older than `CA_NEWS_FRESH_DAYS`
  (default 7). A history-only stop (`NULL`) is never aged out.
- **`tour_cache_layer1.py`**: additive `has_news BOOLEAN`; `store_tour` sets it from
  the content; `get_cached_tour` treats a stale (>7d) news tour as a **MISS**.
  History-only tours are unaffected.

## Tests — `test_local655_current_affairs_news.py` (20 tests, all pass, offline)
intent→queries · fixture news response → dated/attributed/balanced sentences ·
empty response → honest note (once, only when searched) · injection additive &
idempotent · city-anchoring · museum no-op (byte-identical) · env kill-switch ·
TTL marker logic · **DB-backed TTL** for pool and cache (ran against local Postgres;
skip cleanly when unreachable; clean up their own rows by exact key).

```
test_local655_current_affairs_news.py       20 passed   EXIT=0
test_local646_walking_regressions.py        13 passed   EXIT=0   (tour-557 regressions)
tests/test_local648_serper_research.py      10 passed   EXIT=0
test_local590_pool_store.py                 18 passed   EXIT=0
test_f4_cache_roundtrip.py                   4 passed   EXIT=0
test_local644_pool_structured.py             5 passed   EXIT=0
test_local607_pooled_coherence.py           21 passed   EXIT=0
test_local643_parity.py                     11 passed   EXIT=0
```

## Live run — own disposable container, spare port 5117
`./run_local655_live.sh` → builds `local655-gen-img`, runs `local655-gen`
(`docker run --rm`, `--network development_default`, `-p 5117:5000`), cache + pool
OFF, task HARD CAP $1.20 via `tests/live_run_meter` with a reserve gate.
**Never** an `audioura-*` container; **never** `docker compose -p audioura`.

**Boston walking, 5 stops (fresh) → `audio_tours` id=618, `is_test=true`:**
- `wants_current_affairs=True`; the news search **ran**: **10 queries, 100 items
  returned, 15 articles fetched, 4 stops received news**. Honest note **not** used
  (news was found) — exactly the ticket's contract.
- Example injected item (dated, attributed, balanced):
  > *In recent news: On October 8, 2026, over 200 people gathered at Boston Common
  > to protest sexual violence in support of Cornell's 'Jane Doe,' criticizing both
  > the accused fraternity members and Cornell University's response, according to
  > Boston.com. On the same day, a rally organized by Mass NOW and Jane Doe Inc.
  > featured speeches from survivors and advocates calling for stronger protections
  > …, as reported by WGBH.*

**Courtauld Gallery museum canary, 3 stops → id=619, `is_test=true`:**
- `In recent news:` count **0**, honest note **False** — strict no-op; the museum
  path is byte-identical.

**Relevance bug found & fixed on the live run:** a bare `"Old State House news"`
query matched an *Arkansas* museum (KARK / Arkansas Times). I fixed it by
city-anchoring every stop query and adding the compose-prompt locale guard, then
cheaply re-validated (serper + `gpt-4.1-mini`, ~1¢): the State House now returns
WBUR / NBC Boston (Healey, the Legislature) and the Old State House returns The
Boston Globe / WCVB (the Boston one) — no out-of-state match.

**Rows / cost / safety:**
- `audio_tours` count: **418 before → 420 after** (two additive `is_test=true`
  rows: 618, 619). **No DELETE.** No GCloud.
- Spend (authoritative `cost_ledger.our_cost_usd` for the run): **$0.893667**
  (`live_run_meter` TOTAL $0.8937 — openai $0.5771, gemini_grounding $0.2170,
  serper $0.0570, gemini_tokens $0.0425, preflight $0.0728). Plus the ~1¢ cheap
  re-validation. **Total task spend ≈ $0.90, under the $1.20 cap.**
- `critique.sh` / `detectors.py` are not checked into this worktree (sibling
  tooling); the `is_test` rows 618/619 are left in place for them to score.

## Files
- `current_affairs_news.py` — the news research + injection module (new)
- `generate_tour_text.py` — intent detection + delivery-time news pass
- `stop_pool_store.py` — `news_generated_at` + 7-day read exclusion
- `tour_cache_layer1.py` — `has_news` + 7-day read exclusion
- `test_local655_current_affairs_news.py` — the test suite (new)
- `run_local655_container.py`, `run_local655_live.sh` — the isolated live harness (new)

## Process
Committed after each step. `git rev-list --count origin/subscribed..HEAD` ≥ 1 at
every step. Did NOT touch DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
`.continuous_dev/STATUS.md`.
