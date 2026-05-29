# Claude.AI Review — M02 Phase B Design (Cloud-Ready Refactoring)

**Session:** Audioura Services #5
**Reviewer:** Claude
**Document reviewed:** `migration/m02_phase_b_design_for_claude_review.md`
**Verdict:** **The overall plan is sound and the feature-flag approach is the right pattern.** Sections 3–6 are correctly scoped for Phase B. But the design under-treats one architectural question (stateless-session in editing), misses three cross-cutting issues that *will* bite during cutover (per-instance `ACTIVE_JOBS`, the translation-service Dockerfile divergence, hardcoded credentials), and the 12–15 h estimate is optimistic on the editing service. Answers to the 6 numbered questions in §A, cross-cutting findings in §B, revised order/effort in §C.

(Your doc lists six numbered questions in Section 7, not seven — flagging in case a Q7 went missing.)

---

## A. Answers to the 6 numbered questions

### Q1 — Is `STORAGE_MODE=volume|cloud` the right pattern?

**Yes — keep it.** The alternative (always HTTP content passing, even locally) reads as "cleaner code" but is a worse choice in practice: every local dev iteration would pay the serialization tax, memory pressure goes up on the generator service, and you lose the ability to compare cloud vs. local behavior side-by-side when debugging a regression. The feature flag lets you ship the cloud path **before** flipping the local default, which is exactly the safety margin you want.

Two small refinements:

- **Scope the env var name.** `STORAGE_MODE` is generic enough that it'll collide with future "blob storage" or "DB storage" toggles. Suggest `TOUR_STORAGE_MODE` (or even `TOUR_FILE_TRANSPORT`, since what's really changing is how tour files travel between services, not where they're stored long-term).
- **Document the "what changes per mode" contract in one place** — a single block in each service's module docstring listing exactly what behaviour the flag toggles. Otherwise the dual-mode logic will drift between services over time.

### Q2 — Store ZIP in R2 immediately, or keep DB BYTEA for now?

**Defer R2 to Phase D, as your doc originally proposed.** Phase B's purpose is "the code runs cloud-ready locally." R2 brings in: Cloudflare account setup, credential plumbing, network egress costs, S3-protocol error handling, dual-write/read-during-migration logic. None of that has anything to do with eliminating the volume or fixing service URLs. **Two large changes at once double the risk of cutover; staged, they're each validated independently.**

What you *should* do in Phase B: build the **abstraction** (`BlobStorage` interface with `database` and `r2` implementations), wire the feature flag, write the MinIO-backed local test. That's ~2 h. Flipping production to R2 is Phase D.

### Q3 — Is extracting from DB to `/tmp/` on every edit acceptable?

**The 1-second per-extract cost is fine. The architectural question your wording skirts is bigger and needs answering before you code:** *where does edit-session state live across multiple HTTP requests when Cloud Run can route each request to a different container instance?*

The current editing flow is:
1. Mobile downloads the tour (a GET).
2. Mobile makes one or more `bulk-save` requests, each producing a *new* UUID-keyed directory holding the edited ZIP.
3. Mobile later calls `promote` with that UUID → service inserts into `audio_tours`.

In Docker today, step 2's `/app/tours/<uuid>/` directory persists across requests because the volume is shared and the single container has stable disk. **In Cloud Run, that directory exists only inside the one container instance that handled the `bulk-save`.** The `promote` call almost certainly lands on a different instance — `/app/tours/<uuid>/` is gone, and `promote` has nothing to read.

Three options to resolve, in increasing order of work:

1. **Collapse `bulk-save` + `promote` into one call.** Mobile sends edits + custom_name in a single request; service produces the ZIP, inserts the row, returns the new tour id. Loses the naming-conflict UX (you don't know the name is taken until *after* you've done the TTS work). Cheapest.
2. **Persist the draft ZIP somewhere shared between `bulk-save` and `promote`.** Either: store a "draft" row in `audio_tours` with a `draft=true` flag (and clean up unpromoted drafts via a cron); or store in R2 under a temp prefix. Most flexible, preserves current flow.
3. **Cloud Run session affinity.** Configure the service for session affinity so the same client lands on the same instance for the edit session. Works in practice but it's fragile (affinity isn't guaranteed during deploys), and you still lose state on container recycle.

I recommend **Option 2 with the `draft=true` row** — it keeps the two-call UX, the DB is already in your control, and `promote` becomes "flip the draft row to non-draft + set the user's name + enforce uniqueness." Add this decision to Phase B before implementing the editing-service changes.

`/tmp` extraction stays — but it's purely **per-request scratch space**, never relied on across requests.

### Q4 — Should `tour_id_resolution` query the DB instead of reading the volume?

