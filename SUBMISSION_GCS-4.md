# SUBMISSION — GCS-4

Fixing the defects that `GCS-REVIEW-1` found in the 2026-09-15 services deploy.

- **Agent:** Services Kiro
- **Base:** `main` = `912cdd1` (verified `git merge-base --is-ancestor 912cdd1 HEAD` → exit 0)
- **Task branch:** `gcs-4-services-fixes`
- **ClickUp:** `wdvrdaxywb`, `wdvrdaycef`
- **Method:** fixed the code, then **verified by effect** against locally built
  containers (the `Dockerfile.cloudrun` production image), hitting live endpoints and
  reading the DB. **Deployed nothing. No production database was touched** — every DB in
  the verification harness was a throwaway `postgres:15-alpine` container.

---

## A note on the base — the fix commit was never on `main`

The task calls the code under repair "commit `8f5879f` on `main`." In this worktree
`8f5879f` is **not** an ancestor of `main`/`912cdd1`:

```
git merge-base --is-ancestor 8f5879f HEAD  → exit 1   (NOT an ancestor)
git branch --contains 8f5879f              → fix/cryptography-dep only
```

`fix/cryptography-dep` = `8f5879f`, and its parent chain is
`8f5879f → 81dd1cc → 912cdd1`. So the deployed services fix sits **directly on top of my
base but was never merged into `main`**. My worktree at `912cdd1` therefore did *not*
contain the `track` code or the `/user` endpoints at all — repairing "the defects in
`8f5879f`" against a bare `912cdd1` would have meant repairing code that wasn't there.

**What I did:** cherry-picked `81dd1cc` + `8f5879f` onto my branch as an explicit
baseline commit (`e67d4d2`), then applied the three defect fixes on top (`e0f8379`). This
makes the repair a clean, reviewable diff against the exact code the review examined, and
it means merging this branch brings both the deployed fix *and* its repairs onto `main`
together. Flagging it because it changes what "port to storied" means (see the port
section): `main` is getting the whole change, not just the deltas.

Commits on the branch:

| commit | what |
|--------|------|
| `e67d4d2` | import deployed fix (`81dd1cc`+`8f5879f`) as repair baseline |
| `e0f8379` | the three defect fixes + the drift-check tool |

---

## Defect 1 — custom tours now report the real `track`

**File:** `map_delivery_service.py`, `get_tours_near_location`.

### Where a custom tour's track comes from, and why

`custom_tours` has **no engine record of its own** — no `track` column, only
`original_tour_id` (FK → `audio_tours.id`; see `create_tour_editing_schema.sql` and the
`CREATE TABLE IF NOT EXISTS custom_tours` in `map_delivery_service.py`). A custom tour is
*derived* from an original, so the honest source of its track is **the original tour's
track**: a tour edited from a Storied original is a Storied tour.

I inherit it with a `LEFT JOIN audio_tours o ON o.id = c.original_tour_id` and
`COALESCE(o.track, 'beta')`, guarded by the same `_has_track_column()` catalog check the
originals query already uses. **No schema change** — I chose inheritance over adding a
`custom_tours.track` column because:

- it is *authoritative*, read from the source row, not a guess or a value that could go
  stale if a custom tour's provenance were ever re-pointed;
- it needs no additive migration and no backfill of the existing custom rows;
- it matches how the originals path already resolves track.

`LEFT JOIN` (not inner) so a custom tour whose original was deleted still lists and
degrades to `'beta'`. When `audio_tours.track` is absent entirely (a DB that never ran
the Storied self-healing ALTER), the query selects the literal `'beta'` — same fail-safe
as the originals path, so the endpoint never 500s for the missing column.

### Live evidence (against a running `map_delivery_service.py` container)

Seed: three originals near Nice — `track='beta'` (1001), `track='storied'` (1002),
`track=NULL` (1003). Then three custom tours derived from them.

`GET /tours-near/43.70/7.27?radius=50`, custom rows only:

```
id                        original_tour_id  is_custom  track
custom_test_gcs4_storied  1002              True       storied   ← inherited Storied
custom_test_gcs4_beta     1001              True       beta      ← inherited Beta
custom_test_gcs4_orphan   (null)            True       beta      ← COALESCE fail-safe
```

Raw JSON keys on the Storied custom tour confirm the key is actually present:
`distance_km, id, is_custom, lat, lng, name, original_tour_id, popularity,
request_string, track, type` → `track = "storied"`.

**Column-absent path** (second container against a DB with no `track` column):
`GET /tours-near` → **HTTP 200**, every row (original and custom) `track=beta`, no 500.

Before the fix these three custom rows had **no `track` key at all**, which the app maps
to Stable/Beta — the exact silent mislabelling the review described.

**Row-count discipline (throwaway harness DB):** custom_tours `0 → 3` (fixtures created,
ids captured at creation) `→ 0` (fixtures deleted, captured on `DELETE ... RETURNING`).
The `custom_tours` schema on `main` has no `is_test` column, so there was nothing to
confirm `is_test` on; the rows were identified by their `custom_test_gcs4%` id prefix and
removed, and the whole harness was then torn down with `docker compose down -v`.

