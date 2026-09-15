# SUBMISSION — GCS-REVIEW-1

Adversarial code review of the 2026-09-15 services deploy by `GCloud_Storied`.

- **Agent:** Services Kiro
- **Base:** `main` = `912cdd1` (verified `git merge-base --is-ancestor 912cdd1 HEAD` → exit 0)
- **Change under review:** branch `fix/cryptography-dep`, commits `81dd1cc` and `8f5879f`
  (`fix/cryptography-dep` == `8f5879f`)
- **Method:** read the diff, then **verified by effect** — pulled the live Cloud Run
  images by digest, extracted every `.py`, diffed against the reviewed commit and against
  the pre-deploy Beta images, ran the interpreter inside the images, and hit the live
  read-only endpoints. Wrote no production code. Deployed nothing. No DB writes.

---

## ⚠️ Blocker on the brief itself

**`CODE_REVIEW_GCS-1.md` does not exist** — not in the working tree, not in any git tree
on any branch (`git log --all -- "*CODE_REVIEW_GCS-1*"` is empty), not as an untracked
file. The task says that file "is the full specification for this task … follow it," so
I could not follow it. **I reconstructed the seven review items from the inline brief and
the diff.** If the intended seven items differ from my reconstruction below, this review
may not line up one-to-one with what the author expected. This is the first thing to
reconcile.

My reconstructed item list:
1. cryptography dependency added to `Dockerfile.cloudrun`
2. `map_delivery_service.py` — `track` column detection + COALESCE SQL
3. `news_orchestrator_service.py` — `ensure_user` + `/user` POST + `/user/<id>` GET
4. `api-gateway` — removal of the in-gateway `/user` stub, new YAML routes
5. Auth / trust model on the new endpoints
6. **Did Beta actually stay unchanged?** (the highest-value check)
7. Schema / FK assumptions the changes depend on

---

## Verdicts at a glance

| # | Item | Verdict |
|---|------|---------|
| 1 | cryptography in Dockerfile | **Correct**, but see provenance caveat (fix not deployed to the service that needs it; it works only by luck) |
| 2 | map-delivery track detection | **Correct and safe.** One real minor defect: custom tours omit `track` |
| 3 | news-orchestrator user endpoints | **Correct.** Two minor issues (anonymous auto-register; `updated_at` never set) |
| 4 | gateway routing | **Correct.** Backend key valid, routes don't shadow |
| 5 | auth / trust model | **Sound.** Gateway strips `x-internal-service`; news path is fail-closed |
| 6 | **Beta unchanged?** | **Behaviourally yes for news-orchestrator; NOT byte-for-byte at the image level for either service.** 30 modules drifted in the news image and 49 in the map image — none on the runtime import path. See full analysis |
| 7 | schema / FK assumptions | **Verified against `migration/schema_dump.sql`** — all correct |

---

## The images actually live (ground truth)

```
map-delivery        audioura@sha256:3167ba78…  (rev map-delivery-00014-bdp, 2026-09-15)
news-orchestrator   audioura@sha256:3167ba78…  (rev news-orchestrator-00022-nqc, 2026-09-15)
api-gateway         api-gateway:v35            (both api-gateway and api-gateway-storied)
```

map-delivery and news-orchestrator now run **the same digest** `3167ba78`. Their
**pre-deploy** images were **different from each other**:

```
map-delivery  previous: sha256:24f0ceaa…  (rev …00013, built 2026-06-05)
news-orch     previous: sha256:068f6fea…  (rev …00021, built 2026-06-23)
```

`Dockerfile.cloudrun` does `COPY *.py /app/`, so each image carries **every** root `.py`,
and the CMD picks which one runs. That is exactly why item 6 matters.

### Provenance — does the deployed code match the reviewed commit?

Yes. After normalising encoding (the git blobs are UTF-16, the image files UTF-8) and
line endings:

- image `map_delivery_service.py` vs `8f5879f` → **identical except one comment char**
  (`# Regular tour — dual-read` em-dash vs `-` hyphen). Zero behavioural difference.
