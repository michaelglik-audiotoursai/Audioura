# SUBMISSION — LOCAL-678: close the paid-API meter's blind spots

**Branch:** `LOCAL-678-meter-blind-spots` (from `subscribed` @ 82a76ed9)
**Agent:** Mac Mini Kiro

## Problem
OpenAI dashboard for the Mac's key (…VCEA) on Oct 11 UTC ≈ **9.4k chat requests /
$26.80**. `paid_api_calls` for the same day held only **2,769 requests / $7.67** —
**≈ 6.6k requests (≈ $19) never metered** (same shape for Gemini on Oct 10).

Root cause: the network meter (`_meter/paid_api_meter.py`, loaded in containers
via sitecustomize + `PYTHONPATH=/opt/meter`) patched **only** `requests.Session.send`
and `urllib.request.urlopen`. Two gaps:

1. **HTTP client gap.** The OpenAI python SDK (`openai 2.48.0`) and the Google
   GenAI SDK send through **httpx**, not requests/urllib. Any SDK call bypassed
   the meter even inside a metered process.
2. **Process gap.** Scripts run directly on the **host** (Kiro `measure_*.py` /
   `replay_harness.py`, the `run_*_live.py` runners) have no sitecustomize, so the
   meter was never installed and *every* paid call they made — requests, urllib,
   httpx or SDK — was invisible.

## Call-site survey (ticket item 1)
Across the repo (`*.py`): `requests.*` in **253** files, `urllib…urlopen` in **31**,
`api.openai.com` literal in **58**, the OpenAI **SDK** (`OpenAI(` / `chat.completions.create`)
in **7**. Direct `import httpx` / `import aiohttp` in app code: **1 each** — the SDKs
pull httpx in transitively, which is exactly why a per-library patch (not per-call-site)
is the right fix. `httpx 0.28.1`, `aiohttp 3.13.5`, `openai 2.48.0` are all installed
on the host.

## What changed

### 1. Meter httpx (sync + async) and aiohttp  — `_meter/paid_api_meter.py`
`install()` now also wraps the single choke point of each client:
`httpx.Client.send`, `httpx.AsyncClient.send`, and `aiohttp.ClientSession._request`.
Same contract as the requests patch: enforce the daily limit before a paid host,
record `(url, status, body, req_body)` after, never raise into the caller, and
leave the response fully readable. Streaming sends are recorded with an empty body
so the caller's stream is never consumed. `install()` is now **idempotent**
(module-global `_INSTALLED` guard) so sitecustomize + meter_bootstrap can't double-wrap.

### 2. Install the meter in host-run processes
- **New `_meter/meter_bootstrap.py`** — one line (`import meter_bootstrap`) puts
  the repo's `_meter` dir on `sys.path` and installs `paid_api_meter`. Idempotent;
  fails open (a meter error never breaks a run).
- **New `_wire_network_meter_into_host_harnesses.py`** — idempotent editor that
  inserts that import right after the module docstring. Ran it over **27 host
  harnesses** (the `measure_local*`, `replay_harness.py`, and host `run_*_live.py` /
  massart / mcmullen runners). All compile.

### 3. Container audit (ticket item 3) — `submission_artifacts/local678/container_meter_audit.md`
Metered images (have `COPY _meter/ /opt/meter/` + `ENV PYTHONPATH=/opt/meter`):
**generator, orchestrator, modernized, polly-tts** — these are the Mac's primary
tour path, so main generation is metered. **Blind-spot images** (make paid calls,
no meter): translation-service, the news stack (news-generator/-processor/-orchestrator,
background-article-processor, simple-news-search), tour-processor, cloudrun
(beta/GCloud), and the top-level Dockerfile. One PYTHONPATH override
(`docker-compose-testing.yml` → `/app`) masks the meter but that image runs only
`http.server` (no paid calls). Fixing the production Dockerfiles is flagged as an
infra change needing Michael's OK — not applied in this branch.

### 4. Oct 10–11 task audit (ticket item 2) — `submission_artifacts/local678/oct10_11_task_audit.md`
Tasks 663/667/668/669/669b/669c run their paid work **in a container** (metered).
670B/671/672/673 are config/limit work (no run harness). Task **674 uniquely** ships
host-run `measure_local674_walking.py` + `measure_local674_pervenue.py`. Those, plus
`measure_local648_overlap.py`, are the most likely source of the ~6.6k: each
`measure_local674_walking` run loops up to **3 requests × 5 stops × 3 arms = 45
cells**, every cell makes a grounded Gemini call **and** a `gpt-4.1-mini` judge via
`requests.post` to api.openai.com (serper arms add a per-source extractor). Run on
the host with no meter, re-run many times across Oct 10–11 while tuning the A/B →
thousands of unrecorded requests.

### 5. Reconciliation check (ticket item 4) — `reconcile_paid_api.py`
Reads `paid_api_calls` (DB, with jsonl-log fallback / `--log`), groups **billed**
(status 200) requests by normalized OpenAI model family, and compares to the
numbers Michael pastes from the dashboard (`--expected file.json`). Prints per-model
`metered_req / metered_usd` vs `dash_req / dash_usd / gap_req`, plus the total
UNMETERED gap. **Makes no paid call and no DELETE.**

### 6. Tests — `tests/test_local678_meter_httpx_aiohttp.py` (12 tests, all pass)
Using `httpx.MockTransport` (no network, no paid call) with the DB write and the
daily-limit check stubbed: a sync **and** async httpx POST to api.openai.com is
logged with the right model/usage/`$` (4.5e-5 for 100in/50out gpt-4o-mini); a
non-paid host is not logged; a streaming send is recorded without consuming the
caller's stream; `aiohttp.ClientSession._request` is wrapped; the host harnesses
carry the `meter_bootstrap` import; `meter_bootstrap.install_meter()` returns True
and is idempotent.

## Verification (no paid calls anywhere)
- `tests/test_local678_meter_httpx_aiohttp.py` — **12 passed**.
- Manual MockTransport check: the real **OpenAI SDK v2.48** (`client.chat.completions.create`)
  routed through the patched `httpx.Client.send` and was logged — the exact blind
  spot, closed.
- `reconcile_paid_api.py` on a synthetic log + expected file: model-family collapse,
  billed-only filter, UTC day boundary and gap math all correct.
- Regression: `test_local673_daily_paid_limit.py` (20), `test_local562_choke_point.py`
  + `test_local613_meter_and_cap.py` (18) all pass. All wired harnesses + the new
  scripts byte-compile.

## Not done (and why)
Editing the blind-spot production Dockerfiles / composes is a live-infra change
(rebuilds images, affects the running stack). It is documented in the audit with
the exact two-line fix per image, to apply with Michael's go-ahead. Per process
rules, DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md / .continuous_dev/STATUS.md
were not touched.

## Files
- `_meter/paid_api_meter.py` — httpx + aiohttp patches; idempotent install()
- `_meter/meter_bootstrap.py` — one-line host-process meter installer (new)
- `_wire_network_meter_into_host_harnesses.py` — idempotent wiring tool (new)
- 27 host harnesses — meter_bootstrap import inserted
- `reconcile_paid_api.py` — dashboard reconciliation (new)
- `tests/test_local678_meter_httpx_aiohttp.py` — tests (new)
- `submission_artifacts/local678/container_meter_audit.md`,
  `submission_artifacts/local678/oct10_11_task_audit.md` — audits (new)
