# LOCAL-565 — Serper vs Gemini: ask Serper + a cheap reader Gemini's exact questions, score both

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-565-serper-research
**Base:** subscribed = f5bc845 (`git merge-base --is-ancestor f5bc845 HEAD` → 0, OK)

Michael's approved test (2026-10-02). Step 1 (LOCAL-563/563B) recorded 157 grounded
Gemini questions across 10 tours × 2 runs, the noise floor, the per-answer facts with
source tiers, and the answer-key check. This task builds `serper_with_sources`, replays
those 157 questions through it (Serper-only; Gemini is already recorded), and scores both
engines the same way.

Guardrails honoured: no GCloud deploy; default `RESEARCH_PROVIDER` stays `gemini`; the
replay is Serper-only so Gemini spend is ZERO; OpenAI cap $8 (stop & report if reached);
DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md / .continuous_dev/STATUS.md untouched.

---

## Step 1 — fixtures brought onto branch (committed)

`git checkout origin/LOCAL-563-gemini-baseline -- tests/fixtures/local563`

- `gemini_questions.jsonl` — 157 lines. Each: `{tour, run, call_site, purpose, grounded,
  charged, model, prompt, response, grounding_sources[], grounding_queries[], ts, wall_s}`.
  `prompt` is the ORIGINAL prompt to replay; `response` is Gemini's recorded answer.
- `gemini_facts.json` — `{_about, per_tour{...}, facts[]}`. Each fact carries
  `{tour, run, call_site, fact, cited_domains[], tiers[], wikipedia_only, discovery_tier}`.
- `SERPER_AB_ANSWER_KEY.json` — per-tour `must` / `must_not` / `unverified` + `sources`,
  plus `_reliability_tiers` (high / medium / discovery / never_alone) and `_principle`
  (do not rely on Wikipedia alone). Keyed: sail_loft, buttermilk, chart_house, sycamore,
  la_maree, logan. Not keyed (recall + invented only): our_lady, lascaris, riviera_bike,
  faneuil.
- `baseline_summary.json` — per-tour run1/run2, totals, and the 563B `noise_floor`
  (per-metric per-tour abs delta + mean/max for story_defect_count, named_people,
  stops_delivered, gate_deleted_total).

LOCAL-564 context: Gemini's baseline wrongly reported **Chart House** (Weehawken NJ
closure) and **Buttermilk** (BarLola closure) as closed. **la_maree** is genuinely closed
(must_not = open). **sycamore** must be OPEN (a "closed" verdict is an automatic FAIL — the
D544 bug).

## Step 2 — code studied

**`gemini_with_sources(prompt)` return shape** (story_leads.py), which `serper_with_sources`
must match:

```
{'text': str,
 'sources':  [{'domain': str, 'url': str}],      # chunks: domain + URI, de-duped, order kept
 'supports': [{'text': str, 'sources': [{...}]}], # which sentence came from which source(s)
 'queries':  [str],                               # the web queries used
 'error':    str}
```

**LOCAL-562 cost accumulator** (`cost_accumulator.py`): four fixed buckets — `llm`,
`grounding`, `search`, `tts`. `tour_scope()` is a context manager; within it,
`add_search_queries(n)` adds Serper cost (`search` key) and the `openai_cost_wrapper`
monkey-patch auto-feeds `add_llm_usage` (`llm` key) for every OpenAI chat call on the wire.
So inside a `tour_scope`, the reader's gpt-4o-mini tokens are counted automatically; I only
have to call `add_search_queries` for each Serper query.

- `cost_rates.SERPER_COST_PER_QUERY = $0.001`; `GROUNDING_COST_PER_REQUEST = $0.035`.
- Serper: `POST https://google.serper.dev/search`, header `X-API-KEY`, body `{"q", "num"}`,
  returns `organic[]` with `title/link/snippet` (see `work_story_searcher._serp_search`).
- Page text: `robust_text_extractor.extract_clean_text(html, max_length)` (BeautifulSoup,
  encoding-safe, strips script/style, trims to length).

Keys present in `.env`: OPENAI_API_KEY, SERP_API_KEY, GEMINI_API_KEY (GEMINI not used here).

## Step 3 — `serper_with_sources(prompt)` built (behind RESEARCH_PROVIDER)

Added to `story_leads.py` (committed), with `research_with_sources(prompt)` as the
engine-agnostic dispatcher: `RESEARCH_PROVIDER=serper` → Serper engine;
`gemini` / unset / unknown → `gemini_with_sources` (default unchanged, fail-safe).