- image `news_orchestrator_service.py` vs `8f5879f` → identical after stripping
  non-ASCII (em-dashes + emoji in log strings) and a trailing newline.
- `api-gateway:v35` `main.py` and `gateway_routes.yaml` vs `8f5879f` → **identical**
  (ASCII-normalised).
- `cryptography` is genuinely installed in `3167ba78`: `docker run … python -c "import
  cryptography"` → **50.0.1**.

So "verify by effect" passes: the live images are the reviewed commit.

---

## Item 6 — Did Beta stay unchanged? (highest-value check)

**This is the item most likely to have been under-checked, and it was.** The author
diffed one file per service. I diffed the whole `COPY *.py` payload.

### news-orchestrator (Beta control for news): `068f6fea` → `3167ba78`

- Files **added**: `enhanced_tour_templates_fixed.py`, `geocode_stops.py`
- Files **removed**: none
- **Common files whose content differs: 30.** Full list:
  `api_call_logger.py, coordinate_requirements.py, enhanced_prompt_generator.py,
  enhanced_tour_templates.py, generate_tour_text.py, generate_tour_text_service.py,
  map_delivery_service.py, news_orchestrator_service.py, news_search_service.py,
  newsletter_link_extractor_service.py, patch_a77b_callsite.py,
  patch_a77b_manual_refresh.py, patch_a78_mic_permission.py, patch_a78_remove_import.py,
  patch_footer_v100.py, patch_newsletter_refresh_fix.py, patch_remind_v102.py,
  patch_remind_v102b.py, poi_inclusion_exceptions.py, polly_tts_service.py,
  single_file_app_builder.py, text_to_index_service.py, tour_delivery_service.py,
  tour_editing_phase2.py, tour_editing_service.py, tour_generation_modernized.py,
  tour_type_detector.py, version_api.py, voice_control_service.py, voice_nlp_service.py`

**Does any of this reach news-orchestrator at runtime?** news-orchestrator's CMD runs
`news_orchestrator_service.py`, whose only local import is `entitlements`.
- `entitlements.py` is **byte-identical** (SHA-256 match) between `068f6fea` and
  `3167ba78`, and it imports only stdlib + psycopg2.
- Neither `geocode_stops` nor `enhanced_tour_templates_fixed` is imported by
  `news_orchestrator_service.py` (grep = empty).

**Verdict:** the news image drifted in 30 modules, but **none of them are on the
news-orchestrator import path**, so Beta *news* behaviour changes only by the two
intended edits. The runtime blast radius of the drift is nil **for this service**.

### map-delivery (Beta control for tours): `24f0ceaa` → `3167ba78`

The map image was **much** older (built 2026-06-05, 238 root `.py` files vs 199 now):
- **Added (5):** `credential_encryption.py, entitlements.py, geocode_stops.py,
  migrate_credentials_encrypt.py, tour_worker_service.py`
- **Removed (44):** mostly `debug_*.py` / `*_fixed.py` scratch files, **plus one real
  module: `translation_service.py`.**

map-delivery's CMD runs `map_delivery_service.py`, whose only local import is
`blobstorage` (`R2BlobStorage`). **`blobstorage.py` is byte-identical across all three
images** (`24f0ceaa`, `068f6fea`, `3167ba78` — same SHA-256). So again, none of the
drift is on the map-delivery runtime path.

**Verdict:** map-delivery Beta behaviour changes only by the intended `track` edit.

### The honest bottom line on "byte-for-byte unchanged"

The controlling ClickUp task `wdvrdaxxm9` states the **hard requirement**: *"Beta's
behaviour must be byte-for-byte unchanged."*

- **Behaviour:** unchanged apart from the intended `track` field and the intended user
  endpoints — I verified the runtime import closures don't touch any drifted module.
