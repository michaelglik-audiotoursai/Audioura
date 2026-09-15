# CODE REVIEW GCS-1 — services changes deployed to production 2026-09-15

**Author of the code under review:** `GCloud_Storied` (Claude, Windows laptop).
**Reviewer:** Services Kiro.
**Status of the code:** ⚠️ **ALREADY DEPLOYED TO PRODUCTION.** This review is
after the fact, which is exactly why it has to be adversarial.

## Why this review exists

Michael's standing division of labour is: **Kiro writes the code, Claude reviews
it.** On 2026-09-15 that was violated — `GCloud_Storied` investigated, wrote, built
and deployed four services itself, with no Kiro involvement and therefore **no second
pair of eyes on anything before it reached production**.

The self-verification in the ClickUp comments is real, but it is the author checking
their own work. The purpose of this task is to get an independent reviewer onto code
that is already serving live traffic. **Assume nothing in the ClickUp comments is
true until you have checked it yourself.**

---

## What to review

Branch **`fix/cryptography-dep`**, commits **`81dd1cc`** and **`8f5879f`**, both
already merged into / pushed from `main`.

```bash
git fetch origin
git log --oneline 912cdd1..8f5879f
git diff 912cdd1..8f5879f
```

Four files:

| file | change | service | live image |
|---|---|---|---|
| `Dockerfile.cloudrun` | add `cryptography>=41.0.0` to the pip list | newsletter-processor | `audioura:v39` |
| `map_delivery_service.py` | return `track` from `/tours-near`, guarded on column existence | map-delivery | `audioura:v40` |
| `news_orchestrator_service.py` | `ensure_user()` + real `POST /user` and `GET /user/<id>` | news-orchestrator | `audioura:v41` |
| `api-gateway/main.py`, `api-gateway/gateway_routes.yaml` | delete the hardcoded `/user` stub; route `/user` to news-orchestrator | api-gateway, api-gateway-storied | `api-gateway:v35` |

Related ClickUp: `wdvrdaxywb`, `wdvrdaycef`, `wdvrday52p`.

---

## The specific things most likely to be wrong

These are the author's own suspicions about their own code. Start here, but do not
stop here.

### 1. SQL string interpolation in `map_delivery_service.py`

The track column is selected conditionally:

```python
""" % ("COALESCE(track, 'beta')" if _has_track_column(cur) else "'beta'"))
```

**This builds SQL with `%` string formatting.** The interpolated values are two
hardcoded literals, so there is no injection path today — but check that claim rather
than accepting it, and judge whether this pattern is acceptable in a file where other
queries are parameterised. If a later edit makes that expression depend on input, this
becomes an injection. Is there a formulation that cannot degrade that way?

### 2. `_TRACK_COLUMN` is a process-global cache that is never invalidated

```python
_TRACK_COLUMN = None      # module-level
```

Once the service decides the column is absent, **it will keep saying `'beta'` for the
life of the container**, even after the Storied orchestrator's self-healing `ALTER`
adds the column. Cloud Run scales to zero so a container usually does not live long —
but `map-delivery` may hold an instance for hours.

Questions: is a stale `False` here actually harmful? Would checking per-request be too
expensive? Is there a case where a container starts *before* the column exists and
serves wrong labels for a long time afterwards?

### 3. Does `ensure_user()` participate correctly in the caller's transaction?

In `news_orchestrator_service.py`, `ensure_user(cursor, secret_id)` is called on the
**same cursor and connection** as the subsequent `INSERT INTO article_requests`, and
the commit happens later, once, for both.

Check: if the `article_requests` insert fails after `ensure_user()` succeeded, does the
user row get rolled back too? **Is that the behaviour we want?** An orphan user row is
harmless; a rolled-back one means the next attempt re-inserts. Argue which is correct.

Also: two concurrent requests from the same new device. `ensure_user` does
`SELECT` then `INSERT ... ON CONFLICT DO NOTHING`. Is that safe under concurrency, or
is there a window? (The `ON CONFLICT` suggests yes — confirm it, and confirm the
`SELECT` before it is not creating a false sense of atomicity.)

### 4. Connection handling in the new `/user` endpoints

