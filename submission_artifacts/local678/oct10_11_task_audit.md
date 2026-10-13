# LOCAL-678 — Oct 10–11 Kiro task audit: where did the ~6.6k unmetered OpenAI requests come from?

Dashboard (…VCEA, the Mac's key) Oct 11 UTC ≈ 9.4k chat requests / $26.80.
`paid_api_calls` Oct 11 UTC = 2,769 requests / $7.67. Gap ≈ 6.6k requests / ~$19.

## Method
For each Oct 10–11 task I checked whether its harness runs **in a container**
(metered: the generator/orchestrator images install the meter via
`PYTHONPATH=/opt/meter`) or **on the host** (NOT metered before this ticket:
no sitecustomize, so `paid_api_meter` was never imported).

| task | harnesses | how it runs | metered before 678? |
|---|---|---|---|
| 663 | run_local663_container.py + run_local663_live.sh | `docker run … python run_local663_container.py` | YES (container) |
| 667 | run_local667_container.py + _live.sh | container | YES |
| 668 | run_local668_container.py + _live.sh | container | YES |
| 669 / 669b / 669c | run_local669*_container.py + _live.sh | container | YES |
| 670B / 671 / 672 / 673 | (no run harness in tree; config/limit work) | n/a | n/a |
| 674 | **measure_local674_walking.py**, **measure_local674_pervenue.py** + run_local674_container.py + _live.sh | the two `measure_*` run **on the HOST** (`python3 measure_local674_walking.py`); only the `_container` arm is in a container | **NO for the measure_* harnesses** |
| 675 | critique.sh (host python = spoken_text_hygiene only, no paid calls) | host, but no paid calls | n/a |

## Most likely source of the 6.6k
The **host-run `measure_*` harnesses of task 674 (and the sibling
`measure_local648_overlap.py`)**, run repeatedly on Oct 10–11 while tuning the
walking-research A/B.

Why they multiply fast and why they were invisible:
- `measure_local674_walking.py` loops **3 requests × 5 stops × up to 3 arms**
  (gemini / serper / serper_plus) = up to **45 stop-arm cells per run**. Each cell
  makes a grounded **Gemini** research call AND a **gpt-4.1-mini** judge call
  (`_cheap()` → `requests.post('https://api.openai.com/v1/chat/completions')`);
  the serper arms additionally fetch pages and run a gpt-4.1-mini **extractor per
  source**. One full run is well over a hundred OpenAI requests.
- `measure_local674_pervenue.py` and `measure_local648_overlap.py` add more of the
  same per run.
- These were run **on the host** (the docstrings show `python3 measure_local674_walking.py`),
  where there is no sitecustomize and therefore no meter — so none of those
  OpenAI/Gemini requests were written to `paid_api_calls`. Re-running the A/B many
  times across Oct 10–11 (model/arm tuning) accounts for thousands of requests.
- Even the raw `requests.post` calls in `_cheap()` were missed purely because the
  meter module was never imported in that process; and any OpenAI/Gemini traffic
  that goes through the **SDK (httpx)** would have been missed even inside a
  metered process until step 2 of this ticket.

## What closes it
- **Step 3** wires `_meter/meter_bootstrap.py` into `measure_local674_walking.py`,
  `measure_local674_pervenue.py`, `measure_local648_overlap.py`,
  `measure_local645_overlap.py`, `replay_harness.py`, and the host `run_*_live.py`
  / massart / mcmullen runners, so the meter is now installed in those host
  processes — their raw-requests AND SDK/httpx calls are now recorded.
- **Step 2** patches httpx (sync+async) and aiohttp, so SDK calls (OpenAI v2,
  Google GenAI) are recorded even inside already-metered processes.
- **Step 6** reconciliation script lets Michael paste the dashboard per-model
  numbers and see the remaining gap per model, to confirm the gap closes on the
  next measurement day.