- **Image contents:** **not** unchanged. Both Beta services now serve a different image
  than before, containing dozens of modified sibling modules. The author's "diffed one
  file, no drift" conclusion is **too strong** — it happens to be harmless *only because
  none of the drift is imported by the two running entrypoints*. That is a property that
  has to be re-checked on every future shared-image deploy, not an invariant. A tester
  comparing Storied vs Beta is safe today; the safety is incidental, not structural.

**Recommendation:** if "byte-for-byte" is meant literally, Beta services should be pinned
to their prior digest and only the entrypoint they run should change — or the shared-image
model should be dropped for the control. At minimum, document that the control's image
changed and why it's behaviourally inert.

---

## Item 1 — cryptography in `Dockerfile.cloudrun`

**Verdict: the change is correct, but it did not need to be part of this deploy to fix
`/submit_credentials`, and it was NOT deployed to the service that serves that endpoint.**

- The diagnosis is right: `dh_service_simple.py` imports `cryptography.hazmat…`
  **inside a function** (line ~156), so a container without the package boots, passes
  `/health`, then 400s on every `/submit_credentials`. `requirements.txt` declared
  `cryptography>=41.0.0` (line 9) but the Dockerfile installs a hand-maintained pip list
  and never reads `requirements.txt`, so the declaration bought nothing. Accurate.
- The fix (`cryptography>=41.0.0` in the pip list) is present and effective:
  `3167ba78` has cryptography 50.0.1.

**But:** `/submit_credentials` is served by **newsletter-processor**, and
newsletter-processor was **not** redeployed here. It still runs
`audioura@sha256:34738e15…` (revision `newsletter-processor-00012-gxg`, **2026-09-03**).
I ran the interpreter in that exact digest: **it already has cryptography 50.0.1.** So
`/submit_credentials` is fine in production today — but that is because the 09-03 image
already carried the package, not because of this 09-15 deploy. The four services that got
the new image (`3167ba78`) are map-delivery and news-orchestrator, which do **not** serve
`/submit_credentials`.

**Net:** the Dockerfile edit is a good permanent fix (any *future* rebuild-and-deploy of
newsletter-processor will now include cryptography deterministically). But the commit
message frames it as *the* fix that unblocked `/submit_credentials`; the endpoint was
already unblocked by the 09-03 image. Worth correcting the record so nobody believes this
deploy is what fixed credentials, and so newsletter-processor is eventually redeployed
onto an image built from the fixed Dockerfile.

---

## Item 2 — map-delivery track detection

**Verdict: correct and safe. One real minor defect.**

The `%s AS track` / `COALESCE(track, 'beta')` construction:
- The `%` interpolation splices only **hardcoded string literals**
  (`"COALESCE(track, 'beta')"` or `"'beta'"`), never user input → **no SQL injection**.
- `_has_track_column()` does a real `information_schema` catalog read, cached in a module
  global `_TRACK_COLUMN`. Correct: schema presence doesn't change per-request, and the
  cache value is a plain bool, so cross-connection reuse is safe. Degrading to `'beta'`
  when the column is absent is the right fail-safe (avoids a 500 for both tracks).
- Column count matches unpacking: `SELECT id, tour_name, request_string, lat, lng,
  number_requested, %s AS track` = 7 values, unpacked into 7 names. ✓

**Verified by effect** (read-only GET `/tours-near/42.36/-71.06?radius=50`):
```
count = 227
first tour keys: distance_km, id, is_custom, lat, lng, name, popularity,
                 request_string, track, type      ← track now present
track distribution: beta=225, storied=2
```
This directly closes the original defect from `wdvrdaxxm9` (`track field present? False`).
The column exists in prod, is populated, and older rows COALESCE to `beta`.

