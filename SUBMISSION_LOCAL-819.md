# SUBMISSION — LOCAL-819: the Mac's paid-API meter misses ~2/3 of OpenAI calls

**Branch:** `LOCAL-819-meter-gaps`  (base: `subscribed` = 5e2d588a)

## The problem (from the ticket, confirmed)

OpenAI usage for key mac-mini-2026-10 (ends **k9sA**), Oct 26–30: **$47.42 / 28,995 requests**.
The Mac meter (`meterlogs/*.jsonl`, `kind=openai`) recorded only **10,268 calls / $17.93**,
with **`tokens_in`/`tokens_out` = 0 on every row**. So ~18k calls and ~$29 on the Mac key
never showed up where LEAD sums it.

Reproduced on the live log (`~/Audioura/meterlogs/paid_api_calls.jsonl`):

```
kinds: {'openai': 19609, 'serper': 8162, 'gemini': 4291, 'anthropic': 93}
openai rows tokens_in/out == 0 : 19609   (with tokens: 0)
```

Every OpenAI row carried the token data **only nested under `usage.*`** — the top-level
`tokens_in`/`tokens_out` that every report reads were never written (Gemini rows had them).
That is the `tokens=0` half. The other half is **install / landing coverage**: isolated task
containers wrote their meter log to per-task filenames or nowhere LEAD globs, and almost none
tagged `service=<task id>`, so a single sweep could not sum a task's spend.

---

## 1. OFFLINE audit — every path that can reach a paid host

There are **two** meter layers already in the tree:

* **Network choke point** — `_meter/paid_api_meter.py` (`install()`), loaded via
  `sitecustomize` (`PYTHONPATH=/opt/meter`) in containers and via
  `import _meter.meter_bootstrap` on the host. It patches **`requests.Session.send`,
  `urllib.request.urlopen`, `httpx.Client/AsyncClient.send`, `aiohttp.ClientSession._request`,
  and `botocore …_make_api_call`**, and writes one `paid_api_calls` row per paid request
  (`kind` ∈ openai/gemini/serper/anthropic/polly/aws_translate) to `meterlogs/*.jsonl` + the DB.
  This is the layer the ticket's evidence comes from. **Everything on the wire is caught here
  IF `install()` ran.**
* **Per-tour accumulator** — `openai_cost_wrapper.py` + `cost_accumulator` (patches
  `requests.post` and the openai client). Per-tour $, not the ledger the ticket is about.

Because the network layer meters at the HTTP client, a call is metered **when the meter is
installed in that process**, regardless of the call site. The audit therefore classifies by
(a) does the call go through a patched client, and (b) is the meter installed there.

### OpenAI (`api.openai.com`)

| Path | file:line | On the wire via | Metered? |
|------|-----------|-----------------|----------|
| openai SDK client | `story_element_extractor.py:419` (`openai.OpenAI(`) | httpx | ✅ when installed (httpx patch, LOCAL-678) |
| openai SDK client | `run_local252_round7b.py:329` (`openai.OpenAI(`) | httpx | ✅ when installed |
| raw chat-completions | majority of call sites (gates / writers / extractors) | `requests.post` | ✅ when installed (requests patch) |
| `ChatOpenAI` / langchain | — none in repo — | — | n/a |

Only two direct SDK clients; both ride httpx and are covered. No langchain.

### Gemini (`generativelanguage.googleapis.com`)

| Path | file:line | On the wire via | Metered? |
|------|-----------|-----------------|----------|
| grounded / ungrounded generate | `story_leads.py:384`, `story_leads.py:443` | `requests.post` | ✅ when installed |
| venue preflight | `preflight.py:98` | `requests.post` | ✅ when installed |
| escalating lookup | `escalating_lookup.py:530` | `requests.post` | ✅ when installed |
| replay harness | `replay_harness.py:456` | `requests.post` | ✅ when installed |

### Serper (`google.serper.dev`)

All production callers go through **`serper_meter.serper_post()`**, which calls
`record_call()` directly (guaranteed row even if the network patch is absent):
`interpretive_enrichment.py`, `exhibition_checklist.py`, `exhibition_site_js.py`,
`work_story_searcher.py`, `dining_corpus_harvester.py`, `serper_plus_research.py`,
`current_affairs_news.py`, `venue_resolver.py:2808`, `places_search.py`,
`customer_voice.py`, `map_delivery_service.py:781`, `preflight.py:130`.
Raw `urllib` Serper calls remained in a few host harnesses/fetchers (e.g.
`run_local242_retrieval_lift.py:63`) — covered by wiring the meter into those harnesses (below).

### The real gaps (not "a missing call site" — the two below)

