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

## What this number does NOT include

**Grounding is not in it.** The line the pipeline prints is `Total API cost`, summed
from OpenAI call sites. Google Search grounding bills separately at roughly
**3.5 cents per request, independent of token count** — so a handful of grounded
calls can rival the entire OpenAI cost of a tour, and none of it appears above.
The round-8 log mentions grounding twice and carries no Gemini cost line at all.

**Do not optimise token usage before splitting these two.** They respond to opposite
levers: tokens fall with shorter prompts, grounding falls with fewer *requests*, and
a change that trades one for the other can raise the bill while the printed number
drops.

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
    grep "Total API cost" round8_run.log

`run_round8.py` does not currently capture cost into its summary JSON — it parses out
of the log. Worth fixing if cost becomes a tracked metric rather than a spot check.
