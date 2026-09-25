# GCS-COST1 — Beta vs Storied real cost & wall time per tour (production)

**Task:** `wdvrdayj16` (requested by Storied_Tours, 2026-09-22)
**Agent:** Services Kiro · **Base:** main = `912cdd1`
**Run date:** 2026-09-24 · **Window:** last 30 days (≈ 2026-08-25 → 2026-09-24)
**Mode:** READ-ONLY. `SELECT`-only DB access via Cloud SQL Auth Proxy; Cloud Run logs read-only.
Proxy binary and all temp files deleted afterward. DB password pulled from Secret Manager
into process memory only — never printed.

**Data sources**
- Production Cloud SQL: `audiotours-migration:us-central1:audioura-db`, db `audiotours`
  (Postgres 15, RUNNABLE), user `admin`.
- Cloud Run request + application logs, project `audiotours-migration`, region `us-central1`.

---

## TL;DR — the honest headline

**The production data cannot deliver a real Beta-vs-Storied cost comparison, because Beta cost is
not instrumented and the cost ledger is effectively unused.** Over the last 30 days:

- `cost_ledger` holds **exactly one** `tour_generate` row in its entire history — and that row is a
  **Storied** Cloud Run tour, not Beta.
- **Beta emits no cost telemetry at all** (no `cost_ledger` rows, no `[COST_METER]` log lines).
- **Wall time is not recorded in the database** (`tour_requests.finished_at` is `NULL` for every
  tour in the window). Wall time below is **derived from Cloud Run request logs** and labelled as a
  proxy.

So the four figures are reported with the `n` they actually have (frequently `n=0` or `n=1`), and the
gaps are stated plainly rather than filled with estimates.

---

## 1. Cost per tour — `cost_ledger`, `operation_type='tour_generate'`, last 30 days

```sql
-- operation types present in the last 30 days
SELECT operation_type, count(*) FROM cost_ledger
WHERE created_at >= now() - interval '30 days'
GROUP BY operation_type ORDER BY 2 DESC;
-- result: spine_generate=2, tour_generate=1

-- tour_generate cost stats (30 days)
SELECT count(*) n, round(avg(our_cost_usd),6) mean, min(our_cost_usd) mn,
       max(our_cost_usd) mx,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY our_cost_usd) median
FROM cost_ledger
WHERE operation_type='tour_generate' AND created_at >= now() - interval '30 days';
-- result: n=1, mean=0.219565, min=0.219565, max=0.219565, median=0.219565

-- whole-history extent of tour_generate rows
SELECT count(*), min(created_at), max(created_at)
FROM cost_ledger WHERE operation_type='tour_generate';
-- result: count=1, min=max=2026-09-16 01:23:55 UTC
```

**Cost per tour, ledger, 30 days:**

| Track | n | mean | median | min | max |
|---|---|---|---|---|---|
| Beta | **0** | — | — | — | — |
| Storied (cloud) | **1** | $0.219565 | $0.219565 | $0.219565 | $0.219565 |

**Can the ledger be split by track?** No. `cost_ledger` has **no `track` column**. Its columns are:
`id, operation_type, user_id, our_cost_usd, cache_hit, job_id, breakdown (jsonb), created_at,
description, ceiling_breach`. `description` is `NULL` and `breakdown` only holds
`{"llm","tts","search"}` sub-costs — none encode a track. The single row was attributed to a track
**only** by cross-referencing its `job_id` (`70bd141f…`) to the Cloud Run service that logged it
(see §2): it was written by **`tour-generator-storied`**. So the ledger cannot be split by track on
its own; the one row is Storied.

That single row **is** the same data point LEAD captured on 2026-09-16 (Logan, 4 stops,
`tour_generate $0.219564` + `spine_generate $0.008967`). It is one Storied Cloud Run tour, **not** a
Beta baseline and not a distribution.

**Beta cost is uninstrumented.** No `cost_ledger` rows and no `[COST_METER]` lines were produced by
the Beta service `tour-generator` (or by `tour-modernized`, `tour-modernized-storied`, `tour-worker`)
in the window — see §2. There is no production cost figure for Beta to report.

---

## 2. Wall time per tour

### 2a. Database — NOT RECORDED

```sql
-- tour_requests in the last 30 days
SELECT source, status, count(*),
       count(*) FILTER (WHERE finished_at IS NOT NULL AND started_at IS NOT NULL) AS with_both_ts
FROM tour_requests
WHERE created_at >= now() - interval '30 days'
GROUP BY source, status ORDER BY 3 DESC;
-- result: source='orchestrator', status='started', count=5, with_both_ts=0
```