1. **`tokens=0` on every OpenAI/Anthropic row** — the counts were written only under
   `usage`, never at the top level the reports read.
2. **Install / landing coverage** — (a) host-run harnesses with no `sitecustomize` never
   installed the meter; (b) isolated task containers wrote to per-task log filenames (or an
   unmounted `/meterlogs`) and did not set `service=<task id>`, so one sweep couldn't sum them.

---

## 2. Fix the `tokens=0` bug — real `tokens_in`/`tokens_out`, `usd` unchanged

`_meter/paid_api_meter.py` (and the byte-identical `translation-service/_meter/paid_api_meter.py`):

* New helpers `_openai_tokens(usage)` and `_anthropic_tokens(usage)` read the counts from the
  response `usage` block (both the `prompt/completion_tokens` and `input/output_tokens` shapes;
  Anthropic folds `cache_read_input_tokens` into `tokens_in`).
* The `openai` and `anthropic` branches of `_record()` now set **top-level `tokens_in` /
  `tokens_out`** alongside the existing `usage` dict. `usd` is still computed from the same
  `usage`, so **no cost changes** — only the token fields are now populated.

Before (live): all 19,609 OpenAI rows `tokens_in/out = 0`. After (live proof): rows carry
`tokens_in=14 tokens_out=1`.

## 3. Route every unmetered path through the meter

* **Containers** already install the meter via `/opt/meter` `sitecustomize`
  (`docker-compose.subscribed-local.yml`), and the SDK/httpx/requests/urllib/aiohttp/botocore
  choke points are all patched (LOCAL-678/769). No new call-site edits needed there.
* **Host harnesses** that made paid calls without installing the meter were wired via the
  established one-off editor `_wire_network_meter_into_host_harnesses.py` (inserts
  `import _meter.meter_bootstrap`). LOCAL-819 added 12 more:
  `run_local242_retrieval_lift.py`, `run_local39_live_acceptance.py`, `run_local413_live.py`,
  `run_local767_live.py`, `run_local577_palais_live.py`, `run_local580_live.py`,
  `run_local432_live_palais.py`, `run_local582_live.py`, `measure_local806.py`,
  `run_local576_live.py`, `run_local562_live_chart_house.py`,
  `run_local251_namedrop_not_delivery.py`. (All 39 listed harnesses now carry the bootstrap.)

## 4. Isolated task containers land in ONE place, tagged `service=<task id>`

* **`SERVICE` now defaults to `TASK_BUDGET_ID`** when `METER_SERVICE` is unset
  (`paid_api_meter._default_service()`). Every budgeted task already exports `TASK_BUDGET_ID`
  (LOCAL-817), so its rows are tagged `service=<task id>` with **zero per-runner wiring**;
  `METER_SERVICE` still overrides.
* **`meter_container_env.py`** — the single documented contract for an isolated run:
  `docker_meter_args()` / `apply_meter_env()` bind-mount `~/Audioura/meterlogs → /meterlogs`,
  write the **canonical** `PAID_API_LOG=/meterlogs/paid_api_calls.jsonl`, set
  `METER_SERVICE=<task id>`, `PYTHONPATH=/opt/meter`, and the optional non-secret
  `METER_KEY_SUFFIX`.
* **`key_suffix`** — the meter now writes a **non-sensitive** `key_suffix` (last ≤8 chars of
  the key, from `METER_KEY_SUFFIX`) on every row, so the metered side can be lined up against
  the provider usage page, which is per-key. The meter still never logs a key.

## 5. `meter_report.py --since <ts>` — totals by day / service / model / key-suffix

Globs `~/Audioura/meterlogs/*.jsonl` (so **all** per-task logs are summed in one sweep),
filters by `--since` (UTC, matching how the meter writes `ts`), and prints
**BY DAY / BY SERVICE / BY MODEL (family-normalised) / BY KEY-SUFFIX** with requests, usd,
`tokens_in`, `tokens_out`, plus a TOTAL. `--kind`, `--log`, `--all-status`, `--json`.
Reads only — **no paid calls, no writes**.

---

## Tests

New `tests/test_local819_meter_gaps.py` — 13 tests, isolated (httpx `MockTransport`, DB stubbed,
tmp log; no network, no real paid call):

* OpenAI row has top-level `tokens_in`/`tokens_out` (the bug), `usd` unchanged; `_openai_tokens`
  both shapes.
* Anthropic row folds `cache_read_input_tokens` into `tokens_in`; `_anthropic_tokens`.
* `key_suffix` on the row, absent→`""`, and truncation (**never the full key**).
* `SERVICE` defaults to `TASK_BUDGET_ID`; `METER_SERVICE` overrides.
* `meter_container_env.docker_meter_args` contract.
* `meter_report` aggregation (day/service/model/key-suffix), `--since` filter, non-200
  counted-but-$0; `_norm_since`, `_norm_model`.

