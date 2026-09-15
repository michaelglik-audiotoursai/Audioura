# SUBMISSION_GCS-7 — port LOCAL-474 (empty `tour_type` ⇒ classify, not 400) to Beta

**Agent:** Services Kiro
**Branch:** `kiro/gcs-7`  **Base:** `main` = `912cdd1` (verified ancestor of HEAD)
**ClickUp:** `wdvrdaxxm9` (Storied_Tours' deploy request, item 2). Michael approved 2026-09-15 15:42.
**Status:** Staged only. Nothing pushed to a registry, no Cloud Run service updated.

---

## 1. Summary

The app sends `tour_type: ''` whenever its parser recognises no category keyword (every
restaurant request). Stable/Beta reject that with `400 "location and tour_type are required"`.
The fix `ea41026` lives on `storied` only. This task ports the **minimum** equivalent to
`main` and stages an **overlay** deploy for Beta so the Beta control does not drift.

The only behaviour change shipped: **an empty or missing `tour_type` is classified instead of
rejected.** Every previously-working request behaves exactly as before.

---

## 2. What changed and why (three files, 32 insertions / 5 deletions)

I re-derived the `main` equivalent rather than porting storied's hunk verbatim, because
storied's `generate_tour_text.py` hunk (+77) is written against its 17k-line file and pulls in
machinery `main` does not have.

### 2.1 `tour_orchestrator_service.py` (`/generate-complete-tour` gate, ~:1110)
Relaxed the gate to require `location` only. Empty/missing `tour_type` is logged and forwarded
downstream (the orchestrator sends `tour_type` on to the generator's `/generate`; both gates
had to change or the orchestrator would forward `''` and be rejected by the generator).

### 2.2 `generate_tour_text_service.py` (`/generate` gate, ~:169)
- `tour_type = data.get('tour_type') or ''` — coerce `None`/absent to `''`.
- Gate requires `location` only; empty `tour_type` logged, deferred to the classifier.

### 2.3 `generate_tour_text.py` (`generate_tour_text()` entry, ~:601)
Single defensive normalization at function entry:

```python
if tour_type is None:
    tour_type = ''
```

**Why this is the whole fix on `main`, and what I deliberately did NOT port.**
`main`'s crash is `tour_type.lower()` on `None` (`_classify_tour_category` :384, plus title/
conclusion builders :850, :1708, :1813). Coercing `None → ''` at the single entry point makes
every one of those calls safe. An empty string then flows into `_classify_tour_category`
(:377), which already accepts it and **always returns a concrete category** (it defaults to
`'walking'`; a Bread-Thyme location classifies as `restaurant` via the location keyword).

Storied's hunk also adds `_infer_category_log_line`, `_build_unclassifiable_evidence`, a
`_LAST_CLEAN_FAIL_EVIDENCE` global, and an "unclassifiable_request" clean-fail guard. **I did
not port those.** On `main` the classifier can never return empty/None, so the guard is dead
code, and `_LAST_CLEAN_FAIL_EVIDENCE` does not exist in `main` (`grep` returns nothing) — adding
it would be new, unrequested behaviour, i.e. drift. The task said to port the minimum needed to
avoid the crash and to say which I chose and why. I chose the minimum: entry normalization only.

Full diff: see `git diff` on the branch (also pasted in §7).

---

## 3. The overlay images (no rebuild of `main`)

Two Dockerfiles build overlays **on the exact images Beta runs**, copying only the LOCAL-474
files so nothing else in `/app` can change:

`Dockerfile.local474.orchestrator`
```dockerfile
FROM us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22
COPY tour_orchestrator_service.py /app/
```
`Dockerfile.local474.generator`
```dockerfile
FROM us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36
COPY generate_tour_text.py generate_tour_text_service.py /app/
```

**Tag choice:** `audioura:v22-local474` and `audioura:v36-local474`, in the same
`services/audioura` repo. The `-local474` suffix on the exact base tag makes the lineage
obvious (this is v22/v36 + LOCAL-474 and nothing else) and avoids advancing the shared
`audioura` integer sequence, which is a standing hazard (a bare `vNN` bump could collide with
or be mistaken for an unrelated build).

### 3.1 Base ↔ `origin/main` byte-identity (confirms the overlay premise)
The three files inside the base images have git blob OIDs identical to `origin/main`
(so `COPY`-ing my edited files changes exactly and only those files):