Every `tour_requests` row in the window has `status='started'` and `finished_at IS NULL`, so a
`started_at → finished_at` delta is unavailable. (`audio_tours` records only a single `created_at`,
no start timestamp.) All-time, the 159 rows that do have both timestamps produce nonsense deltas
(mean ≈ 2 days, max ≈ 318 days) — `finished_at` is stamped by later status updates, not at generation
completion. **Wall time per tour is not recorded in the database.**

### 2b. Cloud Run request logs — derived proxy (the second source, as permitted)

Both generators are async: `POST /generate` returns in ~2 s after enqueuing the job, then the client
polls `GET /status/<job_id>` on a ~10 s cadence until done. Request logs contain no status body, so
completion is taken as the **last** `/status` poll for each job. **Wall time here = (last `/status`
poll) − (`POST /generate`)**, a proxy that slightly over-estimates true completion by up to one poll
interval (~10 s). It matched LEAD's independent ~7 min reading on the Logan job (see below), which is
why it is trusted as an order-of-magnitude figure, not a precise one.

Log filter used (per service), via `gcloud logging read`:
```
resource.type="cloud_run_revision"
AND logName:"run.googleapis.com%2Frequests"
AND resource.labels.service_name="tour-generator"           # and "tour-generator-storied"
--freshness=30d --limit=1000
```

**Beta — `tour-generator`, 30 days:** 21 jobs (21 `POST /generate`, all HTTP 200).

| n | mean | median | min | max |
|---|---|---|---|---|
| 21 | **53.7 s** | 50.4 s | 20.2 s | 103.3 s |

**Storied — `tour-generator-storied`, 30 days:** 5 jobs (5 `POST /generate`, all HTTP 200).

| n | mean | median | min | max |
|---|---|---|---|---|
| 5 | **115.8 s** | 42.7 s | 12.3 s | 394.9 s |

Storied per-job (start UTC → wall): `73438937` 107.1 s · `85a8ac01` 12.3 s ·
`70bd141f` **394.9 s** · `4a17c275` 42.7 s · `803ce45b` 22.3 s. The 394.9 s job is the Logan tour
(`70bd141f`, the same job as the one ledger cost row); ~6.6 min ≈ LEAD's "~7 min", which validates
the method. The Storied mean is dominated by that one long job (n=5), so the **median (42.7 s)** is
the more representative central figure here.

The `POST /generate` latency alone (Beta 1.8 s; Storied 1.9–6.1 s) is **not** wall time — it is just
the enqueue call — and must not be read as tour duration.

---

## 3. Stops per tour — `audio_tours.stops_count`, last 30 days

```sql
SELECT track, count(*) FROM audio_tours
WHERE created_at >= now() - interval '30 days' GROUP BY track ORDER BY track;
-- beta=18, storied=12

-- storied stops
SELECT count(*) n, round(avg(stops_count),3) mean,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY stops_count) median,
       min(stops_count) mn, max(stops_count) mx
FROM audio_tours
WHERE created_at >= now() - interval '30 days' AND track='storied';
-- n=12, mean=4.917, median=4.5, min=2, max=9

-- beta stops
SELECT count(*) n, count(*) FILTER (WHERE stops_count>0) n_nonzero,
       round(avg(stops_count),3) mean, min(stops_count) mn, max(stops_count) mx
FROM audio_tours
WHERE created_at >= now() - interval '30 days' AND track='beta';
-- n=18, n_nonzero=0, mean=0, min=0, max=0
```

| Track | n | stops mean | stops median | min | max |
|---|---|---|---|---|---|
| Beta | 18 | **0** (not populated) | 0 | 0 | 0 |
| Storied | 12 | 4.917 | 4.5 | 2 | 9 |

**Beta does not populate `stops_count`** — all 18 rows are 0 (and all-time, 272 of 325 Beta rows are
0). So **cost per stop cannot be computed for Beta** on either axis (no cost, no stops). For Storied,
stops are recorded but per-tour cost is not, so a Storied cost-per-stop cannot be computed from
production data either (the one ledger cost row's tour had 4 stops → $0.055/stop for that single tour,
n=1).

---

## 4. Storied on Cloud Run — the four figures (cloud-to-cloud)

Same window, Storied services only (`tour-generator-storied`, and the one `cost_ledger` row it wrote):