Pipeline, matching the gemini_with_sources shape exactly:

1. **Queries** — `_derive_queries` asks gpt-4o-mini for 1–3 web queries, logged; falls
   back to a trimmed prompt line if the query model is down (engine still searches).
2. **Search** — one Serper query per derived query (`add_search_queries(1)` each →
   `search` bucket), top-10 organic with snippets; candidates de-duplicated by URL then
   by **domain** so the reader sees DISTINCT sources (discovery over echo); top 3–5
   fetched with `requests.get` (12s timeout) and cleaned via `extract_clean_text`, then
   `_trim_to_relevant` keeps the passage window overlapping the prompt/snippet. Pages that
   fail to fetch fall back to the Serper snippet so a source is never lost.
3. **Reader** — gpt-4o-mini answers the ORIGINAL prompt using ONLY the numbered sources,
   every fact tagged `[n]`. The response is split into sentences; **any sentence with no
   `[n]` marker is dropped** (JSON-object answers keep the raw block iff it carries at
   least one marker). `supports` records which source each kept sentence points at.
4. **Cost** — Serper queries → `search` bucket directly; reader + query-model tokens →
   `llm` bucket, auto-counted by `openai_cost_wrapper` inside a `tour_scope`. No Gemini
   call, no grounding charge.

Verified live on one real prompt (Boston Sail Loft) inside a `tour_scope`: 3 queries
logged, 5 distinct-domain sources (incl. official `thebostonsailloft.com`), output shape =
`{text, sources, supports, queries, error}`, unsourced sentences dropped, cost
`search=$0.003 (3 q) + llm=$0.00015` ≈ **$0.0032/question** → ~$0.50 projected for the
157-question replay (well under the $8 cap).

Unit test `tests/test_local565_serper_with_sources.py` (offline, mocked search/fetch/reader),
5 tests pass: shape parity, unsourced-sentence drop, cost lands in `search` bucket, no-key
error shape, and default provider = gemini.

## Step 4 — replay: 157 recorded questions through Serper (committed)

Harness `tests/fixtures/local565_replay.py`: reads all 157 lines of
`gemini_questions.jsonl`, sets `RESEARCH_PROVIDER=serper`, installs
`openai_cost_wrapper` + `cost_accumulator.install_executor_context_propagation()`,
and runs each ORIGINAL prompt through `serper_with_sources` in a bounded
`ThreadPoolExecutor` (6 workers). Each question runs in its OWN `tour_scope`, so
its exact Serper + reader cost is captured; cumulative OpenAI (`llm`) spend is
checked against the **$8 cap** on every completion (hard stop if reached).

Output `tests/fixtures/local565/serper_answers.jsonl` — one line per question:
`{idx, tour, run, call_site, purpose, prompt, serper{text,sources,supports,queries,error},
latency_s, cost{llm,search,total}, running_openai_usd}`.

**Replay result (all 157):**

| metric | value |
|---|---|
| questions replayed | 157 / 157 |
| OpenAI (llm) spend | **$0.0494** (cap $8 — never approached) |
| Serper (search) spend | $0.4710 |
| total cost | **$0.5204** |
| avg latency / question | 7.3 s |
| stopped at cap? | no |

**Answer status:** 107 answered with sourced content · 34 honest "NO RELIABLE
INFORMATION" (reader found nothing a source backs — the correct empty) · 16 "no
sourced sentences" (reader wrote prose but every sentence lacked a `[n]` marker, so
all dropped). The empties cluster on **lascaris** (79 questions, only 29 answered):
that tour is dominated by obscure/likely-spurious items (e.g. a "Violes gambe by
William Turner" at Palais Lascaris) for which Serper legitimately surfaces nothing
reliable — itself a discovery-vs-recall signal the scorer will quantify. Answered
questions carried 5.0 distinct-domain sources on average.

Two engine robustness fixes were made during the dry run and are covered by the
unit test: (a) `_derive_queries` now fences the request as inert data and rejects
JSON/code-fence echoes, because restaurant-practicals prompts embed "Return ONLY
JSON" and were hijacking the query model; (b) prompts that demand JSON use a JSON
reader variant that returns the required object plus a `_sources` index array
(attribution without corrupting the format), and the explicit "NO RELIABLE
INFORMATION" sentinel is recorded distinctly from dropped-prose.