| file | base image OID | `origin/main` OID |
|---|---|---|
| `tour_orchestrator_service.py` (v22) | `4af4fcd0…` | `4af4fcd0…` ✓ |
| `generate_tour_text.py` (v36) | `3ec53328…` | `3ec53328…` ✓ |
| `generate_tour_text_service.py` (v36) | `c86c6840…` | `c86c6840…` ✓ |

*(computed with `docker cp` of the base file + `git hash-object`; matches LEAD's finding.)*

---

## 4. Acceptance criteria

### AC1 — Red → green on a container built from the overlay image (local Postgres)

Method: base image = "before" (byte-identical to `main`), overlay image = "after". Containers
run on the local `development_default` network (reaching the existing healthy local Postgres and
peers) on spare host ports; the standing `development-*` stack was never touched. Probes run
from inside the containers so the JSON error bodies are visible.

**Generator `/generate`** (`probe_generator.py`, note the endpoint is async → 200 = accepted):

| case | BEFORE (v36 base) | AFTER (v36-local474) |
|---|---|---|
| `tour_type:""` | `400 {"error":"location and tour_type are required"}` | **`200 {"job_id":…,"status":"queued"}`** |
| `tour_type` absent | `400 …required` | **`200 …queued`** (no 500 from `None.lower()`) |
| `location:""` | `400 …required` | **`400 {"error":"location is required"}`** |

After-container logs for the empty case:
```
[LOCAL-474] Empty tour_type — deferring category to classifier in generate_tour_text()
  [Bug2Fix] tour_type='' suppressed for intent analysis (pre_category='restaurant'); using location only
Detected tour category: RESTAURANT
```

**Orchestrator `/generate-complete-tour`** (`probe_orchestrator.py`; sent with no `user_id`,
which isolates the location/tour_type gate — the entitlements `401` sits *after* that gate):

| case | BEFORE (v22 base) | AFTER (v22-local474) |
|---|---|---|
| `tour_type:""` | `400 …required` | **`401 auth_required`** (gate passed) |
| `tour_type` absent | `400 …required` | **`401 auth_required`** (gate passed, no crash) |
| `location:""` | `400 …required` | **`400 {"error":"location is required"}`** |
| `tour_type:"museum"` | `401 auth_required` (gate passed) | `401 auth_required` (identical) |

The `401` on empty/missing `tour_type` proves the gate now advances past the
location/tour_type check to entitlements — i.e. no longer a 400. `location:""` still 400.

### AC2 — No-drift for explicit types
`_classify_tour_category` is untouched by the fix, so explicit types take the identical path
and category. Verified directly (`probe_classifier.py`, run in BEFORE and AFTER — **identical
output in both**):

```
empty_on_restaurant_loc    tour_type=''       -> category=restaurant
none_on_restaurant_loc     tour_type=None     -> category=restaurant
explicit_museum            tour_type='museum' -> category=museum
explicit_museum_on_rest    tour_type='museum' -> category=restaurant
empty_on_museum_loc        tour_type=''       -> category=museum
```

And at the orchestrator (AC1 table, last row): `tour_type:"museum"` returns the same `401`
before and after — same code path, same category decision, same downstream. The generator logs
`Detected tour category: RESTAURANT` for the empty Bread-Thyme case, exactly as an explicit
type would log its own category. Stop count and path are governed by the classifier, which is
unchanged; only the prose (non-deterministic) would vary, so it is not compared.

### AC3 — `/app` SHA256 manifest diff (only intended files differ)
Full manifests and the diff are in `local474_evidence/`. Summary:

```
ORCHESTRATOR  v22-local474 vs v22 : 241 files both sides
  => e4abb4d7…  ./tour_orchestrator_service.py    (overlay)
  <= 594761a8…  ./tour_orchestrator_service.py    (base)
  — no other file differs, none added, none removed.

GENERATOR     v36-local474 vs v36 : 204 files both sides
  => c45f41b1…  ./generate_tour_text.py           (overlay)
  => e891600d…  ./generate_tour_text_service.py   (overlay)
  <= f4a3abdd…  ./generate_tour_text.py           (base)
  <= f20e4361…  ./generate_tour_text_service.py   (base)
  — no other file differs, none added, none removed.
```

### AC4 — Staged `deploy_beta_local474.sh` (`--dry-run` default, `--apply`)
The script builds+pushes the two overlays, then `gcloud run services update … --image …`
for **`tour-orchestrator`** and **`tour-generator`** only — **image only**, no env/scaling/other
settings, no other service named — records before/after revisions, and prints rollback commands.
Verified read-only that Beta currently runs `:v22`/`:v36` (the rollback targets). Dry-run output:

```
### MODE: --dry-run  (default; nothing is executed, commands only printed)
==== 0. Record current (BEFORE) revisions and images ====
+ gcloud run services describe tour-orchestrator --region us-central1 --project audiotours-migration --format=value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)
+ gcloud run services describe tour-generator --region us-central1 --project audiotours-migration --format=value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)
==== 1. Build overlay images (FROM v22/v36, COPY only the LOCAL-474 files) ====
+ docker build -f .../Dockerfile.local474.orchestrator -t .../audioura:v22-local474 .
+ docker build -f .../Dockerfile.local474.generator  -t .../audioura:v36-local474 .
==== 2. Push overlay images ====
+ docker push .../audioura:v22-local474
+ docker push .../audioura:v36-local474
==== 3. Point the two Beta services at the overlay images — IMAGE ONLY ====
+ gcloud run services update tour-orchestrator --region us-central1 --project audiotours-migration --image .../audioura:v22-local474
+ gcloud run services update tour-generator    --region us-central1 --project audiotours-migration --image .../audioura:v36-local474
==== 4. Record new (AFTER) revisions and images ====
+ gcloud run services describe tour-orchestrator … / tour-generator …
==== 5. ROLLBACK (run these to restore the pre-LOCAL-474 images) ====
gcloud run services update tour-orchestrator --region us-central1 --project audiotours-migration --image .../audioura:v22
gcloud run services update tour-generator    --region us-central1 --project audiotours-migration --image .../audioura:v36
==== DONE ====
Dry run complete. Nothing was built, pushed, or changed.
```

### AC5 — One authorized live tour
Exactly one live 1-stop generation was triggered (the empty-`tour_type` Bread-Thyme case on the
after-generator). The container logged **1** `OPENAI_API_CALL`; I stopped the container
immediately to prevent further spend. No other OpenAI calls were made (all other probes are gate
checks that return before any generation, or classifier-only pure-function calls).

---

## 5. Process compliance
- **Deployed nothing.** Only read-only `docker pull` of `:v22`/`:v36`. No `docker push`, no
  `gcloud run` update. Read-only `gcloud run services describe` used to confirm current images.
- Committed on `kiro/gcs-7` and pushed the branch. Not merged to `main` or `storied`.
- Local Postgres only (the existing healthy `development-postgres-2-1`). No production writes,
  no `DELETE FROM audio_tours`.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `GCLOUD_STORIED_START_HERE.md`, or `BUILD_NUMBERS.md`.
- Windows: evidence scripts use `encoding="utf-8"`; `deploy_beta_local474.sh` runs in Git Bash.
- The standing `development-*` stack was left untouched (still healthy after all tests).

## 6. New / changed files
```
generate_tour_text.py                       (edited: None→'' at entry)
generate_tour_text_service.py               (edited: gate + None→'')
tour_orchestrator_service.py                (edited: gate)
Dockerfile.local474.orchestrator            (new: overlay on v22)
Dockerfile.local474.generator              (new: overlay on v36)
deploy_beta_local474.sh                      (new: staged, dry-run default)
local474_evidence/manifest_*.txt             (new: /app SHA256 manifests)
local474_evidence/manifest_diff.txt          (new: no-drift diff summary)
local474_evidence/probe_generator.py         (new: reproducible gate probe)
local474_evidence/probe_orchestrator.py      (new: reproducible gate probe)
local474_evidence/probe_classifier.py        (new: reproducible classifier probe)
```

## 7. Source diff
See `git diff main..kiro/gcs-7 -- generate_tour_text.py generate_tour_text_service.py tour_orchestrator_service.py`.
Three hunks, described in §2. No other source touched.

## 8. Blocking questions
None. The deploy is staged and authorized (ClickUp `wdvrdaxxm9`, Michael 15:42). Running
`deploy_beta_local474.sh --apply` from a machine authenticated to push to
`services/audioura` and update Cloud Run in `audiotours-migration` completes the deploy;
rollback commands are printed by the script and listed in §4.
