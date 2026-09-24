# SUBMISSION — LOCAL-533: Make grounding cost visible before anyone optimises it

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-533-instrument-grounding-cost
**Base:** storied (46a1954) — verified `git merge-base --is-ancestor 46a1954 HEAD` exits 0.

## What the task asked

Count and price Google-Search grounding requests the same way OpenAI calls are
already counted, and print them in the same summary. Grounding bills ~3.5c per
REQUEST, independent of tokens, and appeared nowhere in the pipeline's
`Total API cost` line (which sums OpenAI call sites only). This is instrumentation,
not optimisation — no behaviour change to generation.

## Where grounding is issued (the search)

I started from `venue_parts.py` and `tragedy_context_gate.py` as instructed, then
went wider. Grounding — the `google_search` tool attached to a Gemini request — is
issued from exactly **two functions**, both in `story_leads.py`:

- `_gemini(prompt, grounded=True)`  — line ~139, attaches `{'tools':[{'google_search':{}}]}` when `grounded`
- `gemini_with_sources(prompt, grounded=True)` — line ~210, same tool, default `grounded=True`

Verified by searching the whole tree for `google_search` / `generativelanguage` /
`groundingMetadata`: the only live sites are those two functions. `preflight.py`
also hits the Gemini endpoint but is a diagnostic health-check, not part of tour
generation. Every pipeline module that grounds during a tour
(`venue_parts.py`, `tragedy_context_gate.py` via `story_leads`, `stop_knowledge_fallback.py`,
`story_production_loop.py`, `restaurant_practicals.py`, and `generate_tour_text.py`
via `story_leads.run`) funnels through those two functions. `tragedy_context_gate.py`
itself is search-first via Serper (`_serp_search`) — a *separate* billing channel
already priced by `cost_rates.search_cost`, not grounding.

So the two functions are a single chokepoint. Counting there catches every grounded
request in the pipeline, present and future, without hunting call sites.

## What I changed

1. **`story_leads.py` — central counter.** Module-level `_GROUNDING_REQUESTS` with
   `reset_grounding_requests()`, `get_grounding_requests()`, `_count_grounding_request()`.
   The counter increments **once per grounded request actually issued** — inside both
   `_gemini` and `gemini_with_sources`, *after* the API-key check (a keyless no-op is
   not counted) and *only* when `grounded=True` (an ungrounded Gemini call is free of
   the per-request grounding charge and not counted), immediately before the HTTP POST.
   Requests, not tokens.

2. **`cost_rates.py` — one price, one place.** `GROUNDING_COST_PER_REQUEST = 0.035`
   with a source/date comment (https://ai.google.dev/gemini-api/docs/pricing, read
   2026-09-23; $35 per 1,000 grounding requests). Helper `grounding_cost(n) = n * rate`.

3. **`generate_tour_text.py` — count, price, print, record.**
   - Resets the counter at the start of a generation, *before* the cache check, so a
     cache hit correctly reads back 0.
   - On the success path, reads the counter, prices it, and prints two new lines next
     to the existing one:

         Total API cost: $0.2605 (37448 tokens)
         Grounding:      $0.3150 (9 requests)
         Tour total:     $0.5755

   - Folds `grounding_cost`, `grounding_requests`, `tour_total_cost` (and a
     `breakdown.grounding` entry) into the canonical `_LAST_GENERATION_COST` record.
   - On a cache hit, prints the same three lines (all $0.00 / 0 requests) and records
     the same fields.

4. **`run_round9.py` — record, don't parse.** Reads
   `generate_tour_text._LAST_GENERATION_COST` after each tour and writes a `cost`
   block into `ROUND9_SUMMARY.json` with both channels
   (`total_api_cost_usd`, `total_tokens`, `grounding_cost_usd`, `grounding_requests`,
   `tour_total_cost_usd`, `cache_hit`). No log parsing — that is how the number got
   lost in the first place.

## Acceptance — evidence

### A real generated tour prints both lines, separately verifiable

One real 4-stop tour (`Our Lady Help of Christians Catholic Church, Newton MA`,
museum, 4 stops, cache disabled) via `run_local533_one_tour.py`. From
`LOCAL533_ONE_TOUR_RUN.log`, lines 664–666:

    Total API cost: $0.2605 (37448 tokens)
    Grounding:      $0.3150 (9 requests)
    Tour total:     $0.5755

