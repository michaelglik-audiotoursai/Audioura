# Audioura Services — Carry-Forward Context (Cloud Migration)

**Updated:** 2026-05-28 (Session 18+)
**Active workstream:** **M02 — Phase B: Cloud-ready refactoring** (21 services → Google Cloud Run)
**Branch:** `services-migration` (was `Newsletters`)
**Purpose:** Paste this into a fresh session to continue the migration work without re-reading the full `claude_*` document trail. This is **migration-focused** — other workstreams (custom tours editing, generation pipeline, newsletter processing) are stable and summarised in §5 only as context.

---

## 1. Where the migration stands

**Goal:** Make all 21 Docker services run on Google Cloud Run with no behaviour change for end users.

**Phases (per migration plan):**
- Phase A: assessment + planning. Done.
- **Phase B: cloud-ready refactoring (current).** Design doc reviewed; awaiting implementation.
- Phase C: GCP project setup.
- Phase D: data migration (DB blobs → Cloudflare R2; existing tour ZIPs).
- Phase E: production cutover.

**Phase B design:** `migration/m02_phase_b_design_for_claude_review.md` (Kiro).
**Claude review:** `migration/claude_response_m02_phase_b_design.md` — **approved with 4 decisions to make before coding** (see §3).

---

## 2. The three things Phase B must solve

1. **Shared volume `/app/tours/`.** 7 services share it as a message bus during tour generation. Cloud Run is stateless — no shared FS. Solution: pass tour content (text, then ZIP) between services via HTTP instead of via disk; orchestrator still stores final ZIP in DB.
2. **Hardcoded inter-service URLs.** Services call each other by Docker container names (`http://development-tour-generator-1:5000`). Cloud Run URLs are dynamic. Solution: env-var-driven URLs with current Docker names as defaults (so local dev keeps working).
3. **2.7 GB of ZIP files in PostgreSQL BYTEA.** Expensive backups, slow restores. Solution: abstraction layer in Phase B (with `BlobStorage` interface, MinIO-backed local test); flip to R2 in Phase D.

**Feature flag:** `TOUR_STORAGE_MODE=volume|cloud` (Kiro proposed `STORAGE_MODE`; Claude review recommended scoping the name). When unset → local Docker Compose behaviour unchanged. When `=cloud` → HTTP content passing + `/tmp` + DB blobs.

---

## 3. Four pre-implementation decisions (from the Claude review)

These are **architectural calls Phase B's code depends on.** Resolve before writing the editing-service refactor.

