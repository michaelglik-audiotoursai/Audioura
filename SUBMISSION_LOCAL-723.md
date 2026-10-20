# SUBMISSION — LOCAL-723: Test spend must never trip the listeners' daily limit

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-723-listener-limit` (from `subscribed` = `836504d4`)
**code_sha:** `1c99ebd333ee0692d7f190150bb55a16a9ffe21c`
**Base verified:** `git merge-base --is-ancestor 836504d4 HEAD` → exit 0.

## Problem (LEAD, 2026-10-20 17:54)

`DAILY_PAID_LIMIT_USD=8` (LOCAL-673) blocked Michael's phone stack although
listeners had spent $0 today. The limit summed `paid_api_calls` by `service`
(`DAILY_PAID_LIMIT_SERVICES`), and test/bench containers run the **same**
services. The LOCAL-721/722 task containers also copied the shared generator's
env **including `HOSTNAME`**, so the meter labelled their calls as the shared
host (`c6de8edad79d`, `2ecd782373ea` in LEAD's by-host breakdown). Test spend
therefore counted against the listeners' limit.

## Fix

The limit now counts **proven listener spend only**.

1. **Additive migration** — `migrations/local723_add_role_column.sql`:
   `ALTER TABLE paid_api_calls ADD COLUMN IF NOT EXISTS role text;` (nullable;
   old rows NULL) plus a partial index
   `idx_paid_api_calls_listener ON paid_api_calls (ts) WHERE status = 200 AND role = 'listener'`.
   No existing column or row is changed.

2. **Role on every row, proven not labelled** — `_meter/paid_api_meter.py`:
   `_meter_role()` returns `'listener'` **only** when
   `METER_ROLE == 'listener'` **AND** `METER_ROLE_TOKEN` (env) is non-empty
   **AND** it equals the stripped contents of the file at `METER_ROLE_TOKEN_FILE`.
   The token file is bind-mounted **only** into the shared listener containers
   (at `/opt/meter/role_token`, a path NOT inside `_meter`, so a test container
   that mounts `_meter` does not receive it).

   **Why a copied env cannot qualify:** a test container that copies the listener
   env inherits `METER_ROLE` and the token *value*, but it does **not** inherit
   the bind-mounted file. The `open(path)` either fails (absent) or the contents
   mismatch, so `_meter_role()` returns `None`. The row is written with
   `role = NULL` and is never counted. **Fail safe for listeners:** any error, no
   proof, or `METER_ROLE != listener` → `None` → not counted; test spend can
   never trip the limit. (Mechanism = the task's documented option B: an explicit
   `METER_ROLE_TOKEN` checked against a file mounted only into the shared
   containers.)

3. **Real hostname** — `_real_hostname()` returns `socket.gethostname()`, never
   the copyable `HOSTNAME` env. `_db_write` now stores the real hostname and the
   `role`.

4. **Role-scoped limit query** — `_query_today_total_usd` sums
   `status = 200 AND role = 'listener'` for the NY calendar day. The
   `DAILY_PAID_LIMIT_SERVICES` service-list scope is retired (it is no longer
   read).

5. **Override** — `docker-compose.subscribed-local.yml`: the four listener
   services (`tour-generator`, `tour-orchestrator`, `polly-tts-1`,
   `translation-service`) get `METER_ROLE=listener`,
   `METER_ROLE_TOKEN=${METER_ROLE_TOKEN}`,
   `METER_ROLE_TOKEN_FILE=/opt/meter/role_token`, and a read-only bind-mount
   `/Users/micha/Audioura/listener_role.token:/opt/meter/role_token:ro`.
   `DAILY_PAID_LIMIT_USD` stays **8** (the TEMP 14 on the Mac is a local,
   uncommitted edit; this branch keeps 8). The stale `DAILY_PAID_LIMIT_SERVICES`
   lines are removed.

   **LEAD action at merge (never committed):** create
   `/Users/micha/Audioura/listener_role.token` containing a random secret, and
   set `METER_ROLE_TOKEN=<same secret>` in `~/Audioura/.env`. The token is an
   anti-spoof proof of container identity, not a dangerous secret — it only
   decides whether a row counts toward a spend cap.

   `docker compose -f docker-compose-master.yml -f docker-compose.subscribed-local.yml config`
   parses cleanly (exit 0): 4 services with `METER_ROLE`, 0
   `DAILY_PAID_LIMIT_SERVICES`, `DAILY_PAID_LIMIT_USD: "8"`.

## Files changed

- `migrations/local723_add_role_column.sql` (new)
- `_meter/paid_api_meter.py`
- `docker-compose.subscribed-local.yml`
- `tests/test_local723_listener_role.py` (new)
- `run_local723_proof.py` (new — live-proof harness)

## Unit tests

`tests/test_local723_listener_role.py` — 16 tests, no DB, no network:

- `_meter_role`: listener when env+file match; **copied-env-without-file is not
  listener**; wrong file contents not listener; no role env; non-listener label;
  missing token; missing file path; empty file never matches; case/whitespace
  tolerance on the label.
- `_real_hostname`: uses `socket.gethostname`, ignores `HOSTNAME`; never raises.
- `_record`: the JSONL row carries `role` (listener when proven, NULL for a
  copied-env test container).
- `_query_today_total_usd`: SQL filters `status = 200 AND role = 'listener'`,
  params = `(day,)`, and no longer references `service = ANY`/
  `DAILY_PAID_LIMIT_SERVICES`.

Run (new + existing LOCAL-673 enforcement contract):

```
$ python3 -m pytest tests/test_local723_listener_role.py tests/test_local673_daily_paid_limit.py -q
...................................                                      [100%]
35 passed in 0.49s
```

The 19 LOCAL-673 tests still pass, confirming the enforcement contract (off /
under / over / network-refused / cache / day-boundary / fail-open / alert / the
AWS Translate + Polly paths) survives the role scoping.

## Live proof (own container only; budget ≤ $0.50 — actual **$0.000002**)

DB: `development-postgres-2-1` (network `development_default`, alias
`postgres-2`, db `audiotours`). No `audioura-*` container was touched/renamed;
no `docker compose -p audioura`; the test container is `--rm` and named
`local723-proof-test`.

**Row counts (additive migration):**

| point | paid_api_calls | audio_tours |
|---|---|---|
| baseline (before migration) | 54738 | 498 |
| after migration (ALTER + CREATE INDEX) | 54740* | 498 |
| after proof call (+1 legit test row) | 54741 | 498 |

\* the +2 between baseline and post-migration is live listener traffic from the
running shared stack during the read, **not** the migration — a migration adds
no rows. After migration, all existing rows had `role = NULL`
(`<NULL>|54740`), and the listener-scoped today total was `$0`.

**Negative path (the core case) — copied env, no mounted file, HOSTNAME dropped:**

```
[proof] real hostname (socket.gethostname) = 'local723-proof-box'
[proof] METER_ROLE env                      = 'listener'
[proof] METER_ROLE_TOKEN set?               = True
[proof] METER_ROLE_TOKEN_FILE               = '/opt/meter/role_token'
[proof] token file exists in THIS container? = False
[proof] meter computed role for THIS container = None  (expect None -> not counted)
[proof] OpenAI status=200   usage={'prompt_tokens': 14, 'completion_tokens': 1, ...}
[proof] my row (id,kind,status,usd,host,role) = (54741, 'openai', 200, Decimal('0.000002'), 'local723-proof-box', None)
[proof] listener spend today (role='listener') = $0.000000  (my test call is NOT in it)
```

One `gpt-4.1-nano` call (status 200, **$0.000002**) wrote row 54741 with
`role = NULL` and the **real** hostname `local723-proof-box` (not a copied
shared HOSTNAME). The listener-scoped total stayed `$0` — the test call is not
counted.

**Positive path (read-only / rolled back) — a proven listener row WOULD count:**

```
BEGIN
INSERT ... role='listener', usd=0.010000
listener_total_with_synthetic|0.010000     <- counted
ROLLBACK
listener_total_after_rollback|0            <- reverted, no DB pollution
final_counts paid_api_calls|54741
```

A synthetic `role='listener'` row made the limit query total `$0.010000` (it IS
counted), then ROLLBACK reverted it to `$0`. This confirms the shared generator
(which mounts the token file and so stamps `role='listener'`) **is** counted,
without recreating the shared containers (LEAD does that at merge).

**Cleanup:** no leftover `local723` containers; the only persistent change is
the one legitimate $0.000002 test row (54741) and the additive `role` column +
index.

## Process notes

- Branched from `subscribed` HEAD (`836504d4`); base ancestry verified.
- When copying the shared env for the test container, **HOSTNAME was dropped**
  (the container set its own `--hostname`). No env capture is committed.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`, or
  `.continuous_dev/`. No phones.
