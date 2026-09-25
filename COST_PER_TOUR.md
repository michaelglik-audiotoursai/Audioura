# Cost per tour — measured, not estimated

**Measured 2026-09-23** from `round8_run.log`, the round-8 regeneration. Both tours
ran on the current tree with Postgres up and the cache disabled
(`DISABLE_TOUR_CACHE=1`), so these are full generations with no cache hits.

| tour | stops | cost | tokens | wall | chars | $/stop |
|---|---|---|---|---|---|---|
| CHURCH_1 (Our Lady Help of Christians, Newton MA) | 4 | **$0.2462** | 40,919 | 385s | 10,702 | $0.0616 |
| LOGAN_1 (Boston Logan International) | 4 | **$0.1703** | 26,942 | 235s | 9,208 | $0.0426 |

**~$0.21 for a 4-stop tour.** Earlier spot measurement: $0.33 for 6 stops
($0.055/stop), consistent with these.

## Full cost — both billing channels (LOCAL-533, measured 2026-09-23)

The figures above are the OpenAI channel ONLY. Grounding (Gemini + Google Search)
is now counted and priced, so a tour's FULL cost is on the page. Measured on the
current tree, cache disabled, one real 4-stop generation of
`Our Lady Help of Christians Catholic Church, Newton MA` (museum, 4 stops):

    Total API cost: $0.2605 (37448 tokens)     ← OpenAI token channel
    Grounding:      $0.3150 (9 requests)        ← Google Search, $0.035/request
    Tour total:     $0.5755                      ← the real bill

**Grounding was $0.3150 on this tour — larger than the $0.2605 OpenAI cost, and
previously invisible.** The full cost of a 4-stop tour is **~$0.58**, not ~$0.26.
The OpenAI-only line understated the real bill by more than half. Grounding is
priced per REQUEST (9 grounded requests here), independent of token count, so it
does not move with prompt length — only with how many grounded calls are issued.

Cached tours issue no grounded requests and correctly report `Grounding: $0.0000
(0 requests)` — verified on a cache hit of the same request.

Rate source: https://ai.google.dev/gemini-api/docs/pricing (read 2026-09-23),
$35 per 1,000 grounding requests = $0.035/request. Constant lives in
`cost_rates.GROUNDING_COST_PER_REQUEST`; count is `story_leads.get_grounding_requests()`.

## What the top OpenAI-only table does NOT include — now fixed

Until LOCAL-533, the line the pipeline printed was `Total API cost`, summed from
OpenAI call sites ONLY. Google Search grounding bills separately at **3.5 cents
per request, independent of token count** — so a handful of grounded calls can
rival the entire OpenAI cost of a tour, and none of it appeared. The round-8 log
that produced the top table mentions grounding twice and carries no Gemini cost
line at all, which is why those CHURCH_1/LOGAN_1 numbers are OpenAI-only and
understate the real bill.

**This is now instrumented** (see the full-cost section above): the pipeline
prints a `Grounding:` line and a `Tour total:` line next to `Total API cost`, and
`run_round9.py` records all of it into `ROUND9_SUMMARY.json` from a returned
record instead of parsing the log.

**Do not optimise token usage before looking at both.** They respond to opposite
levers: tokens fall with shorter prompts, grounding falls with fewer *requests*, and
a change that trades one for the other can raise the bill while the printed number
drops. Both are now on the page, which is the precondition for tuning either.


## What is already solved

Caching works and is populated — `tour_cache` holds 166 rows, and a 4-stop repeat was
verified at **$0.00 in 0.2s** against $0.33 generated. The remaining lever is not more
caching code, it is **hit rate**: the stop-pool design (D581).

## The open question

Per-tour cost against Beta. That comparison is the thing Michael actually asked for,
and it cannot be answered from this file alone — Beta's per-tour cost has not been
measured the same way. Measuring it the same way is the next step, not guessing.

## How to reproduce

    python3 run_round8.py            # writes round8_run.log
    grep -E "Total API cost|Grounding|Tour total" round8_run.log

Or a single 4-stop tour with the full-cost lines (LOCAL-533):

    python3 run_local533_one_tour.py     # one fresh tour, then a cache hit
    grep -E "Total API cost|Grounding|Tour total" LOCAL533_ONE_TOUR_RUN.log

`run_round9.py` now captures cost into its summary JSON (`ROUND9_SUMMARY.json`)
from `generate_tour_text._LAST_GENERATION_COST` — both the OpenAI channel and the
grounding channel — instead of parsing it out of the log, which is how grounding
cost got lost in the first place.