**DEFECT (minor): custom tours omit `track`.** In `get_tours_near_location`, the
`custom_tours` result branch builds its dict **without** a `track` key (the second
`nearby_tours.append({...})` has no `track`). Original tours have it; custom tours don't.
Because the app's `trackLabel()` maps *missing ⇒ Stable/beta*, **every custom tour will
be reported as Beta regardless of which engine produced it.** Not a crash, but it
undercuts the very attribution this change exists to provide. I could not exercise it
live (0 custom tours in the test radius), but it is unambiguous in the source.
*Failure scenario:* a Storied-track user creates a custom tour, opens the map, sees it
labelled Stable — and any Storied-vs-Beta quality comparison silently miscounts it.

---

## Item 3 — news-orchestrator `ensure_user` + `/user` endpoints

**Verdict: correct. Two minor issues.**

- `ensure_user` + the `article_requests` INSERT run in one transaction and commit
  together, so `article_requests_secret_id_fkey` is satisfied atomically. ✓
- `/user` POST: `users` upsert is `ON CONFLICT (secret_id) DO UPDATE SET app_version`
  (idempotent), then reads the row back before claiming success (kills the old
  "fabricated success" bug), commits, returns. FK ordering for the `coordinates` insert
  is correct (users row written first, same txn). ✓
- `/user/<id>` GET returns an honest **404** when absent. **Verified by effect:** live
  GET on a nonexistent id → **HTTP 404** (not a stubbed success). ✓

**Issue 3a (minor): `coordinates` grows unbounded — but this is pre-existing, by design.**
The `coordinates` INSERT has no `ON CONFLICT`, so every `/user` POST with coordinates
appends a row. This is **not a regression**: the legacy `user_api_with_cors.py` did the
exact same plain INSERT, and the `coordinates` table has its own serial `id` +
`created_at`, i.e. it is a location *history log*, not a current-location row. So the new
code faithfully matches the established contract. Flagging only so it isn't mistaken for
new behaviour; if unbounded growth is undesirable that's a separate, older ticket.

**Issue 3b (minor): trusted-internal path can auto-register `secret_id='anonymous'`.**
In `generate_news`, external callers with missing/`'anonymous'` secret_id are rejected
401 *before* `ensure_user`. But the **trusted-internal** branch (valid
`X-Internal-Service`) does **not** re-validate secret_id (it defaults to `'anonymous'`),
then reaches `ensure_user(cursor, 'anonymous')`. If newsletter-processor ever calls
without a real secret_id, a `users` row with `secret_id='anonymous'` is created and
articles are attributed to it. Low severity (internal caller presumably always sends a
real id), but it's an unvalidated write path.

**Issue 3c (cosmetic): `updated_at` never set.** `users.updated_at` exists in the schema;
neither the upsert nor `ensure_user` touches it, so it stays NULL. `/user/<id>` GET
doesn't return it either. Harmless, but the column is now dead.

---

## Item 4 — gateway routing

**Verdict: correct.**

- The old in-gateway handlers (`/user/<path:subpath>` and `/user`, both returning a
  hardcoded `{"status":"success","rows_affected":1}`) are removed and replaced by a
  comment explaining the gateway has no DB attachment. Good — that stub is exactly what
  produced the "sync claims success, writes nothing" bug.
- New YAML routes `/user` (POST) and `/user/<secret_id>` (GET) both point to
  `backend: news-orchestrator`. **`news-orchestrator` is a defined key in the manifest
  `backends:` block** (line 23) and is already used by existing news routes, so
  `BACKENDS[backend_key]` cannot KeyError. ✓
- Routes register via `app.add_url_rule`; Flask resolves by rule specificity, and the two
  `/user` rules differ in path and method, so no shadowing. ✓
- Both routes are `auth: api_key`; the handler defaults auth to `api_key` (fail-closed)
  when omitted. ✓

---

## Item 5 — auth / trust model

**Verdict: sound.**

- Gateway `main.py` (line ~159) strips `x-internal-service` (and `host`,
  `content-length`, `transfer-encoding`) from **inbound** client headers before proxying.
  So a public client cannot forge the internal-service trust that
  `news_orchestrator_service.generate_news` relies on. ✓