---

## Defect 2 — internal path can no longer auto-register `secret_id='anonymous'`

**File:** `news_orchestrator_service.py`, `generate_news`.

External callers with missing/`'anonymous'` id were already rejected 401 before
`ensure_user`. The **trusted-internal** branch (valid `X-Internal-Service`) was not
re-validating, so the default `'anonymous'` reached `ensure_user(cursor, 'anonymous')` and
created a `users` row that every such article FK-attaches to.

**Decision — reject, don't attribute to a service principal.** A batch news article
always originates from a real subscriber's newsletter, so the internal caller
(newsletter-processor) already holds that user's `secret_id` and simply has to send it.
Substituting a synthetic principal would collapse per-user attribution and quota — the
very thing this endpoint exists to preserve. Rejecting fail-closed (HTTP 400) forces the
real id through. "Trusted internal" means *skip the quota gate*, not *skip identifying the
user*.

### The red test (criterion 2: break it and show it go red)

I ran the **pre-fix** `news_orchestrator_service.py` (extracted from baseline `e67d4d2`,
mounted into the same production image) against a fresh DB and called the internal path
with no secret_id:

```
PRE-FIX  users before: 0
PRE-FIX  POST /generate-news  (X-Internal-Service valid, no secret_id)
PRE-FIX  users after:  secret_id='anonymous', app_version='auto-registered'   ← RED
```

The damaging write happened and committed (the request then 500'd only because a
downstream peer is absent in the minimal harness — irrelevant; the `users` row was
already created by `ensure_user`, exactly as the review predicted).

### Green, after the fix (same call, fixed container)

```
POST /generate-news  (X-Internal-Service valid, no secret_id)      → HTTP 400
POST /generate-news  (X-Internal-Service valid, secret_id=anonymous) → HTTP 400
users after both calls: 0 rows   (no 'anonymous' row)
service log: "[QUOTA] Internal call with missing/anonymous secret_id — refusing (fail-closed)"
```

And to show the path still *works* with a real id: an internal call with
`secret_id='USER-ENSURE-TEST'` reached `ensure_user` and created that user row (with
`updated_at` set — see Defect 3).

---

## Defect 3 — `users.updated_at` is now written and returned

**File:** `news_orchestrator_service.py`.

- `ensure_user` insert: `INSERT INTO users (secret_id, app_version, updated_at) VALUES
  (%s, %s, NOW())`.
- `/user` upsert: sets `updated_at = NOW()` on both the INSERT and the
  `ON CONFLICT DO UPDATE`.
- `GET /user/<id>`: `SELECT ... , updated_at` and returns it as an **additive** field.

### Live evidence

```
POST /user {secret_id:USER-GCS4-TEST, app_version:1.2.3} → 200
DB: updated_at IS NOT NULL → t
GET /user/USER-GCS4-TEST → {"app_version":"1.2.3","created_at":"...","secret_id":"...",
                            "status":"success","updated_at":"2026-09-15T03:57:43..."}

re-POST {app_version:1.2.4} → 200
DB: app_version=1.2.4, updated_at advanced 03:57:43 → 03:57:55   (DO UPDATE path works)

internal generate-news {secret_id:USER-ENSURE-TEST} → user row created, updated_at = t
```

---

## Criterion 4 — no existing field, name, or type changed

The full `git diff` of both files (in the branch) is additive only:

- news GET response keeps `secret_id`, `app_version`, `created_at` unchanged and only
  *adds* `updated_at`.
- `/tours-near` original-tour objects are unchanged; custom-tour objects only *gain* a
  `track` key (older builds ignore unknown keys).
- No column renamed or retyped; the SQL only *adds* `updated_at` to INSERT lists and a
  `track` expression to SELECTs.

Older clients keep working.

---

## Criterion 5 / Beta-drift — the reusable check (`tools/beta_image_drift_check.py`)

The review's headline correction stands: "diffed one file, no drift" is too strong,
because `Dockerfile.cloudrun` does `COPY *.py /app/` and the CMD only *selects* the
entrypoint. Whether sibling-module drift matters depends entirely on whether any drifted
module is on the **runtime import path** of the entrypoint that actually runs. That is
incidental, not structural, and must be re-checked on **every** shared-image deploy.

I wrote that procedure down as `tools/beta_image_drift_check.py`. Given two image refs
and an entrypoint it:

1. extracts every root `.py` from both images,
2. computes the transitive **local**-import closure of the entrypoint (static AST walk,
   limited to modules actually present in the image),
3. diffs the two images file-by-file (SHA-256), and
4. classifies each drifted/removed file as **ON** the import path (behavioural risk) or
   **OFF** it (behaviourally inert for this entrypoint). Exit code is non-zero iff drift
   lands on the import path, so it is CI-usable.

Usage (discover the live digest with
`gcloud run services describe … --format='value(spec.template.spec.containers[0].image)'`,
then):

```
python tools/beta_image_drift_check.py \
    --new  <freshly-built-image> \
    --old  <deployed-image@sha256:…> \
    --entrypoint news_orchestrator_service.py
```