Both new endpoints use `try/except/finally` with `conn.close()` in `finally`. Check:

- On the exception path, is the transaction **rolled back** before close, or left to
  the driver? Is a half-applied transaction possible?
- `cursor.close()` is called on the success path only. Does that leak on the error path?
- Compare against how the rest of `news_orchestrator_service.py` does it — **consistency
  with the surrounding file matters more than my preference.**

### 5. The gateway route may shadow or be shadowed

`gateway_routes.yaml` gained:

```yaml
  - public_path: /user            methods: [POST]
  - public_path: /user/<secret_id> methods: [GET]
```

The old stub also handled `PUT` and `GET /user`, and used
`/user/<path:subpath>` (which matches multi-segment paths). The new routes use
`<secret_id>` (single segment) and drop `PUT` entirely.

**Check what the mobile app actually calls.** If anything calls `PUT /user/<id>` or a
multi-segment path, it now gets a 404 where it used to get a (fake) 200. That is
arguably an improvement, but it is a behaviour change nobody has verified against the
app. Look at `audio_tour_app/lib/` for every call to `/user` and `/sync`.

### 6. Was Beta really unchanged?

The author's claim is that `news_orchestrator_service.py` is "0 lines removed, 108
added" versus the running `v31`, and `map_delivery_service.py` differs from `v5` only
by 4 replaced lines. **Reproduce that comparison yourself** — do not take it on trust:

```bash
docker create --name x31 us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v31
docker cp x31:/app/news_orchestrator_service.py /tmp/nos_v31.py
docker rm x31
diff <(tr -d '\r' < /tmp/nos_v31.py) news_orchestrator_service.py
```

The images jumped a long way (`v5` → `v40`, `v31` → `v41`). Those images contain
**every** `.py` in the repo, not just the one file each service runs. Check whether any
*other* module that these services import at runtime changed between the old and new
image. `Dockerfile.cloudrun` does `COPY *.py`, so the blast radius is wider than the
diff of one file.

**This is the highest-value check on this page.** Beta is the control for the
Storied-vs-Beta comparison in `wdvrdaxxm9`; undetected drift in it invalidates every
tester judgement.

### 7. The `/sync` stub is still a lie

`api-gateway/main.py` still has:

```python
@app.route('/sync', methods=['POST', 'GET'])
def sync():
    return jsonify({"status": "success"})
```

Deliberately left alone as out of scope. Confirm nothing depends on it writing, and
say whether it should be fixed or removed.

---

## What to produce

**`SUBMISSION_GCS-REVIEW-1.md`** on your task branch, containing:

1. A **verdict per item 1–7** above: sound / defect / needs change. Say which.
2. Anything you found that is **not** on this list. The list is the author's own
   suspicions and is therefore biased toward what they already thought about.
3. For each real defect: the file and line, what breaks, and **a concrete failure
   scenario** — inputs or state that produce a wrong result. "This is fragile" is not a
   finding; "two requests from a new device within the same second cause X" is.
4. Your independent reproduction of the Beta-drift comparison (item 6), with the actual
   `diff` output pasted.
5. An explicit statement of **anything you could not check and why.** That is always an
   acceptable answer and is far more useful than a guess.

**Do not fix anything in this task.** If you find a defect, report it; the fix is a
separate dispatch so that the fix itself gets reviewed too. The one exception: if you
find something actively dangerous in production, say so at the very top of your
submission in capitals.

## PROCESS

1. **Review only. Change no production code in this task.** The deliverable is a
   document.
2. **Do not deploy anything.** All four services are live; a deploy is Michael's call.
3. Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
   or `GCLOUD_STORIED_START_HERE.md`.
4. **Verify by effect, not by reading.** Where a claim can be checked against a running
   container or a pulled image, check it. `exit=0` proves nothing.
5. **No `DELETE FROM audio_tours`.** If you touch the live DB at all, report row counts
   before and after. Read access is preferred; the Cloud SQL proxy plus
   `gcloud secrets versions access latest --secret=db-password` reaches it.
6. Commit on your task branch. Do not merge to `main` or `storied`.
7. If you disagree with a premise in this document, say so. It was written by the
   author of the code and may be wrong about its own work.