The two channels are separately verifiable: the OpenAI figure is the sum of the
per-call `Stop N API call cost` lines already in the log; the grounding figure is
`9 × $0.035 = $0.315`, and 9 is the count of grounded requests issued.

### HOW I verified the count matches requests actually issued

`test_local533_grounding_count.py` — an **instrument-level** proof. It monkeypatches
`requests.post` and, at the wire, independently counts every HTTP request whose body
carries the `google_search` tool. It then compares that independent network-level
tally to `story_leads.get_grounding_requests()`. Result (`RESULT: PASS`):

- 5 grounded `_gemini` calls → wire grounded tally 5, counter 5
- 3 **ungrounded** `_gemini` calls → wire ungrounded 3, counter 0 (not counted)
- 4 `gemini_with_sources` calls → wire grounded 4, counter 4
- 1 ungrounded `gemini_with_sources` → counter 0
- mixed (5 requests: 3 grounded, 2 ungrounded) → counter == 3 == wire grounded tally
- `reset_grounding_requests()` zeroes it
- `grounding_cost(3) == 3 × 0.035`, `grounding_cost(0) == 0`

This proves the counter equals the number of grounded requests that leave the client,
not merely that a counter exists. On the live tour, the same counter read **9**, and
$0.315 = 9 × $0.035.

### Cached tours report grounding $0.00

`run_local533_cache_check.py` (free — issues no paid calls) re-requests the same tour,
which is now cached. Output:

    CACHE HIT: Our Lady Help of Christians Catholic Church, Newton MA / museum / 4
    Total API cost: $0.0000 (0 tokens)
    Grounding:      $0.0000 (0 requests)
    Tour total:     $0.0000

    _LAST_GENERATION_COST = { "cache_hit": true, "grounding_cost": 0.0,
      "grounding_requests": 0, "tour_total_cost": 0.0, ... }
    get_grounding_requests() = 0
    RESULT: PASS — cache hit reports grounding $0.00 / 0 requests

A cache hit issues no grounded requests, so grounding is $0.00 — verified, not asserted.

### COST_PER_TOUR.md updated with a full-cost figure

Added a "Full cost — both billing channels" section: the 4-stop tour's real bill is
**$0.5755** (OpenAI $0.2605 + grounding $0.3150 across 9 requests), ~$0.58 not ~$0.26.
Grounding on this tour was *larger* than the OpenAI cost and was previously invisible.

## A bug I found and fixed during verification

My first success-path `_LAST_GENERATION_COST` write was silently **overwritten** by
the canonical `[LOCAL-60]` cost record further down the function (~line 19701). The
printed lines were correct, but the recorded dict reverted to the OpenAI-only shape.
Caught by dumping the record in the live run (it showed the old shape despite correct
prints). Fixed by folding the grounding fields into that canonical record and removing
my duplicate. The cache-hit dump above confirms the record now carries grounding.

## No behaviour change

The grounding request itself is unchanged: I count *before* the same POST that always
ran, guarded by the same `grounded`/key conditions the code already used. No prompt,
model, tool, timeout, or control-flow change to generation. This measures; it does not
tune.

### Scope note (stated honestly)

Rare cost-ceiling **partial-tour** early returns and clean-fail returns still record
the OpenAI-only cost (grounding not folded in on those branches). These are guardrail
paths not exercised by the acceptance criteria (a normal 4-stop tour and a cache hit),
and editing them carries behaviour risk on branches with no live coverage — a poor
trade for a measurement-only task. The two acceptance paths (normal success, cache hit)
carry the full two-channel cost.

## Files changed

- `story_leads.py` — grounding request counter (reset/getter/increment)
- `cost_rates.py` — `GROUNDING_COST_PER_REQUEST` + `grounding_cost()`
- `generate_tour_text.py` — reset/read/price/print grounding; record in `_LAST_GENERATION_COST`
- `run_round9.py` — record both channels into `ROUND9_SUMMARY.json`
- `COST_PER_TOUR.md` — full-cost figure for one tour
- `test_local533_grounding_count.py` — instrument-level count proof (new)
- `run_local533_one_tour.py` — one real 4-stop tour + cache hit (new)
- `run_local533_cache_check.py` — free cache-hit $0.00 check (new)
- `LOCAL533_ONE_TOUR_RUN.log` — live run log (evidence)