### 3.1 Edit-session state across multi-instance Cloud Run
Today: `bulk-save` writes `/app/tours/<uuid>/` on disk; `promote` reads it later. In Cloud Run those two calls hit different instances → directory is gone. Three options:
- **Collapse `bulk-save` + `promote` into one call.** Cheapest; loses naming-conflict UX.
- **`draft=true` row in `audio_tours`.** [**Claude's recommendation**] Persist the draft ZIP in the DB between calls; `promote` flips the flag and sets the user's name. Preserves current UX.
- **Cloud Run session affinity.** Fragile across deploys/recycles.

### 3.2 `ACTIVE_JOBS` shared store
Every async service (`generator`, `modernized`, `editing`) holds job status in a module-level `ACTIVE_JOBS = {}` dict. Per-instance — breaks the moment Cloud Run scales past 1 replica (POST creates job on A; GET `/status/<id>` hits B → 404). Options: Redis Memorystore (recommended), DB table, or pin services to `min=max=1` as a temporary measure.

### 3.3 `translation_service.py` Dockerfile/runtime divergence
Container builds from `./translation-service/translation_service.py` (8 KB, old) but the **live** logic (`translate_tour_with_audio`, `/translate-with-audio`) is the **root** `translation_service.py` (76 KB), `docker cp`'d in. A plain `docker compose build` would silently revert it. **Cloud Build will.** Fix the Dockerfile before any Cloud Run deploy of this service.

### 3.4 Credentials externalization
`tour_editing_phase2.py:97` has `password="password123"` hardcoded. Cloud Run images cannot ship credentials. Move all DB/AWS creds to env vars; local Compose injects via `.env`; Cloud Run injects via Secret Manager.

---

## 4. Critical caveats (don't relearn the hard way)

- **9 stale sibling files in `development/`** (e.g. `tour_editing_phase2_*.py` × 9; multiple `tour_orchestrator_service*.py`; multiple `tour_editing*.py`). Docker Compose runs the file in its `command:` line, today; Cloud Build will copy whatever the Dockerfile says. Audit each service's Dockerfile vs. its `docker-compose.yml command:` *before* the migration touches it.
- **Pre-fix tours stay broken.** Mobile reuses tours from the DB by `request_string` match. Fixes only show on newly generated tours. Cleanup of cached rows is required to verify any fix end-to-end.
- **Translation needs `tour_content`** (DB text column). The legacy fallback `translate_zip_audio()` only understands embedded-base64 ZIPs — silently no-ops on modern separate-file ZIPs. Normal generated tours are fine because the orchestrator populates `tour_content`. The risk is for the in-flight Custom Tours `promote` work: that endpoint **must** populate `tour_content` or translation breaks silently.
- **Deploy pattern is changing.** Today: `docker cp <file> <container>:/app/<file> && docker restart`. This works because of host-mounted source. **In Cloud Run, every change rebuilds the image.** Resolve every `docker cp` drift before cutover.

---

## 5. Other workstreams (context only — not active)

- **Custom tours / editing / translation / `promote`.** Spec: `claude_spec_language_aware_editing.md` (Parts A/B/C services + Part D mobile). Work plan: `claude_workplan_tour_editing.md` (8 small tasks). `promote` endpoint still has open items from `claude_response_promote_endpoint_review.md`: DB unique index, `derived_from_tour_id` column, populating `tour_content`. **Should converge with migration:** the editing service's `ACTIVE_JOBS` and stale-sibling-files issues overlap with §3.2 / §4 here.
- **Tour generation pipeline (PHASEs 1–6 + 3C + GEO-CHECK).** Stable. Session 17 (geographic_scope + walking-compactness haversine GEO-CHECK) shipped and approved with minor follow-ups (`claude_response_session17_approval.md`).
- **Newsletter processing.** Two recent fixes shipped: `advertising_url_filter.py` (parse_qs + assertion tests, `claude_response_advertising_filter_fix.md`) and `newsletter_pattern_detector.py` (blog-homepage pattern for Ghost/WordPress/Substack, `claude_response_blog_homepage_pattern.md`).
- **Needham in-tour map white screen.** Flutter-side bug diagnosed (`tour_map_screen.dart` `_fitBounds()` with single-POI degenerate bounds; fix: `if points.length == 1: move(point, 15)`). Status: confirm whether applied.

---

## 6. Service topology (current Docker, the migration's source of truth)

| Service | Container | Port | Role |
|---|---|---|---|
| `tour-orchestrator` | `development-tour-orchestrator-1` | 5002 | Mobile-facing; coordinates pipeline; stores ZIP + row in `audio_tours` |
| `tour-generator` | `development-tour-generator-1` | 5000 | `generate_tour_text.py` — POI generation (PHASEs 1–6) |
| `tour-generation-modernized` | `tour-generation-modernized-1` | 5021 | Splits text into stops, builds `index.html`, calls TTS, builds ZIP |
| `tour-editing-phase2` | `tour-editing-phase2-1` | 5022 | Tour editing — runs `tour_editing_phase2.py` (per docker-compose) |
| `tour-editing-1` | (port 5020) | | Short title generation only; consolidation deferred |
| `tour-id-resolution` | | 5025 | Resolves tour IDs by reading the volume → must switch to DB |
| `translation-service` | `translation-service-1` | 5030 | Translates tours; **divergent Dockerfile, see §3.3** |
| `polly-tts` | `polly-tts-1` | 5018 | AWS Polly wrapper |
| `map-delivery` | | 5005 | Serves tour ZIPs from DB BYTEA — **already volume-free** |
| `newsletter-processor` | `newsletter-processor-1` | 5017 | Runs `newsletter_processor_service.py` |
| (+ 11 others — see docker-compose.yml) | | | |

**DB:** PostgreSQL `audiotours` on host `postgres-2`. Tables: `audio_tours` (tours + translations, `audio_tour` BYTEA), `news_audios`. Migration needs `derived_from_tour_id` column on `audio_tours` (separate change, from the editing workstream).

**Deploy pattern today (will change in Phase E):**
```bash
docker cp <file>.py <container>:/app/<file>.py && docker restart <container>
```

---

## 7. How to verify (migration smoke tests)

Before declaring Phase B done, locally with `TOUR_STORAGE_MODE=cloud` set:

1. **End-to-end tour generation works without the shared volume.** Mobile → orchestrator → generator → modernized → ZIP back to orchestrator → DB. No reads/writes to `/app/tours/` anywhere except `/tmp/`.
2. **Multi-instance smoke test.** `docker-compose up --scale tour-generator=2 --scale tour-generation-modernized=2 --scale tour-editing-phase2=2`. Generation + editing + promote still work — surfaces the §3.2 `ACTIVE_JOBS` problem cheaply.
3. **Health endpoints.** Every service's `/health` returns 200 *and actually checks dependency it needs* (DB connection, AWS client). Slow checks behind `/health/deep`.
4. **No hardcoded credentials.** `grep -rn 'password=' --include='*.py' .` returns zero non-test hits.
5. **Service URL audit.** `grep -rn 'http://[a-z0-9.-]*:' --include='*.py' .` returns only env-var reads, no raw container names.
6. **Translation regression.** Generate a tour, translate to Russian, confirm audio is Russian (catches `translation_service.py` Dockerfile divergence — §3.3).

---

## 8. Document trail for migration

Active:
- `migration/m02_phase_b_design_for_claude_review.md` — Kiro's Phase B design.
- `migration/claude_response_m02_phase_b_design.md` — Claude review + 4 pre-implementation decisions.
- `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` — overall migration plan.
- `sir_michael_services_migration_overview.md`, `aws_migration_notes.md` — background context.

Adjacent (read on demand):
- `claude_spec_language_aware_editing.md` + `claude_workplan_tour_editing.md` — custom-tours work; intersects migration at §3.1 / §3.2.
- `claude_response_promote_endpoint_review.md` — promote endpoint open items.
- `claude_advice_amazon_q_autonomy.md` — Eclipse plugin's limited per-tool permission UI; helper-script pattern in `dev_tools/deploy_test.sh` is the biggest win.

Key source files (the migration touches these directly):
- `tour_orchestrator_service.py` — pipeline coordination, DB insert.
- `generate_tour_text_service.py` / `generate_tour_text.py` — generator service wrapper + the PHASE 1–6 logic.
- `tour_generation_modernized.py` — modernized ZIP builder, port 5021.
- `tour_editing_phase2.py` — editing service, the most complex migration target.
- `translation_service.py` (root 76 KB — the **live** one, not the 8 KB Dockerfile-copied one).
- `docker-compose.yml` — source of truth for which file runs in which container.
