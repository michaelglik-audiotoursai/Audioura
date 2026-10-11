# SUBMISSION — LOCAL-674

**Replace Gemini web-search research on WALKING tours with a cheaper path, without losing quality.**

Agent: Mac Mini Kiro · Branch: `LOCAL-674-walking-research` · Base: `subscribed` @ `62e37a0f`

---

## Why

Gemini web-search fees are 81% of the bill — ≈ **$0.053 per grounded request**,
one request per stop (`.continuous_dev/PRICE_CARD.md` r5). Museums already moved to
the Serper research backend (D645, `CHEAP_ARM_CATEGORIES=museum`), but on WALKING
tours that same backend lost ~2 Kiro points (Boston: Gemini 7.5 v11; Serper 5.0,
tours 655/656; `COST_TIME_RESULTS_2026-10-09.md` "2026-10-10"): stops fell back to
filler ("$26.5 million … 1969") and repeated stories, so **walking stayed on
Gemini**. LOCAL-674 cuts that cost on walking without the quality loss.

**Root cause of the Serper loss on walking.** The LOCAL-648 backend was built for
museum OBJECTS: it keys queries on a work's `canonical_title`/`artist`/
`credit_line`, and museums carry a rich Wikidata catalogue + a venue corpus. A
walking stop is a PLACE (a building, a square, a monument) with thin object
context, so the queries fall back to generic content words and the top Serper
results are SEO/listing pages (tripadvisor, "15 best things to do"). The problem
was the RESEARCH, not the writing model.

---

## What this delivers

A new research backend **`serper_plus`** (`serper_plus_research.py`) for walking
stops, selected per-tour by a flag, plus the GEMINI_PER_VENUE lever kept as an
alternative arm. `serper_plus` answers the SAME per-stop story-lead question that
`gemini_with_sources(grounded=True)` answers and returns the SAME shape
(`{text, sources, supports, queries, error}`), so it is a drop-in. In order,
cheapest-and-highest-signal first:

1. **Wikipedia FIRST (free).** Resolve the stop to its Wikidata item
   (`wbsearchentities`), read the FULL English article extract AND — for a
   non-English locale only (Old Nice → `fr`, HCMC → `vi`) — the local-language
   article via the item's sitelinks, through the Wikipedia action API
   (`prop=extracts&explaintext`). A place's own Wikipedia article is dense with
   dated, named, consequential history. All Wikimedia GETs reuse the proven
   `venue_resolver._request_with_backoff` (LOCAL-637: 429/5xx retry, Retry-After)
   — a first probe hit Wikidata 429s hard under the concurrent pipeline, and the
   backoff is what makes the free path reliable.
2. **Better web pages.** Serper top results → fetch the best 3, SKIPPING
   SEO/listing/UGC domains (the `exhibition_checklist` blocklist) and preferring
   the stop's own `… official site` page.
3. **News pass, only where current affairs apply.** A Serper `/news` query is
   issued ONLY when the question/context signals recent/ongoing matters
   (`recent`, `renovation`, `2025…`; LOCAL-655), so a historic building does not
   pay for news it will not use.
4. **One extractor** over everything gathered: `gpt-4.1-mini` by default,
   `gpt-4.1` when `SERPER_PLUS_EXTRACTOR=gpt-4.1`. Constrained to the gathered
   text — no parametric memory, every sentence cites its source `[n]`.

Every PAID call (Serper queries, the OpenAI completion) is metered through
`_meter/paid_api_meter.py`; Wikipedia/Wikidata are free.

---

## The flag (deliverable 4)

`WALKING_RESEARCH = serper_plus | gemini_per_venue | gemini` — **default
`gemini`**, routed in `story_leads.research_with_sources`:

| value | effect on a WALKING tour |
|---|---|
| `gemini` (default) | unchanged grounded Gemini, one request per stop |
| `serper_plus` | the LOCAL-674 backend above |
| `gemini_per_venue` | keep Gemini but ONE grounded request per VENUE/tour (LOCAL-645), per-stop narrate ungrounded on that material |

