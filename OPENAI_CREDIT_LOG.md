# OpenAI credit log

**Why this file exists.** Michael asked on 2026-08-18 how much he had added before and
when. The answer was not recorded anywhere — not in `DECISIONS.md`, not in memory, not in
the ClickUp task that was filed for the previous outage. Work has now stopped twice on an
empty balance in two weeks, and each time the only record of the fix was that generation
started working again.

**Add one line per top-up and per outage.** The authoritative source is still Michael's
billing history at platform.openai.com — this file is the project-side record so a fresh
session can answer the question from disk.

| date | event | amount | notes |
|---|---|---|---|
| 2026-08-05 18:35 | **outage** — `credit_balance_exhausted` | — | D193. All three keys returned it, so it was the balance, not a key. ClickUp `wdvrdaxda6` filed with instructions. Continuous dev paused. |
| 2026-08-05/06 | top-up | **unrecorded** | Michael topped up and work resumed; nobody wrote down the amount or the exact time. This gap is why the file exists. |
| 2026-08-18 21:49 | **outage** — `credit_balance_exhausted` | — | D483. Three measurement runs died at PHASE_3A in under a second. Nothing spent. |
| 2026-08-18 ~22:0x | **top-up** | **$30.00** | Michael's words: *"I put $30 to OpenAI."* Verified live at 22:06 by direct API probe — `gpt-4o-mini` returned HTTP 200. |

## Measured burn rate, for sizing the next one

| date measured | unit | cost |
|---|---|---|
| 2026-08-05 | 2-stop tour | $0.019 – $0.026 |
| 2026-08-05 | 8-stop tour | $0.047 – $0.059 |
| **2026-08-18** | **4-stop release-check run** | **~$0.16** |

The 08-05 figures are stale and far too low — they predate the story pipeline's per-stop
SERP retrieval and snippet mining. Do not quote them for planning.

**What actually drives spend now is measurement, not generation.** D480 requires a mean
and range over >= 3 runs, so a single A/B comparison is 6 runs, ~$1. Yesterday's total was
~$3.13 across 16 runs.

At ~$0.16/run, **$30 is roughly 190 runs, or about 30 A/B comparisons.**

## Standing recommendation

**Set auto-recharge** at platform.openai.com/settings/organization/billing — a low
threshold ($10) with a $30–50 refill. Twice now the failure mode has been identical: the
balance runs out mid-session, every generation returns 429, and the session either burns
time retrying or stops entirely. Auto-recharge is the only fix that does not depend on
someone noticing.

## Not the same thing as Serper

`SERP_API_KEY` (Serper.dev) is a separate prepaid account — 50K credits topped up
2026-08-11, ~$0.001/query (D343). A Serper outage reports `{"message":"Not enough
credits"}`, not `credit_balance_exhausted`. Check which one is empty before acting.