Regression — every meter/cost test file passes in isolation (165 tests):
`test_local819_meter_gaps`, `test_local678_meter_httpx_aiohttp`, `test_local707_serper_metered`,
`test_local707_serper_scan_guard`, `test_local712_anthropic_provider`, `test_local712b_current_claude`,
`test_local769_boto3_metered`, `test_local673_daily_paid_limit`, `test_local817_task_budget`,
`test_local60_cost_metering`, `test_local613_meter_and_cap`, `test_translation_meter_copy`,
`test_local783_serper_places`, `test_cost_meter_cloudsql_url`, `test_local64_cost_ceiling`.
(`translation-service/_meter/paid_api_meter.py` was kept **byte-identical** to the base copy so
`test_translation_meter_copy` passes.)

> Note: running `test_local673` immediately before `test_local613` in one pytest process fails
> `test_local613::test_one_row_lands_in_ledger` — `test_local673` does
> `monkeypatch.setitem(sys.modules, "psycopg2", stub)` which leaks into `cost_meter`. This is a
> **pre-existing** test-ordering issue (reproduces on the base commit; both files are untouched
> by LOCAL-819) and is out of scope here. Each file passes on its own.

---

## Live proof — budget enforced, ≤5 tiny calls, real tokens

```
TASK_BUDGET_ID=LOCAL-819 TASK_BUDGET_USD=0.10 python3 live_local819_proof.py
```

5 tiny OpenAI calls (`gpt-4o-mini`, `max_tokens=5`) via the OpenAI SDK (httpx path), metered to
a **proof-only** log (`paid_api_calls_LOCAL-819-proof.jsonl`, `service=LOCAL-819-proof`,
`key_suffix=k9sA` — the ticket's mac-mini key suffix), DB write stubbed:

```
  call 1..5: ok  prompt=14 completion=1
--- PROOF METER ROWS (5 new) ---
  kind=openai status=200 model=gpt-4o-mini-2024-07-18 tokens_in=14 tokens_out=1 usd=0.00000270 service=LOCAL-819-proof key_suffix=k9sA
  ... (x5) ...
  calls made           : 5
  meter rows written   : 5
  all rows real tokens : True
  total proof spend    : $0.00001350 (budget $0.10)
  RESULT: PASS
```

Each row has **real `tokens_in=14 tokens_out=1`** (would have been 0 before the fix).
`meter_report.py` on the proof log:

```
BY SERVICE      LOCAL-819-proof   5 req   $0.0000   tokens_in=70  tokens_out=5
BY MODEL        gpt-4o-mini       5 req   $0.0000   tokens_in=70  tokens_out=5
BY KEY-SUFFIX   k9sA              5 req   $0.0000   tokens_in=70  tokens_out=5
TOTAL           requests=5  usd=$0.0000  tokens_in=70  tokens_out=5
```

The canonical `paid_api_calls.jsonl` was **not polluted** (0 `LOCAL-819-proof` rows).

### `task_budget_report.py LOCAL-819`

```
Task budget report: LOCAL-819
Ledger: /Users/micha/.audioura_task_budgets/LOCAL-819.json

  when (UTC)                      usd  note
  ----------------------------------------------------------
  2026-10-30T01:51:39Z        $0.0000  LOCAL-819-proof live proof
  ----------------------------------------------------------
  TOTAL (1 runs)              $0.0000

Budget:    $0.1000
Remaining: $0.1000
```

(Spend is $0.0000135, which rounds to $0.0000 at the report's 4 dp — far under $0.10.)

---

## Files changed

**Modified (tracked):**
* `_meter/paid_api_meter.py` — `tokens_in`/`tokens_out` fix, `key_suffix`, `SERVICE`←`TASK_BUDGET_ID`.
* `translation-service/_meter/paid_api_meter.py` — kept byte-identical to the above.
* `_wire_network_meter_into_host_harnesses.py` + the 12 newly wired host harnesses listed in §3.

**New:**
* `meter_report.py` — totals by day/service/model/key-suffix (read-only).
* `meter_container_env.py` — standard isolated-container meter contract.
* `tests/test_local819_meter_gaps.py` — 13 unit tests.
* `live_local819_proof.py` — the budget-enforced live proof harness.
* `SUBMISSION_LOCAL-819.md` — this file.

No `DELETE`; no live-DB writes; no edits to the do-not-touch files; no shared `audioura-*`
containers touched.
