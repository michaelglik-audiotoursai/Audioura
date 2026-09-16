# SUBMISSION — GCS-QUOTA1: raise tester tour quota to 10/day

**Agent:** Services Kiro
**Branch:** `gcs-quota1-tester-quota` (from HEAD `5e53c56`; `git merge-base --is-ancestor 5e53c56 HEAD` → exit 0, base OK)
**ClickUp:** `wdvrdayd3c` (urgent)
**Authorised by:** Michael, 2026-09-15 — "we need to allow 10 tours a day per tester".

## Summary

One production write, exactly as scoped: `UPDATE users SET tours_per_day_override = 10 WHERE
secret_id = 'USER-773827679'` (Michael's iPhone). **Rows affected = 1.** No `plans` change, no other
table/column, no `DELETE`/`INSERT`/DDL, no code/deploy/restart. `users` row count unchanged (22 → 22).
No secret value was printed at any point.

No code or deploy needed: `entitlements.py:68` already resolves the quota as
`COALESCE(u.tours_per_day_override, p.tours_per_day)`, so setting the per-user override to 10 takes
effect on the next request.

## Connection

Cloud SQL Auth Proxy → `audiotours-migration:us-central1:audioura-db`, db `audiotours`, user `admin`.
- Proxy: `cloud-sql-proxy v2.14.1` started with `--gcloud-auth` (gcloud user creds; ADC was not
  configured, so the default-credentials path failed and `--gcloud-auth` was used instead), listening
  on `127.0.0.1:5432`.
- Password: read from Secret Manager secret `db-password` (`latest`) straight into an environment
  variable inside the shell command and passed to psycopg2. **Never printed.**
- Writes: a single committed transaction for the one `UPDATE` (with a guard that rolls back unless
  exactly 1 row is affected). Everything else was autocommit read-only `SELECT`s.
- Cleanup: proxy process stopped; the proxy binary and all helper scripts/logs were deleted. `git
  status --porcelain` is empty apart from this submission. None of them are committed.

---

## Step 1 — Row counts and before-state (read-only)

```
SELECT count(*) FROM users;
count
22
```

```
SELECT plan_id, tours_per_day FROM plans ORDER BY plan_id;   -- before
plan_id | tours_per_day
free    | 1
paid    | 10
tester  | 100
```

```
SELECT secret_id, plan, tours_per_day_override FROM users WHERE secret_id = 'USER-773827679';
secret_id       | plan | tours_per_day_override
USER-773827679  | free | (null)
```

The row **exists** (plan `free`, override NULL), so the update is valid and will match 1 row.

Note: Michael's iPhone is on the **`free`** plan, not `tester`. Setting the per-user override to 10
raises just this user to 10/day via the COALESCE, without touching `plans` (raising `free` would give
every anonymous user 10/day, which is exactly what the boundaries forbid).

## Step 2 — The update (the only write)

```
UPDATE users SET tours_per_day_override = 10 WHERE secret_id = 'USER-773827679';
rows affected: 1        -- COMMITTED
```

After-SELECT:

```
SELECT secret_id, plan, tours_per_day_override FROM users WHERE secret_id = 'USER-773827679';
secret_id       | plan | tours_per_day_override
USER-773827679  | free | 10
```

## Step 3 — Candidate testers for LEAD to confirm with Michael (read-only, no writes)

`users` has columns: `secret_id, app_version, is_deleted, app_uninstalled, created_at, updated_at,
plan, tours_per_day_override`. All 22 rows, most-recent first:

```
SELECT secret_id, plan, tours_per_day_override, created_at, app_version
  FROM users ORDER BY created_at DESC LIMIT 25;

secret_id            | plan   | override | created_at                  | app_version
USER-773827679       | free   | 10       | 2026-09-15 00:34:53.349174  | 2.3.2+23      <- Michael iPhone (SET this task)
USER-974226925       | tester | (null)   | 2026-05-28 04:00:15.113823  | 1.2.9+65      <- tester plan = 100/day already
USER-816194559       | free   | (null)   | 2026-05-09 22:03:42.003046  | 1.2.9+31
USER-652478439       | free   | (null)   | 2026-05-08 17:42:56.069924  | 1.2.9+30
USER-873019399       | free   | (null)   | 2026-05-08 17:15:59.335813  | 1.2.9+29
USER-185792635       | free   | (null)   | 2026-05-08 16:42:48.061674  | 1.2.9+28
test_user_debug      | free   | (null)   | 2026-05-05 00:30:08.559935  | 0.0.0.3
USER-996271755       | free   | (null)   | 2026-05-01 20:40:37.933090  | 1.2.9+24
USER-1777510725070   | free   | (null)   | 2026-04-30 02:29:53.499251  | Error loading+Error loading
test_translation     | free   | (null)   | 2025-12-21 04:16:34.064704  | unknown
final_test_user      | free   | (null)   | 2025-12-05 18:33:30.473465  | unknown
test_user_fix        | free   | (null)   | 2025-12-05 18:27:12.381160  | unknown
USER-1764816788212   | free   | (null)   | 2025-12-04 18:18:43.726979  | 1.2.8+115
test_user_boston_globe | free | (null)   | 2025-11-13 17:22:13.664290  | unknown
PHASE2-TEST-USER     | free   | (null)   | 2025-11-13 03:55:16.730635  | unknown
USER-12345678        | free   | (null)   | 2025-11-10 06:20:00.975806  | unknown
test_user_newsletter | free   | (null)   | 2025-11-07 16:15:41.448513  | unknown
test_user_apple      | free   | (null)   | 2025-11-07 15:02:41.530512  | unknown
test_user_spotify    | free   | (null)   | 2025-11-07 15:02:41.530512  | unknown
test_user            | free   | (null)   | 2025-10-29 03:47:27.273105  | unknown
USER-241354860       | free   | (null)   | 2025-07-29 01:34:40.622001  | unknown
USER-281301397       | tester | (null)   | 2025-07-23 14:27:47.843827  | unknown      <- tester plan = 100/day already
```

(22 rows returned — the full table; the `LIMIT 25` was not reached.)

**Reading for LEAD (I did NOT guess identities and updated none of these):**
- `USER-773827679` — Michael's iPhone, app `2.3.2+23`, matches the task. Override now 10. ✔ done.
- **Michael's Android** (tonight's test) has a *different* `secret_id` than the iPhone. There is **no**
  other row with a 2.3.x app_version in this table — so his Android device does not appear to have
  registered a user row yet, **or** it maps to one of the `unknown`/older `USER-…` rows. This needs
  Michael to confirm the exact `secret_id` before anyone sets an override. Do not assume.