It is **category-aware and default-safe**: it only takes effect when the tour's
category is `walking` (read from the `cheap_arm` contextvar); any other category
keeps the normal `RESEARCH_BACKEND`/cheap-arm routing. Unset or `gemini` → byte-
for-byte the old behaviour. `WALKING_RESEARCH=gemini_per_venue` also turns on the
LOCAL-645 per-venue pass in `story_production_loop` (OR'd with `GEMINI_PER_VENUE=1`).
**LEAD decides whether to switch it on.**

---

## Measure first (deliverable 1) — research-ONLY, no narration

`measure_local674_walking.py` reconstructs the EXACT per-stop story-lead question
the pipeline sends (`story_query.compile_for_seed` on a PLACE matrix) for 15 real
walking stops across 3 requests — Boston political (the 557 stops), the Freedom
Trail, and Old Nice, France — answers each under every backend, and scores the
evidence with a cheap judge (distinct **dated + named** facts; a consequence
present; sources; filler), with per-arm $ read from the meter. The GEMINI_PER_VENUE
arm is measured by `measure_local674_pervenue.py` (one grounded request per tour,
split per stop).

**Combined 15 walking stops (r5 rates, rate_tag `2026-10-10-r5`):**

| arm | mean evidence | dated+named facts | consequence | filler | $/stop | grounded reqs |
|---|---|---|---|---|---|---|
| gemini (per-stop, baseline) | 5.67 | 3.67 | 15/15 | 0/15 | $0.0540 | 15 |
| serper (LOCAL-648) | 6.20 | 4.47 | 13/15 | 2/15 | $0.0045 | 0 |
| gemini_per_venue (LOCAL-645) | 6.07 | 4.60 | 11/15 | 0/15 | $0.0115 | 3 (1/tour) |
| **serper_plus (LOCAL-674)** | **7.87** | **5.87** | **15/15** | 1/15 | **$0.0038** | **0** |

`serper_plus` is the WINNER: **highest evidence (≥ Gemini) at the lowest $** — 14×
cheaper than per-stop Gemini, also the fastest, zero grounded Gemini. It fixes the
documented failure: **Boston City Hall** evidence went Gemini 3 (one dated+named
fact) → **serper_plus 8** (six). Research-only runs cost ≈ $0.93 total.

Artifacts: `LOCAL674_walking_boston.json`, `LOCAL674_walking_rest.json`,
`LOCAL674_pervenue_measurement.json`.

---

## One live A/B (deliverable 3)

`run_local674_live.sh` built `Dockerfile.generator` from this worktree and
launched TWO disposable containers **at the same moment** — `local674-gemini` and
`local674-serper_plus`, `docker run --rm`, spare ports 5191/5192, network
`development_default`. One fresh 5-stop Boston walking tour each; the ONLY varying
knob was `WALKING_RESEARCH` (everything else equal: `CHEAP_ARM_CATEGORIES=museum`
so museum envs do not bleed into walking, `FAST_PIPELINE`, cache+pool OFF, gpt-4.1
narration in both). No `audioura-*` container was touched; rows are additive
`is_test` only.

| arm | Kiro (`critique.sh <id> 5`) | grounded Gemini requests | tour_total $ (r5) | wall s | tour id |
|---|---|---|---|---|---|
| gemini (baseline) | **6.5/10** (critique 681) | 6 (7 queries) | $0.6536 | 400.9 | 681 |
| **serper_plus** | **6.5/10** (critique 680) | **0** | **$0.3063** | **322.0** | 680 |

**Detectors (both tours):** 5 delivered stops, identical stop list (Old State
House · Faneuil Hall · Boston City Hall · Parkman Bandstand · Massachusetts State
House), 0 missing directions, 0 run-on headers. Each arm had ONE dropped-subject
sentence — a pre-existing sentence-assembly defect present in BOTH arms, not caused
by the research backend (both critiques flag it, plus a shared news-injection and
unspoken-hours defect). 

**Conclusion:** serper_plus matches Gemini quality (6.5 = 6.5) on a live walking
tour at **~half the dollar cost, with zero grounded Gemini requests, and 80s
faster**. The research-only evidence advantage (7.87 vs 5.67) is partly absorbed
by downstream gates/ranker that both arms share; the cost and grounded-request
win is unambiguous.

---

## Spend (from `paid_api_calls`, r5)

Checked before each paid step. Whole-task total: **$2.06 of the $2.50 cap**
(Gemini $1.33, OpenAI $0.57, Serper $0.16). Research-only harness ≈ $0.93 across
all four arms; the GEMINI_PER_VENUE arm ≈ $0.18; the live A/B ≈ $0.96 (gemini
tour $0.65 + serper_plus tour $0.31). `critique.sh` uses the local `kiro-cli`
(no paid API). No further paid steps are needed.

---

## Safety / process

- Base verified: `git merge-base --is-ancestor 62e37a0f HEAD` exits 0 (the worktree
  started one commit behind at `09ca36b2`; the branch was reset onto the real
  `subscribed` head `62e37a0f` before any work).
- Default behaviour is **byte-for-byte unchanged** with the flag unset (proven by
  the router test and the untouched default path).
- Live test used OWN disposable containers (`--rm`, `local674-*`), never
  `docker compose -p audioura`, never renamed/replaced an `audioura-*` container
  (13 still up afterwards). Rows additive `is_test` only (ids 680, 681). No DELETE,
  no GCloud.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.

## Tests

- `tests/test_local674_serper_plus.py` — 8 offline tests (no network/cost):
  place-query derivation, news trigger, local-language gating, SEO/UGC drop,
  output shape + source dedup, news-pass source add, honest-empty, and the
  WALKING_RESEARCH router dispatch + default safety.
- No regression: `test_local648_serper_research.py` (10) and
  `test_local645_gemini_per_venue.py` (10) pass; `test_local664_cheap_arm_by_category.py`
  passes.

## Files

- `serper_plus_research.py` — the backend (new).
- `story_leads.py` — `WALKING_RESEARCH` router + `walking_research_backend()` /
  `walking_gemini_per_venue_selected()`.
- `story_production_loop.py` — per-venue pass enabled by `GEMINI_PER_VENUE=1` OR
  `WALKING_RESEARCH=gemini_per_venue`.
- `measure_local674_walking.py`, `measure_local674_pervenue.py` — research-only harnesses.
- `run_local674_container.py`, `run_local674_live.sh` — the live A/B.
- `tests/test_local674_serper_plus.py` — offline tests.

## Recommendation

Switch walking to `serper_plus`: equal Kiro quality on the live A/B, higher
research-evidence in the measure-first harness, ~half the tour cost, zero grounded
Gemini requests, and faster. The pre-existing news-injection and dropped-subject
sentence defects seen in both arms are separate tickets (not research-backend
caused).