**Self-test** (ran it here against the built image on both entrypoints; it independently
reproduces the review's import-closure finding):

```
news_orchestrator_service.py  →  import closure = {news_orchestrator_service.py, entitlements.py}
map_delivery_service.py        →  import closure = {map_delivery_service.py, blobstorage.py}
```

Those are exactly the closures the review found ("only local import is `entitlements` /
`blobstorage`"). I could **not** pull the actual Cloud Run digests here (no gcloud auth in
this environment) — that step is documented in the script header for whoever runs it
pre-deploy. That is the one part of criterion 5 I verified by tooling+method rather than
against the live registry.

---

## `translation_service.py` — confirmed nothing in the shared image CMDs it

The only Dockerfile that runs it is `translation-service/Dockerfile`
(`COPY translation_service.py blobstorage.py ./`, `CMD ["python", "translation_service.py"]`)
— its **own dedicated image**, built from the `translation-service/` context, not the
shared `Dockerfile.cloudrun`. `Dockerfile.cloudrun` has no per-service CMD for it (the CMD
is overridden per Cloud Run service), and neither `map_delivery_service.py` nor
`news_orchestrator_service.py` imports it. So its disappearance from the *map* image is
behaviourally inert: nothing in that image ever ran it, and the live translation service
ships from a separate image. No action needed for these four services.

---

## The `storied` port

The same three fixes are wanted on `storied`. I inspected `port/services-fixes-to-storied`
@ `5b38605` before writing this.

**Good news:** `5b38605`'s `news_orchestrator_service.py` has **byte-identical target
shapes** for all three defects (same `ensure_user` INSERT, same `/user` upsert and GET,
same `generate_news` internal branch). So:

- **Defect 2 and Defect 3 port verbatim** — the exact same edits apply. (Storied's news
  file has an unrelated `send_file` compat shim near the top; it does not touch any line I
  change.)

**Defect 1 needs care, but less than feared:**

- ⚠️ The storied warning is about `/tours-near`'s **originals** query, which on storied
  carries `AND (is_test IS NOT TRUE) AND original_tour_id IS NULL` — filters `main` has
  never had. **Do not touch those.** My Defect-1 change does not: it only rewrites the
  **custom_tours** query.
- Storied's **custom_tours** query (in `5b38605`) is the *same defective block as main* —
  it selects `original_tour_id` but builds the dict with **no `track`**, and it has **no
  `is_test` / `original_tour_id IS NULL` filter** of its own. So porting my LEFT-JOIN
  change there adds the inherited `track` without dropping any storied-only filter, because
  there is none on that query to drop.
- Net port for Defect 1 on storied: apply the identical
  `LEFT JOIN audio_tours o ON o.id = c.original_tour_id` + `COALESCE(o.track,'beta')`
  rewrite (with the column-absent `else` branch) to the storied custom_tours query, and
  unpack the extra `track` value in its loop. Leave the originals query and its
  `is_test`/`original_tour_id IS NULL` filters exactly as they are.

A careless "just re-apply the main diff" would be safe here **only** because storied's
custom query has no extra filters — but the safe move is still to hand-apply to the
custom block and eyeball the originals query to confirm its filters survive, since that is
the conflict `5b38605` already resolved once.

I did **not** commit to `storied` (PROCESS #6). The port is described, not performed.

---

## Disagreements with the review

None substantive — the four findings reproduce. Two clarifications:

- The review filed Defect 2 as "low severity (internal caller presumably always sends a
  real id)." I'd rate it a touch higher: it is an *unvalidated write on the trusted path*,
  and the whole point of this deploy is trustworthy attribution. Rejecting is cheap and
  removes the footgun entirely, so I fixed it as fail-closed rather than documenting it as
  acceptable.
- The review's Item 1 (cryptography / newsletter-processor provenance) is out of scope for
  GCS-4's four services and I did not act on it beyond keeping the `81dd1cc` Dockerfile
  edit in the baseline. Its "correct the record" recommendation stands for whoever owns
  the deploy.

---

## What I could NOT verify

- **Live Cloud Run image diff for criterion 5.** No gcloud auth in this environment, so I
  could not pull the deployed digests. I reproduced the review's *method* with
  `tools/beta_image_drift_check.py` and confirmed the import closures match; the actual
  registry pull is documented for the deploy step.
- **`/generate-news` full happy path.** In the minimal harness the downstream news peers
  (`news-generator`, etc.) are absent, so a *successful* internal call 500s after the
  `users`/`article_requests` writes. That was enough to prove the write behaviour (row
  created / refused), which is what the defects are about, but not an end-to-end article
  generation.
- **The storied port by effect.** Described from source inspection of `5b38605`, not run —
  committing/verifying on storied is out of scope per PROCESS #6.

---

*No production code deployed. No production database touched. All verification containers
and the throwaway DBs were torn down (`docker compose down -v`), the temporary pre-fix
extraction was deleted, and the built image was removed. No untracked `.py` remains in the
`Dockerfile.cloudrun` build context (root `*.py`); the drift-check tool lives under
`tools/` and is committed.*