- Yury / Gregory / Igor — not identifiable from the data alone. Candidates are the `USER-…` rows above.
  Two rows are already on the **`tester`** plan (`USER-974226925`, `USER-281301397`), which grants
  100/day by plan — they may not need a per-user override at all.

**Tours used today per user:** could not be reported — see surprise below.

## Step 4 — Re-report row count (must be unchanged)

```
SELECT count(*) FROM users;
count
22
```

Unchanged: 22 before, 22 after.

---

## Acceptance criteria

1. **`tours_per_day_override = 10` for `USER-773827679`** — shown by the after-SELECT in Step 2. ✔
2. **Rows affected = 1, and users row count identical before/after** — 1 row; 22 → 22. ✔
3. **`plans` untouched** — before and after both:
   ```
   plan_id | tours_per_day
   free    | 1
   paid    | 10
   tester  | 100
   ```
   Identical. ✔
4. **Candidate list for identifying Michael's Android and the other testers** — Step 3. ✔

## PROCESS compliance
- Live production DB; no `DELETE`/`INSERT`/DDL; only one `UPDATE` to `users.tours_per_day_override`.
  Row counts reported before (22) and after (22).
- No code change, no deploy, no service restart.
- No secret value printed.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `GCLOUD_STORIED_START_HERE.md`, or `BUILD_NUMBERS.md`.
- Proxy binary and helper scripts/logs deleted; none committed.

## Surprise / stop-and-report

**`usage_counters` is completely empty.** `SELECT DISTINCT kind FROM usage_counters;` and
`SELECT ... FROM usage_counters ORDER BY updated_at DESC LIMIT 15;` both returned **zero rows**.
So the "tours used today per user" figure requested in Step 3 cannot be produced — there is no usage
data recorded in this table at all. This may mean quota counting is tracked elsewhere (e.g. by
counting `audio_tours`/`tour_requests` rows per day rather than in `usage_counters`), or the counters
simply have not been written to on this instance. Flagging rather than guessing. This did not affect
the required write, which is complete and verified.

Second (minor) note: Michael's iPhone is on the **`free`** plan, not `tester`; the per-user override
is the correct lever here and was used exactly as scoped. If the intent is instead to move testers to
the `tester` plan (100/day) or `paid` (10/day), that is a different, unauthorised change — flagging for
LEAD, not done.
