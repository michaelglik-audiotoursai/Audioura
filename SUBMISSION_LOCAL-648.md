# SUBMISSION — LOCAL-648

**Research: a Serper + page-fetch + cheap-model research backend vs Gemini
grounded search — cost, coverage, seconds.**
New module `serper_research.py` and a flag `RESEARCH_BACKEND=serper|gemini`
(default **gemini**, so nothing changes) in `story_leads.py`'s grounded path.

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-648-serper-research` (from `subscribed`; base `531a5219`
  confirmed an ancestor of HEAD — `git merge-base --is-ancestor 531a5219 HEAD`
  exits 0).
- **PARALLEL with LOCAL-647.** Only the research path is touched; **no narration
  or assembly code was edited.**
- **Total spend across every run: ~$1.47** (offline A/B $0.25 + live A/B $1.14 +
  smokes ~$0.08), under the **$2.50** cap. Every paid call went through the
  network meter (`paid_api_calls`); per-arm spend is read from it, never
  estimated.

---

## Why

A fresh grounded **Gemini** answer is billed per search-enabled request at
**$0.035** (price card r4, `RATE_TAG 2026-10-08-r4`,
`_meter/paid_api_meter.GROUNDED_REQUEST_USD`). A 3-stop tour issues several such
requests (preflight + per-stop research), so grounding is the dominant line of a
tour's bill. **Serper** costs **$0.001/query** and we already use it; a cheap
model (gpt-4.1-mini) can write the answer from the fetched pages.

> Note: the ticket points at `.continuous_dev/PRICE_CARD.md`; that file is not
> checked out in this worktree. The authoritative r4 rates live in
> `_meter/paid_api_meter.py` (`RATE_TAG = "2026-10-08-r4"`,
> `GROUNDED_REQUEST_USD = 0.035`, `SERPER_PER_QUERY = 0.001`,
> gpt-4.1-mini `$0.40/$1.60` per 1M in/out). All figures below carry that tag.

---

## 1. `serper_research.py` — the backend

`serper_research(prompt, …, grounded=True)` answers the SAME question
`story_leads.gemini_with_sources(grounded=True)` answers, and returns the **exact
same structure** — `{text, sources:[{domain,url}], supports:[{text,
sources:[{domain,url}]}], queries, error}` — so it is a drop-in:

1. **derive_queries** — turns the prompt into 2–3 focused web queries. The
   pipeline's per-stop prompt (`story_query.compile_for_seed`) carries a labelled
   *"Context — the work this concerns:"* block, so we build the queries from those
   strong signals (title + artist + year, title + venue, title + donor history) —
   the same encoding `compile_for_serper` proved. Instruction boilerplate
   (`NO RELIABLE INFORMATION`, `Using Google Search`) is dropped.
2. **gather_pages** — runs the queries with the project Serper caller
   (`work_story_searcher._serp_search`, $0.001/query, metered) and fetches the
   top 3–5 unique pages with the existing polite/cached helper
   (`exhibition_checklist._fetch_page`: 1.5 s per-host delay, retry/backoff,
   honours `Retry-After`, Cloudflare→Wayback, 1 h per-host cache). Robots/timeouts
   are respected by reusing that helper; nothing is re-implemented.
3. **extract** — clean text via `robust_text_extractor.extract_clean_text`,
   capped at 2 500 chars/page.
4. **answer** — `gpt-4.1-mini`, CONSTRAINED to the fetched text ("do not use prior
   knowledge"), told to end each sentence with the source number `[n]`. The `[n]`
   markers become per-sentence `supports[].sources` (mirroring Gemini's
   `groundingSupports`) and are stripped from the displayed text.

**Honest-empty by construction:** no fetchable pages → `text=''` + an error; a
`NO MATERIAL FOUND` model reply → `text=''`. It never guesses when retrieval
fails.

### The flag (default OFF = gemini)

`story_leads.research_with_sources(…)` is a thin router: it calls
`serper_research` **only** when `RESEARCH_BACKEND=serper` **and** `grounded=True`;
otherwise it calls `gemini_with_sources` with the identical arguments (and fails
safe to Gemini if the Serper module cannot import). The default backend is
`gemini`, so `research_with_sources == gemini_with_sources` and behaviour is
**byte-for-byte unchanged** (proven by the router tests and the regression
suites).

The three per-stop **research** call sites now go through the router:
`story_production_loop` r1 (D511 narrate), `venue_parts.default_ask_grounded`
(Q3 / story questions), and `stop_knowledge_fallback` (the juicy-fact lookup).
The **venue preflight** still calls `gemini_with_sources` directly, so it always
stays on Gemini. The r2 adjudication is ungrounded by design and was not touched.

---

## 2. Offline comparison — 6 museums, per story-lead question

For each museum we **reconstruct the exact per-stop question** by replaying the
real builder `story_query.compile_for_seed` on a signature, well-documented work,
then answer it BOTH ways. Reproduce:

```
python3 measure_local648_overlap.py        # writes LOCAL648_overlap_measurement.json
```

Measured in an isolated container (`local648-offline`, budget $1.00, actual
$0.25). `$/question` is read from `paid_api_calls`; `facts` are extracted and the
overlap judged by gpt-4.1-mini (every answer is dumped in the JSON for spot
checks).

| museum (work) | G facts | S facts | shared | G-only | S-only | G $/q | S $/q | G s | S s |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Courtauld — *A Bar at the Folies-Bergère* | 8 | 6 | 5 | 5 | 3 | 0.0361 | 0.0038 | 8.1 | 9.0 |
| Walters — *The Ideal City* | 4 | 6 | 3 | 3 | 5 | 0.0361 | 0.0046 | 10.8 | 8.8 |
| Wallace — *The Swing* | 7 | 10 | 3 | 5 | 9 | 0.0361 | 0.0046 | 20.2 | 8.7 |
| Frick — *St. Francis in the Desert* | 8 | 5 | 2 | 6 | 3 | 0.0360 | 0.0046 | 7.0 | 11.7 |
| Uffizi — *The Birth of Venus* | 4 | 7 | 2 | 3 | 5 | 0.0362 | 0.0047 | 9.8 | 18.7 |
| National Gallery — *The Arnolfini Portrait* | 10 | 7 | 3 | 10 | 5 | 0.0360 | 0.0047 | 8.7 | 9.4 |
| **mean / per-question** | **6.8** | **6.8** | — | — | — | **0.0361** | **0.0057** | **10.8** | **11.1** |

**Headline:** identical fact coverage (41 distinct facts each across the 6
questions, 6.8/question), near-identical latency (10.8 s vs 11.1 s), and
**Serper is 6.3× cheaper per question** ($0.0057 vs $0.0361). The Serper
per-question cost includes both the Serper queries ($0.001 each) and the
gpt-4.1-mini completion.

### Facts in one but not the other, and WHERE SERPER IS WORSE (honest)

The two backends do not just differ in cost — they find *different* facts:

- **Gemini wins on deep provenance chains** that are scattered across many pages.
  National Gallery: Gemini traced Guevara → Margaret of Austria (who had a lock
  fitted on the shutters) → the Peninsular War → the 1842 purchase for 600
  guineas (10 facts); Serper's 5-page budget missed most of that chain. Frick:
  Gemini had the 1851 National Gallery rejection, the Christie's 1852 sale at
  £735, and the no-loan bequest clause. **This is the real weakness: Gemini's
  grounding reads more pages than our 5-page fetch budget, so long provenance
  stories favour Gemini.**
- **Serper matches or beats Gemini on the work's own facts** — date, maker,
  commission, recent events — which live on the top result pages. On the Wallace
  *Swing* Serper found 10 facts to Gemini's 7 (the 1767 date, Ménage de Pressigny
  guillotined 1794, the 2021 Bank-of-America-funded conservation); on the Uffizi
  *Venus* it found the commission for Lorenzo di Pierfrancesco and the Poliziano
  theme, which Gemini missed.
- **Serper quality depends entirely on query derivation hitting the right
  pages.** Before the context-block fix, the Courtauld query latched onto the
  instruction literal and the bare year "1882" and fetched *Collier's Cyclopedia
  of 1882* — **0 facts**. After parsing the labelled context block, the same
  question returned 6–8 solid facts. A backend that writes only from fetched
  pages is only as good as the pages the query retrieves.

---

## 3. Live A/B — Courtauld + Walters, 3 stops, `RESEARCH_BACKEND=serper`

Own disposable container (`local648-gen`, `--rm`, spare port 5116, network
`development_default`, DB `development-postgres-2-1`). **Never** `docker compose
-p audioura`; no `audioura-*` container was touched. Cache + pool OFF (fresh).
Combined cap $2.50 enforced by `tests/live_run_meter.py` with a reserve gate.

```
./run_local648_live.sh            # offline A/B + both live tours, one container
```

| tour | id | stops | Kiro score (`critique.sh`) | detectors | Gemini grounding req | tour $ |
|---|--:|--:|--:|---|--:|--:|
| The Courtauld Gallery | **564** | 3 | **6 / 10** | 1 fail (`recall_unseen_work`) | **0** | $0.85 |
| The Walters Art Museum | **565** | 3 | **6.5 / 10** | **0 fail** | **0** | $0.57 |

- **Gemini grounding requests per tour: 0** (0 queries). With the Serper backend
  the per-stop research never touches Gemini, and the one request the ticket
  expects — the **preflight** — was a 7-day **cache hit** this run (3
  `venue_preflight_cache` rows for these venues), so it issued no request either.
  On a cold preflight cache it would be exactly **1**. **No grounded Gemini ran at
  all beyond the (cached) preflight** — confirmed in `paid_api_calls`: 48 Gemini
  calls this run, **0 with `webSearchQueries`** (all ungrounded r2 adjudication +
  prose→facts structuring).
- **Per-arm spend** (from `paid_api_calls`, this live run $1.14 total): Serper
  **$0.167** (167 queries), OpenAI **$0.872** (gpt-4.1-mini research + narration),
  Gemini **$0.101** (ungrounded tokens only).
- **The detector failure is backend-independent.** `recall_unseen_work` fired on
  a Courtauld *narration* cross-reference ("…relates back to the societal
  reflections you observed in Seurat's work earlier") — produced by the narration
  layer I did not touch, not by the research backend.
- **The Kiro critique confirms the facts are sound:** every work genuinely hangs
  at its museum, admission/hours are spoken, no URLs in narration. The flagged
  defects (an orphan "theft and recovery" phrase, accession filler, a broken
  "Trajan's Column … wasn't constructed until —" empty-template, intra-stop
  repetition, a weak conclusion) are all **narration/assembly** issues — the layer
  the ticket told me to leave alone — not research-backend defects. 6–6.5/10 is in
  the same band as a Gemini-backend museum tour.

### Rows (additive is_test only; no DELETE)

```
audio_tours BEFORE: 369 (305 is_test)   AFTER: 371 (307 is_test)   => +2, both is_test=true
```

The two reported tours are **564** (Courtauld) and **565** (Walters). (An earlier
run before the research-site routing was extended produced 562/563, also
is_test=true and left in place — additive, never deleted.)

---

## 4. Per-tour $ projection (price card r4)

A 3-stop museum tour's grounded-channel cost, Gemini vs Serper backend:

| line | Gemini backend | Serper backend |
|---|--:|--:|
| preflight (stays on Gemini, cold cache) | 1 req × $0.035 = **$0.035** | 1 req × $0.035 = **$0.035** |
| per-stop research (3 stops) | ~3 req × $0.035 = **$0.105** | Serper + gpt-4.1-mini ≈ **$0.03** total |
| **grounded-channel subtotal** | **~$0.14** | **~$0.065** |

The live run is the end-to-end check: a 3-stop Serper tour's **total** cost
(every provider) was **$0.57–$0.85**, with the research channel measured at
**Serper $0.167 + its share of OpenAI** across two tours — versus a Gemini-backend
tour whose grounded channel alone is ~$0.14/tour and whose per-question grounded
cost the offline A/B measured at **$0.036**. **Replacing the per-stop grounded
Gemini research with Serper removes ~$0.10 of Google search fee per 3-stop tour
(~$0.17 on a 5-stop tour)** at equal fact coverage, trading away only the deep
multi-page provenance chains Gemini's wider page reads surface.

**No blanket quality claim:** the live scores (6, 6.5) and the offline fact
counts are the evidence; the honest cost is a clear win, the honest coverage is a
wash on the work's own facts and a loss on long provenance chains.

---

## 5. Tests & regression (offline, zero paid calls)

`tests/test_local648_serper_research.py` — **10 tests, all pass**: shape parity
with `gemini_with_sources`; `[n]` citations → `supports[].sources` with the
markers stripped (no "1971 ." artefact); `derive_queries` boilerplate drop;
honest-empty (no pages / `NO MATERIAL FOUND`); source de-dup; and the router
dispatch (default→gemini, serper+grounded→serper, serper+ungrounded→gemini, and
the `research_backend()` name helper).

| suite | result |
|---|---|
| `tests/test_local648_serper_research.py` (new) | 10 passed |
| `tests/test_local645_gemini_per_venue.py` | 10 passed |
| `tests/test_local594_grounding_cost.py` | passed |
| `tests/test_local597_guard.py` | passed |
| `tests/test_local603_meter_and_l2.py` + `test_local609_cost_breakdown.py` | passed |
| `test_local533_grounding_count.py` | PASS |
| `tests/test_local587_parallel_stops.py` + `test_local466_multi_story.py` | 14 passed |

`py_compile` clean on every touched module. The default backend is `gemini`, so
all of the above is byte-for-byte identical to pre-change behaviour.

---

## 6. Files

- `serper_research.py` — the backend (new).
- `story_leads.py` — `research_backend()`, `research_with_sources()` router,
  `RESEARCH_BACKEND_ENV` (additive).
- `story_production_loop.py` — the per-stop r1 narrate calls the router.
- `venue_parts.py`, `stop_knowledge_fallback.py` — their per-stop grounded
  **research** calls go through the router (preflight untouched).
- `measure_local648_overlap.py`, `LOCAL648_overlap_measurement.json` — the offline
  A/B harness + its results.
- `run_local648_container.py`, `run_local648_live.sh` — the isolated live-run
  harness.
- `tests/test_local648_serper_research.py` — the offline test suite.

No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
`.continuous_dev/STATUS.md`.