- news `generate_news` is **fail-closed**: missing/`anonymous` id → 401; quota-check
  exception → 503; over quota → 429. The trust check uses `hmac.compare_digest`. ✓
- Backends are `--no-allow-unauthenticated` (only the gateway is public, per the file
  header); my direct probes required a gcloud identity token. ✓

---

## Item 7 — schema / FK assumptions

**Verdict: every assumption verified** against `migration/schema_dump.sql`.

- `users_pkey PRIMARY KEY (secret_id)` → `ON CONFLICT (secret_id)` is valid. ✓
- `article_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES users(secret_id)`
  → confirms the FK that made news fail for unregistered devices; `ensure_user` addresses
  it. ✓
- `coordinates_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES users(secret_id)`
  → the `/user` POST coordinates insert has its own FK; users-first ordering satisfies it.
  ✓
- `users` columns used (`secret_id, app_version, created_at`) all exist; `updated_at`
  exists but is unused (Issue 3c). ✓
- `audio_tours.track` is created by the Storied orchestrator's self-healing ALTER; prod
  confirms it exists and is populated (beta=225, storied=2). ✓

---

## Other things I found

- **The cryptography commit's premise is stale** (Item 1): production credentials were
  already working on the 09-03 image; this deploy did not touch newsletter-processor.
- **Shared-image model is a standing hazard for the Beta control** (Item 6): "diff one
  file" is not sufficient evidence of no drift when `COPY *.py` bakes in the whole repo.
- **`translation_service.py` disappeared from the map image** across the June→September
  gap. Irrelevant to map-delivery runtime, but if any service still CMDs that module and
  gets moved onto `3167ba78`, it would fail to start. Not in scope of these 4 services;
  flagging for whoever owns image hygiene.

## Concrete failure scenarios for the real defects

1. **Custom-tour mislabelling (Item 2 defect).** Storied user makes a custom tour →
   `/tours-near` returns it with no `track` key → app shows "Stable" → Storied-vs-Beta
   comparison miscounts it as Beta. Silent, ongoing, corrupts exactly the data the deploy
   was meant to produce.
2. **Anonymous internal attribution (Issue 3b).** newsletter-processor calls
   `/generate_news` without a secret_id → a `users` row `secret_id='anonymous'` is
   auto-created and every such article FK-attaches to it → quota/attribution for those
   articles is meaningless.
3. **False confidence in the cryptography fix (Item 1).** Someone rebuilds
   newsletter-processor from an *older* Dockerfile (pre-`81dd1cc`) believing "crypto was
   fixed in the image" → `/submit_credentials` 400s again, because the guarantee lives in
   the Dockerfile, and only this image (not newsletter-processor) was rebuilt from it.

---

## What I could NOT check

- **`CODE_REVIEW_GCS-1.md`** — absent everywhere. The seven items above are my
  reconstruction; a genuine item may be missing or mis-scoped.
- **`/user` POST and `/generate_news` by effect** — both write to the DB and the process
  forbids test writes / I have no gateway API key. I verified GET `/user/<id>` (404 path)
  and `/tours-near` (track field) live, and everything else by image+source inspection.
- **`/submit_credentials` end-to-end** — it ingests real credentials and writes; I did
  not exercise it. I only proved the newsletter-processor image contains cryptography.
- **Whether `api-gateway:v35` is itself part of commit `8f5879f`'s intended deploy** — the
  brief only named the two `audioura` bumps. v35 content matches `8f5879f`, but I did not
  confirm the deploy checklist expected an api-gateway bump too.
- **Runtime import *closure* beyond one hop** — I checked direct imports of the two
  entrypoints (+ `entitlements`, `blobstorage`) and confirmed those dependencies are
  byte-identical; I did not exhaustively trace every transitive dynamic/`__import__`.
- **The other 3 hostnames' live behaviour** (`api-gateway-storied`, tour orchestrators) —
  out of scope for these four changes.

---

*Review only. No production code changed. Nothing deployed. No DB writes. Temporary image
extractions used for the diff were deleted.*