| Figure | n | mean | median | min | max | Source |
|---|---|---|---|---|---|---|
| Cost / tour | 1 | $0.219565 | $0.219565 | $0.219565 | $0.219565 | `cost_ledger` |
| Wall time / tour | 5 | 115.8 s | 42.7 s | 12.3 s | 394.9 s | Cloud Run request logs (proxy) |
| Stops / tour | 12 | 4.917 | 4.5 | 2 | 9 | `audio_tours.stops_count` |
| Cost / stop | 1 | $0.0549 | — | — | — | ledger cost ÷ that tour's 4 stops |

The three different `n` values (1 cost, 5 wall, 12 stops) reflect three different instruments over the
same period, not the same tours; they are not row-aligned.

---

## 5. What is NOT recorded (stated explicitly, not estimated)

1. **Beta cost per tour** — no `cost_ledger` rows and no `[COST_METER]` log lines from the Beta
   service. Not instrumented; **cannot be reported**.
2. **Wall time per tour in the DB** — `tour_requests.finished_at` is `NULL` for every tour in the
   window; `audio_tours` has only `created_at`. Wall time exists **only** as a Cloud Run request-log
   proxy (§2b).
3. **Track split inside `cost_ledger`** — no `track` column; not derivable from `description`/
   `breakdown`. Only linkable to a track via `job_id` → Cloud Run service.
4. **Beta stops per tour** — `stops_count` is left at 0 for Beta rows.
5. **`usage_counters`** — confirmed empty/unused; not used as a source (as noted in the brief).

---

## 6. Comparison table — Beta vs Storied (cloud) vs Storied (Mac Mini host)

| Metric | Beta (Cloud Run) | Storied (Cloud Run) | Storied (Mac Mini host)¹ |
|---|---|---|---|
| Cost / tour | **not recorded** (n=0) | $0.2196 (n=1) | $0.187 |
| Wall time / tour | 53.7 s mean / 50.4 s median (n=21, log-derived proxy) | 42.7 s median / 115.8 s mean (n=5, proxy) | 237 s |
| Stops / tour | not populated (n=18 all 0) | 4.9 mean / 4.5 median (n=12) | 4 |
| Cost / stop | not computable | $0.055 (n=1, 4-stop tour) | $0.047 |
| Tokens | not captured here | not captured here | 27k |

¹ Mac Mini **host** (not cloud) figures are the given context (4-stop building tours), reproduced for
comparison only — not measured in this task.

**Reading the table:** the intended Beta-vs-Storied cost comparison **cannot be made from production
data** — the one usable production cost point is Storied ($0.2196 for a 4-stop tour), close to the
Mac Mini host's $0.187, while **Beta has zero cost instrumentation**. On the wall-time proxy, Beta's
cloud tours (median ~50 s) and Storied's shorter cloud tours are in the tens-of-seconds range; the
Storied mean is pulled to 116 s by a single ~6.6 min outlier (the Logan tour). Both are far below the
Mac Mini host's 237 s, but the two are measured by different instruments (log proxy vs host timing)
and are not directly equivalent.

---

## BLOCKING QUESTION for LEAD / Storied_Tours

The production database **cannot** produce the requested Beta-vs-Storied cost distribution: Beta
writes no cost telemetry, and `cost_ledger` contains a single `tour_generate` row in its whole history
(a Storied tour). To get a real comparison, one of these is needed — which do you want?

1. **Instrument Beta** to write `cost_ledger` / `[COST_METER]` like Storied does, then re-measure
   after real traffic accumulates (separate, non-read-only task).
2. **Run a controlled A/B**: generate N identical tours on both `tour-generator` and
   `tour-generator-storied` and read the `[COST_METER]` lines (would require permission to generate
   tours — out of scope for this READ-ONLY task).
3. Accept that today only **Storied cloud** has a production cost point (n=1), and treat cost parity
   as unmeasurable for Beta until (1) lands.

## Method / reproducibility notes
- Connection: Cloud SQL Auth Proxy v2.14.1 on `127.0.0.1:5433`, authed with a short-lived
  `gcloud auth print-access-token` (`--token`), because Application Default Credentials were not set.
  Queries run with `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` (psycopg2
  `set_session(readonly=True)`).
- Password read at runtime from Secret Manager `db-password`; held in memory, never logged.
- All statistics use Postgres `avg` / `percentile_cont(0.5)` / `min` / `max` / `count`; wall-time
  aggregates computed in Python over the request-log job spans.
- Cleanup: proxy process stopped, `cloud-sql-proxy.exe` and temp logs deleted, all probe scripts
  removed. No writes of any kind were issued to the database or to any Cloud Run service.
