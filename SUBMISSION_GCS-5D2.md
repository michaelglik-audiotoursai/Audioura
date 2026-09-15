# SUBMISSION — GCS-5D2

**Agent:** Services Kiro
**Base:** storied @ `0de517c` (verified: `git merge-base --is-ancestor 0de517c HEAD` → exit 0)
**Branch:** `kiro/gcs-5d2` (HEAD = `0de517c8cdd5d0c080b2f5dc4ab073667f7848f9`)
**Authorisation:** Michael, 2026-09-15 ~14:22 — "Yes, deploy to Preview" (Preview only).
**Result:** **STOPPED at the first failure, before any mutation.** No images built or
pushed, no Cloud Run service created, no IAM changed, no gateway redeployed.

---

## Outcome in one line

`bash deploy_gcs5_tour_editing.sh --apply` aborted in the **very first step**
(computing the `tour-editing` image tag) because the `tour-editing` image does not
yet exist in Artifact Registry, so the script's `next_tag` guard fired:

```
FAILED: could not list tags for tour-editing — pass a tag flag
```

Per the GCS-5D2 rules ("Stop at the first failure. No retries with changes, no
workarounds... No edits to the script or any file. No extra flags."), I did **not**
add `--editing-tag`, edit the script, or otherwise work around it. This is a genuine
blocker that needs a LEAD/Michael decision. See "Blocking question" below.

---

## The answer to GCS-5D's question WAS validated (read-only, no stubs)

Before `--apply`, I ran the full `--dry-run`, which executes the same read-only proofs
the deploy relies on (pull the running `api-gateway:v35`, extract `/app/main.py` and
`/app/gateway_routes.yaml`, SHA256 gate, route-diff, in-process editing-route test).
All passed **in this environment, against the real running image**:

- Running image pulled: `api-gateway:v35`, digest
  `sha256:a47117c141f34caa426c28830cf087b913d4c272a74a0dcf6a1d72ae0b3e3481`.
- **SHA256 gate PASS.** Staged `main.py` (from `git show origin/main:api-gateway/main.py`)
  normalised SHA256 = `ef7cf1adc15eef5626d6c53cd8a5ca17109f7cde9d8fd9b871f8d781175fab18`,
  **identical** to `/app/main.py` extracted from the v35 image. This matches the SHA
  LEAD reported. → The `origin/main` staging is NOT an "unverified live run on origin";
  it is proven byte-identical to the code already live. GCS-5D's concern is resolved.
- **Route-diff PASS.** v35 = 25 route-methods / 6 backends; new = 29 / 7. Added exactly:
  `+GET /tour/<tour_id>/download`, `+GET /tour/<tour_id>/job-status/<job_id>`,
  `+POST /tour/<tour_id>/update-multiple-stops`, `+POST /tour/<tour_id>/update-stop`,
  `+backend tour-editing`. Nothing removed.
- **Editing-route test PASS.** Against the staged v35 `main.py`: all 4 routes registered
  and fail-closed (no-key=401, wrong-key=401, good-key!=401).
- Target gateway(s): **`api-gateway-storied` only** (Stable not in target list; no `--stable`).
- `GIT_SHA=0de517c  RELEASE_TAG=v2t-gcs5r`.

The dry-run did NOT surface the tag failure because in dry-run `next_tag` returns the
hard-coded default (`vNEXT`) without querying the registry; the registry query only runs
under `--apply`.

---

## Full `--apply` output (aborted)

```
== Preflight
  GIT_SHA=0de517c  RELEASE_TAG=v2t-gcs5r
  Target gateway(s): api-gateway-storied   (Preview default; Stable only with --stable)

FAILED: could not list tags for tour-editing — pass a tag flag
```

Exit status: 1. The failure occurs at:

```bash
# next_tag(): highest existing vN + 1
highest=$(gcloud artifacts docker tags list "${REPO}/tour-editing" ... )
[ -n "$highest" ] || fail "could not list tags for ${image} — pass a tag flag"
```

Confirming cause (read-only):

```
$ gcloud artifacts docker tags list \
    us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing --format="value(tag)"
ERROR: (gcloud.artifacts.docker.tags.list) NOT_FOUND: Requested entity was not found.
```

The `tour-editing` image path has never been pushed (this is its first-ever deploy), so
there is no `vN` to increment.

---

## Image tags used

- `tour-editing:vN` — **none.** Aborted before build; no tag was resolved or pushed.
- `api-gateway:vN` — **none pushed.** (Would have been `v36` per dry-run; not built.)

## tour-editing URL and ready revision

- **Not created.** `gcloud run services describe tour-editing` → `Cannot find service [tour-editing]`.

## Stable and Preview gateway revision/image — before and after (UNCHANGED)

| Service | Before | After |
|---|---|---|
| Preview `api-gateway-storied` | `api-gateway-storied-00002-6kb` / `api-gateway:v35` | `api-gateway-storied-00002-6kb` / `api-gateway:v35` |
| Stable `api-gateway` | `api-gateway-00022-t88` / `api-gateway:v35` | `api-gateway-00022-t88` / `api-gateway:v35` |

Both gateways are byte-for-byte identical before and after. Stable untouched. Preview untouched.

## No-key curl results

**Not run.** The no-key curls are a post-deploy verification; the deploy never happened,
and the editing routes are not yet baked into the running Preview gateway (still v35), so
they would still 404. Running them now would only re-confirm the pre-deploy state. Deferred
until after a successful `--apply`.

---

## Blocking question for LEAD / Michael

The script is authoritative as written (per the GCS-5D2 answer), and it explicitly fails
closed on an unknown image with the instruction "pass a tag flag". But GCS-5D2 also forbids
adding flags or editing the script. These two collide on the **first-ever** deploy of the
`tour-editing` image, which by definition has no prior `vN`.

**Please choose one and I will execute exactly that, nothing more:**

- **(A)** Authorise the single documented flag for a first push:
  `bash deploy_gcs5_tour_editing.sh --apply --editing-tag v1`
  (still Preview-only, no `--stable`, no file edits). `next_tag` already honours a forced
  tag via `--editing-tag`, so this is the script's own intended path for a new image, not a
  workaround of a defect. The gateway would still auto-resolve to `v36`.
- **(B)** If the `tour-editing` repo/first tag is meant to be created out-of-band first,
  do that (or point me to the step) and I will re-run plain `--apply`.

I stopped rather than pick, because choosing a tag value or editing the tag logic is exactly
the "no workarounds / no edits" line GCS-5D2 drew, and the previous session's failure was
precisely an unlogged judgment call. Everything upstream of the tag (base, SHA gate,
route-diff, route test, target=Preview-only) is already proven green above.