**Yes.** When the volume is gone, "the DB is the source of truth" needs to be true everywhere, including in resolution. Behaviour change is acceptable for an internal service. While you're in there, replace the keyword-matching `resolve_numeric_to_uuid_directory` logic (which I noted earlier is fragile — `if 'harvard' in tour_name`-style) with a clean DB lookup by `id` and `tour_name`.

### Q5 — Consolidate `tour_editing_1` and `tour_editing_phase2`?

**Defer.** Sir Michael said keep both, and Phase B isn't the right scope to refactor service boundaries. Two services × env-var URLs work fine. Track consolidation as a separate post-migration cleanup. Don't grow Phase B's blast radius for refactor-tax reasons.

### Q6 — HTTP request size limits?

**Tour text is fine; bulk-save with custom audio is the size you should worry about.** Numbers:
- Tour text: 5–50 KB. Comfortably inside Cloud Run's 32 MB request cap.
- ZIP downloads from modernized service: typically 1–10 MB, max observed 19 MB. Fine.
- `bulk-save` with multiple `audio_parts` or `custom_audio_data` (base64-encoded MP3s, multiple stops): can plausibly hit 10–30 MB on a long custom-recorded tour. A 5-stop tour with 5 MB of recorded audio per stop, base64-inflated 33% to ~6.6 MB per stop, is already 33 MB and over the cap.

For Phase B's main generation pipeline (text → ZIP, no custom audio): no risk. For bulk-save: file as a follow-up — chunked upload, or upload custom audio directly to R2 with the request body carrying only references. Not blocking Phase B; flag for Phase D.

---

## B. Cross-cutting issues the design doesn't address (recommend folding into Phase B)

These are not in the questions you raised, but they will block cutover if left to Phase E. Each is small if caught now, large if caught later.

### B.1 — `ACTIVE_JOBS = {}` is per-instance state that breaks under multi-instance Cloud Run

Every async service in your stack — generator, modernized, editing — holds job status in a module-level `ACTIVE_JOBS` dict. In Docker today there's one container per service, so the dict is effectively a singleton. In Cloud Run, **every container instance has its own dict.** A flow that's broken the moment your service scales past one instance:

1. POST `/generate` lands on instance A → A creates `job_id=abc` in *its* `ACTIVE_JOBS`.
2. Returns 202 with `job_id`.
3. Mobile polls GET `/status/abc` — load balancer routes to instance B. B's `ACTIVE_JOBS` has no `abc`. **404.**

This is exactly the same shape as the editing-session problem (Q3) — and Cloud Run will *always* route to a different instance whenever load goes up. Options:
- Move `ACTIVE_JOBS` to a shared store (Redis Memorystore on GCP, or a DB table). The "right" fix.
- Single-instance Cloud Run config (`min_instances=1, max_instances=1`) per service. Works as a temporary measure but defeats the point of Cloud Run.
- Cloud Tasks / Pub/Sub for async work. Larger refactor.

This is *not* avoidable. I'd add it to Phase B as a known scope item rather than discover it during your first end-to-end Cloud Run smoke test.

### B.2 — The `translation_service.py` Dockerfile/runtime divergence will silently regress on first cloud build

I documented earlier that the translation-service container builds from `./translation-service/translation_service.py` (8 KB, old) but the **live** code (`translate_tour_with_audio`, `/translate-with-audio` endpoint) is the **root** `translation_service.py` (76 KB), almost certainly `docker cp`'d in. A `docker compose build` today would silently revert it. **Cloud Build will do exactly that.** Your first Cloud Run deploy of the translation service will lose all the post-Session-15 work in this file.

Fix in Phase B: move the 76 KB file into the build context (either into `./translation-service/` or update the Dockerfile to copy from the parent), delete the 8 KB stale copy, and **run a clean Docker build locally to verify** before the migration touches anything. Two minutes of work, prevents a category of cutover disaster.

The same audit should run against every service in the migration:

```bash
# In every service container, compare what the Dockerfile copies vs. what
# docker-compose `command:` actually runs:
docker exec <container> md5sum /app/<script>.py
md5sum ./<script>.py        # the file the Dockerfile copies
md5sum ./<container>/<script>.py   # the file an alternate Dockerfile path copies
```

Any mismatch → you have a docker-cp drift that'll break cutover. The 9 `tour_editing_phase2_*.py` siblings are a related risk surface: Cloud Build will use whatever the Dockerfile points at, and the Dockerfile may have been written before the `_final.py` variants existed.

### B.3 — Hardcoded DB credentials must move to a secret before any Cloud Run deploy

The editing service has `password="password123"` in source (`tour_editing_phase2.py:97`). I noted this previously as pre-existing tech debt — but Cloud Run will read this from the container image, and the moment that image is in Cloud Build's cache it's effectively *published* with credentials. For Phase B you need:

- Move DB credentials to env vars (`DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_NAME`).
- Local Docker Compose continues to inject the dev defaults via `.env`.
- Cloud Run injects via Secret Manager.
- `get_db_connection()` reads from env vars only — no fallback to hardcoded strings.

Same audit for every service that connects to Postgres or AWS. Run once, fix everywhere, before any deploy touches a real environment.

### B.4 — Inter-service URL audit: don't rely on the 8 you listed

§4 enumerates 8 env vars. That's probably most of them, but I'd run a sanity grep before declaring complete:

```bash
grep -rn "http://[a-z0-9.-]*:" --include='*.py' .
```

Any hit that isn't already going through an env var is a missed migration. Newsletter pipeline, polly-tts callbacks, the `tour-id-resolution` callers, the orchestrator's calls into editing/promote — verify each. Cheap to do, painful to miss.

### B.5 — Health endpoints (your step 6) — make sure they don't accidentally lie

`/health` returning 200 is the contract Cloud Run uses for liveness/readiness. If your `/health` returns 200 unconditionally but the service can't actually reach the DB or AWS, you get cascading failures that look like "scaling problems" instead of "broken deploy." Each `/health` should at minimum check the dependency it absolutely needs (DB connection for DB-backed services, AWS client init for AWS-backed services). Slow checks should be on a separate `/health/deep` endpoint that monitoring hits less often. Cheap to do correctly now, expensive to debug later.

---

## C. Revised order and effort

Your sequence (§6) is broadly right; here's a refinement that puts the cross-cutting items where they fit:

| Step | What | Risk | Realistic effort |
|---|---|---|---|
| 1 | Env-var-driven service URLs + audit grep | Low | 1.5 h |
| 2 | `/health` endpoints (with real dependency checks) | Low | 1.5 h |
| 3 | Externalize DB credentials and AWS config to env vars (§B.3) | Low | 1.5 h |
| 4 | Fix translation_service Dockerfile divergence (§B.2) + audit other services for same drift | Low | 1 h |
| 5 | Add `tour_content` field to generator status response | Low | 30 min |
| 6 | Add `tour_content` parameter to modernized `/process` | Low | 1 h |
| 7 | Refactor orchestrator: content-passing + `STORAGE_MODE` flag | Medium | 2 h |
| 8 | Decide and implement the editing-session state model (Q3 / §B.1 follow-up) | **Medium–High — design decision first** | 4–6 h |
| 9 | Refactor `tour_editing_phase2` to extract from DB to `/tmp` per request | Medium | 2 h |
| 10 | Refactor `tour_id_resolution` to query DB | Low | 1 h |
| 11 | `ACTIVE_JOBS` → shared store (Redis Memorystore or DB table) for every async service (§B.1) | **Medium — touches multiple services** | 3–4 h |
| 12 | Build `BlobStorage` abstraction behind feature flag, MinIO-backed local test | Medium | 2 h |
| 13 | End-to-end test locally with `TOUR_STORAGE_MODE=cloud` + `BLOB_STORAGE=database` (multi-instance simulation) | — | 3 h |

**Realistic effort: 23–28 h.** Closer to 2× your estimate, mostly because §B.1 (multi-instance state) is a real piece of work that the design currently leaves implicit, and Q3 needs an actual design decision before code.

If schedule pressure is a problem, the order above puts the **safe, low-risk items first** (steps 1–6, ~6 h) — that gets a meaningful slice of Phase B shipped early with no behaviour change. Then the harder architectural items (steps 7–12) get the focus they need.

---

## D. Success-criteria additions

Your §9 list is good. Two additions:

8. **Multi-instance smoke test.** Run the orchestrator and modernized service with 2+ replicas locally (Docker Compose `scale: 2`) and confirm tour generation still works end-to-end. This is the cheapest way to surface §B.1 bugs *before* Cloud Run does.
9. **No hardcoded credentials in any service's source.** A grep for `password=`, `aws_secret`, `api_key=` (excluding obvious env reads) should return zero hits.

---

## E. Summary

Approve the design with the following before-implementation decisions:

| Item | Decision needed |
|---|---|
| Edit-session state across multi-instance Cloud Run (Q3 expanded) | Pick Option 1, 2, or 3 from §A.Q3 — I recommend the `draft=true` row |
| `ACTIVE_JOBS` shared store (§B.1) | Redis Memorystore or DB table? Recommend Redis if budget allows |
| Translation-service Dockerfile fix (§B.2) | Acknowledge and schedule before any Cloud Run build |
| Credentials externalization (§B.3) | Confirm scope; needed for Phase B, not Phase D |

The feature-flag approach, the env-var URLs, the content-over-HTTP swap, and the R2-deferred-to-Phase-D split are all the right calls. The plan just needs the cross-cutting items to be explicit, not implicit. Once those four decisions are made, this is ready to implement.

— Claude
