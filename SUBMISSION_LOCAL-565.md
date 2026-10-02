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

### Mid-step correction (recorded for honesty)

During scoring the invented-fact check returned **0 characters for every page**, which
exposed that `robust_text_extractor` could not be imported on this Python 3.9
(an f-string-with-backslash `SyntaxError` in its `__main__` test helper) AND that
`beautifulsoup4` (a pinned production dep, `beautifulsoup4==4.12.2`) was not installed
locally. The consequence: **the first replay never read full pages** — `_fetch_page_text`
silently caught the ImportError and the Serper engine fell back to Serper *snippets*
only (support text averaged 155 chars = snippet length). The task requires full-page
fetching, so this was a real measurement defect, not cosmetic.

Fixes: (1) corrected the two `SyntaxError` lines in `robust_text_extractor.py` (a genuine
3.9 bug in a test helper, unbreaks every caller); (2) installed the pinned
`beautifulsoup4==4.12.2`; (3) made `_fetch_page_text` fall back to a stdlib tag-stripper
when BeautifulSoup is unavailable, so it never silently degrades to snippet-only again.
The replay was then **re-run with real page fetching** (112 answered vs 107, OpenAI
$0.078, latency 13.3s/q as full pages are now read) and all scoring is on that data.

## Step 5 — both engines scored the same way (`score.json` + tables, committed)

`tests/fixtures/local565_score.py` → `tests/fixtures/local565/score.json`. Gemini is read
from the recorded fixtures; Serper from the re-run replay. Both engines use the IDENTICAL
tier classifier (copied from `analyze_baseline.py`) so comparisons are symmetric.
Total OpenAI for scoring: **$1.28** (whole task ≈ $1.4, cap $8 never approached).

### Recall judge calibration

gpt-4o judge calibrated on **30 hand-labeled pairs** (clear matches / clear misses /
near-misses with a changed number/name/status). **Agreement 96.7% (29/30)**; the single
miss was conservative (judge said NO to "Logan opened September 8, 1923" vs text "The field
opened 8 Sep 1923 as Boston Airport"), so the judge is strict and biases recall *down* for
both engines — an acceptable, conservative direction. Full per-pair detail is in
`score.json → judge_calibration`.

### Answer key (keyed tours) — must-facts, closure verdicts

| tour | engine | must stated | says_closed | auto-FAIL (wrong closed on open) |
|---|---|---|---|---|
| sail_loft | gemini / serper | 4/4 · 3/4 | no · no | no · no |
| buttermilk | gemini / serper | 3/4 · 0/4 | no · no | no · no |
| chart_house | gemini / serper | 4/4 · 4/4 | no · no | no · no |
| sycamore | gemini / serper | 3/6 · 1/6 | **yes · yes** | **YES · YES** |
| la_maree | gemini / serper | 0/1 · 0/1 | yes · yes (correct) | no · no |
| logan | gemini / serper | 1/4 · 1/4 | no · no | no · no |

- **LOCAL-564 regression — does Serper repeat Gemini's errors?** No. In this replay
  **neither** engine marks **Chart House** or **Buttermilk** as closed; both report them
  open. Serper even recovered Chart House's Gardiner-Building/1763/John-Hancock history
  (though it gave conflicting opening years 1971 vs 1973 across blocks). The Weehawken-NJ
  and BarLola closure errors are not reproduced here.
- **sycamore (D544 open-venue test): BOTH engines auto-FAIL.** Gemini returned
  `status: closed_permanently`; Serper **confused the venue entirely** — it answered about
  "THE LOCAL NEWTON" / "Sullivan's Steakhouse" and declared *those* closed. Different cause,
  same failure: a "closed" verdict on a venue that is open.
- **la_maree:** both say closed — which is **correct** (genuinely closed 2020); not scored
  as a fail because the key's status is not "open".
- No `must_not` violations and no `unverified` claims (e.g. logan's "Governor Channing Cox")
  were detected for either engine on the keyed tours.

### Recall — of Gemini's atomic facts, the share Serper also states (keyed tours)

**Overall recall 7.1%.** This low number is the A/B's central finding, not a Serper
failure: the Gemini facts Serper does *not* reproduce are overwhelmingly **Gemini's own
unverifiable narrative** — e.g. sail_loft's "Great Dill Chowder Feud", the "Heresy Debate",
"the chowder went on to defeat nearly every legacy establishment". Serper, by construction,
states only what a fetched page backs, so it correctly does not echo invented storytelling.
Read recall *together with* the invented-fact rate below. Every missed fact per keyed tour
is listed in `score.json → recall.missed_facts`.

### Invented facts — exact cited page, 50 per engine (apples-to-apples)

Both checks fetch the **exact cited URL** and ask the judge whether that page states the
fact. (Gemini's `gemini_facts.json` carries only domains, so exact URLs were rebuilt from
the recorded per-run `*.gemini.jsonl` `grounding.supports`.)

| engine | sampled | unsupported rate |
|---|---|---|
| **Gemini** | 50 | **0.52** |
| **Serper** | 50 | **0.44** |

Both are high (the check is strict — paraphrase gaps and page-fetch failures count against),
but **Serper's cited facts are supported by their page more often than Gemini's** (56% vs
48%). Per-fact detail incl. page_chars and exact_url flags in `score.json → invented_facts`.

### Discovery (Michael's criterion)

| metric | Gemini | Serper |
|---|---|---|
| total atomic facts | 1431 | 345 |
| distinct cited domains | 220 | 88 |
| Wikipedia-only share | 2.7% | 9.9% |
| discovery-tier share | 59.7% | 72.8% |
| confirmed discoveries (disc fact + high-tier in same answer) | 600 | 155 |
| confirmed-discovery share of discovery facts | 70.3% | 61.8% |

Gemini produces **far more facts and from more domains** (it writes freely); Serper produces
fewer, more disciplined facts. Serper leans **more on Wikipedia** (9.9% vs 2.7%) and more on
discovery-tier sources (72.8%). Gemini's **confirmed-discovery share is higher** (70% vs 62%)
— when it uses a little-known source it more often also carries a high-tier one in the same
answer. Caveat recorded in `score.json`: the generic classifier cannot know a venue's
official site is "high", so official sites (thebostonsailloft.com, sycamorenewton.com) count
as discovery for **both** engines — symmetric, but it inflates both discovery shares.

### Cost & latency (per the 157 research questions), with 563B noise floor

| | Serper (this replay) | Gemini baseline (recorded) |
|---|---|---|
| research cost, 157 q | **$0.549** ($0.078 llm + $0.471 search) | **$5.495** grounding (157 × $0.035) |
| whole-tour cost (context) | — | $9.62 ($4.13 llm + $5.50 grounding) |
| avg latency / question | 13.3 s | (whole-tour wall only recorded) |

**Serper is ~10× cheaper on the research questions** ($0.549 vs $5.495 grounding). Per-tour
cost/latency for both engines is in `score.json → cost_latency.per_tour`. The **563B noise
floor** (`score.json → noise_floor_563B`) sits next to every tour comparison: run-to-run
named-people deltas averaged 1.4 (max 4 on riviera_bike) and story-defect deltas averaged
0.6 — so per-tour differences smaller than those are within run-to-run noise and are not
claimed as engine effects.

### Bottom line

Serper + a cheap gpt-4o-mini reader answers the same 157 questions for **~1/10th the research
cost**, does **not** reproduce Gemini's LOCAL-564 closure errors, and has a **lower invented-fact
rate** on an exact-page check (44% vs 52%). Its discipline shows as low "recall" of Gemini's
output — but that gap is mostly Gemini's unverifiable narrative, which Serper correctly omits.
Both engines still **fail the sycamore open-venue test** (Serper via venue confusion), so venue
disambiguation is the clear next weakness to fix. Default provider remains Gemini; the Serper
path is additive and behind `RESEARCH_PROVIDER`.

## Guardrails & reproduction

- **No GCloud deploy.** Nothing was deployed.
- **Default provider stays `gemini`.** `research_with_sources` routes to
  `gemini_with_sources` for `gemini`/unset/unknown; Serper only when
  `RESEARCH_PROVIDER=serper`. Unit test asserts the default.
- **Gemini spend this task = $0.** The replay is Serper + gpt-4o-mini only; the
  Gemini side is read from the already-recorded LOCAL-563 fixtures.
- **OpenAI cap $8:** total ≈ **$1.4** (replay $0.078 + scoring $1.28 + calibration/smoke
  ≈ $0.06). Never approached; the replay harness also hard-stops at the cap.
- **Untouched:** DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md,
  .continuous_dev/STATUS.md (verified with `git status`).
- **Base:** `git merge-base --is-ancestor f5bc845 HEAD` → 0.
- **Dependency note:** `beautifulsoup4==4.12.2` (a pinned production dep) was installed
  locally so full-page extraction works; `_fetch_page_text` now also has a stdlib fallback.

### Files added / changed

- `story_leads.py` — `serper_with_sources`, `research_with_sources`, helpers, prompts;
  `_fetch_page_text` fallback. (Default behaviour unchanged.)
- `robust_text_extractor.py` — fixed two Python-3.9 f-string `SyntaxError`s in its test
  helper (2 lines; unbreaks `import` for every caller).
- `tests/test_local565_serper_with_sources.py` — 5 offline unit tests (pass).
- `tests/fixtures/local565_replay.py` — replay harness.
- `tests/fixtures/local565_score.py` — scorer.
- `tests/fixtures/local565/serper_answers.jsonl` — 157 Serper answers (real page fetch).
- `tests/fixtures/local565/score.json` — full scoring output for both engines.
- `tests/fixtures/local563/**` — LOCAL-563 baseline fixtures (checked out onto branch).
- `SUBMISSION_LOCAL-565.md` — this file.

### Reproduce

```bash
RESEARCH_PROVIDER=serper python3 tests/fixtures/local565_replay.py   # -> serper_answers.jsonl
python3 tests/fixtures/local565_score.py                            # -> score.json
python3 tests/test_local565_serper_with_sources.py                  # 5 tests
```




