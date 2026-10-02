# DEPLOY_READINESS.md — Is Storied ready for a GCloud Preview end-to-end test?

**Task:** LOCAL-516 · **Agent:** Mac Mini Kiro · **Branch:** `LOCAL-516-deploy-readiness`
**Base:** `storied` = `7a97e72` (verified `git merge-base --is-ancestor 7a97e72 HEAD` → exit 0; HEAD == origin/storied here)
**Date:** 2026-09-23 · **This is an audit. Nothing was deployed, migrated, or written to production.**

Preview has never run a tour *through the service* with the current Storied code. Every tour in
the last week was produced by calling `generate_tour_text()` directly on the host. This document
answers the five readiness questions with evidence, and marks each PASS / FAIL / UNKNOWN.

---

## Summary table

| # | Check | Verdict |
|---|---|---|
| 1 | Does the service path work at all? | **PASS** (mechanically), with a caveat: only *old* code was exercised |
| 2 | Do the new modules import cleanly in the container? | **PASS** for import; **the deployed image is STALE and MUST be rebuilt** |
| 3 | Env/secrets Cloud Run needs (GEMINI, SERP)? | **FAIL as-scripted** — `deploy_storied_generator.sh` would wipe SERP + Gemini |
| 4 | Does the venue-parts path need a schema change? | **PASS** — it writes nothing to the DB |
| 5 | Does a service tour land in `audio_tours` with audio? | **UNKNOWN on Cloud SQL** — works locally; a live-schema dependency is unverifiable from here |

---

## 1. Does the service path work at all? — **PASS (mechanically)**

**How the path is wired (read from source):**
`tour_orchestrator_service.py` → `orchestrate_tour_async()` (line 639) POSTs to
`TOUR_GENERATOR_URL/generate`. `generate_tour_text_service.py`'s `/generate` spawns a background
thread → `generate_tour_async()` → **calls `generate_tour_text()` — the exact same function the
host path calls directly.** The orchestrator then POSTs to `MODERNIZED_URL/process` (which produces
the MP3 audio via Polly TTS and returns a ZIP), downloads the ZIP, and calls `store_audio_tour()`
to insert it into `audio_tours`. The orchestrator does not generate; it delegates. So the service
path and the host path share the identical generation function — the result **shape** is the same
by construction.

**Verified end-to-end, live, today (2026-09-23 12:39–12:42), on the local Docker stack.** The
orchestrator log shows a `Beacon Hill, Boston` historical 2-stop request going the whole way:

```
orchestrate_tour_async → /generate → /status poll → tour_content returned
  (proper "Stop 1: … / Stop 2: …" shape, coordinates [42.3589, -71.0637])
→ modernized "Generating audio files…" → ZIP
→ store_audio_tour "Inserted new tour… ==== AUDIO TOUR STORED SUCCESSFULLY ===="
→ final_tour_id: 349
```

The DB row confirms it: `audio_tours` id 349, `has_audio = t`, **1,602,144 bytes** of audio.

**Caveat (why this is not a full PASS for the new code):** the running containers are 8 days up but
their code is ~24 days old. `/health` on the generator reports `code_sha: ef536c2`,
`build_time: 2026-08-30`. The running container **does not contain** `venue_parts.py`,
`tragedy_context_gate.py`, `preflight.py`, or `tour_quality.py` (`ls` → "No such file"), and its
`generate_tour_text.py` md5 (`e0d8343…`) differs from the host's (`1a8d089…`). So the today-run
proves the **plumbing and result shape** are correct through the service, but it exercised the
*old* engine — it does **not** prove the new venue-parts code works through the service. That
requires a rebuilt image (see #2), which is deploy-adjacent and out of scope here.

---

## 2. Do the new modules import cleanly in the container? — **PASS (import); REBUILD REQUIRED**

**Import test (Python 3.9.6, matching the generator's `python:3.9-slim` base):** all six import
cleanly with no error:

```
IMPORT_OK: venue_parts
IMPORT_OK: tragedy_context_gate
IMPORT_OK: sentence_split
IMPORT_OK: geo_refutation
IMPORT_OK: tour_quality
IMPORT_OK: preflight
```

**They are stdlib-only.** None of the six imports a third-party package, even at function level
(only `os`, `sys`, `re`, `json`, `threading`, `math`, `urllib`). So the hand-maintained pip lists
in `requirements_generator.txt` / `Dockerfile.cloudrun` are irrelevant to them — nothing to add.
`Dockerfile.generator` and `Dockerfile.cloudrun` both `COPY *.py /app/`, which is content-addressed
and picks up all six root-level modules on any rebuild.

**Only two of the six are on the service request path.** `generate_tour_text.py` imports
`venue_parts` and `tragedy_context_gate` (which pulls in `sentence_split`). `tour_quality`,
`preflight`, and `geo_refutation` are imported **only** by `tour_loop.py`, a host-side batch/QA
harness — never by the generator service, orchestrator, or modernizer. They ship in the image but
are not invoked by a tour request.

**The deployed image is STALE — this is the real blocker (D531).**
- The six modules were first committed 2026-09-17 … 2026-09-22.
- The live Storied generator image is `audioura-storied:v1`, built ~2026-09-15 from source that
  **predates every one of them** (per `GCLOUD_STORIED_START_HERE.md`).
- The local running container proves the same failure mode concretely: it lacks the new files and
  runs an old `generate_tour_text.py`.
- D531's own finding: `COPY *.py` is content-addressed (no stale-layer risk); the trap is rebuilding
  the image but not recreating the container. On Cloud Run, "recreate" = deploy the new image.

**Conclusion:** the modules are import-clean, but a Preview test on today's image would silently run
the old engine. **The Storied image must be rebuilt from current `storied` and redeployed before any
Preview test can measure the new code.**

---

## 3. Env vars / secrets Cloud Run needs — **FAIL as-scripted (silent-degradation trap)**

**Three keys matter on the generation path** (`preflight.py` documents their roles exactly):
- `OPENAI_API_KEY` — **required**; generation hard-fails without it. It **is** wired.
- `GEMINI_API_KEY` — `preflight` classifies it *required*; in `generate_tour_text.py` it powers the
  LOCAL-488 cross-model agreement (`story_leads` fan-out) and the grounded knowledge fallback
  (`stop_knowledge_fallback`). Missing it does **not** hard-fail — OpenAI is primary — it prints
  `"…set GEMINI_API_KEY"` and **silently degrades** grounding/verification.
- `SERP_API_KEY` — **optional**; missing it degrades the tour (fewer `[SQ-S2]` searches), no error.
  (Note the name is `SERP_API_KEY`, not `SERPER_API_KEY` — `preflight.py` calls this out.)

The host `.env` contains all three (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `SERP_API_KEY`), which is
why every host tour last week was ungraded — this is precisely the "fails silently into a degraded
tour" gap the task warns about.

**What is live on Cloud Run today (per `GCLOUD_STORIED_START_HERE.md`, 2026-09-15):** Michael
manually wired both — secret `serp-api-key` v1 → `tour-generator-storied` rev `00002-xql`
(`SERP_PROVIDER=serper`), and secret `GEMINI_API_KEY` (uppercase name) → rev `00003-2gf` via
`--update-secrets`. Only `tour-generator-storied` reads them (not the orchestrator or modernizer).
**These bindings were never confirmed by a real Preview tour** — the doc's own open item is *"On the
first real Preview tour, confirm `[SQ-S2]` search lines … Gemini calls …"*.

**The trap:** `deploy_storied_generator.sh` sets
`GEN_SECRETS="OPENAI_API_KEY=openai-api-key:latest,DB_PASSWORD=db-password:latest,PGPASSWORD=db-password:latest"`
— **no GEMINI, no SERP** — and applies it with **`--set-secrets`, which REPLACES the entire secret
list.** The same doc warns in bold: *"Never use `--set-secrets` … They replace the whole list … it
would have deleted the OpenAI, DB and SERP secrets."* So redeploying the rebuilt image (#2) with the
script as written **would strip the SERP and Gemini secrets** off the service, silently degrading
every Preview tour.

**Verdict FAIL as-scripted.** The keys exist in Secret Manager and are wired to the *current* live
revision, but the rebuild-and-redeploy needed for #2 would remove them unless the script is first
fixed to include `GEMINI_API_KEY` + `SERP_API_KEY` in `GEN_SECRETS`, or the deploy uses
`--update-secrets` instead of `--set-secrets`.

---

## 4. Does the venue-parts path need a schema change? — **PASS (no schema change)**

`venue_parts.py` has **zero** database access — 0 occurrences of `psycopg2`, `db_connection`,
`INSERT`, `CREATE TABLE`, `ALTER TABLE`, `.execute(`, or `commit(`. The same is true of all six new
modules (`db_tokens = 0` for each).

The "evidence" the venue-parts path produces is an **in-memory Python dict** returned from
`venue_parts.build_tour_stops()` back into `generate_tour_text.py` (line ~6528), where it seeds the
writer's `_lore` input channel and the stop ordering. It is consumed within the request and **never
persisted**. Nothing to migrate.

*(Adjacent note, not a venue-parts issue — see #5: `store_audio_tour`'s existing dependency on the
`original_tour_id` column is a separate, pre-existing risk.)*

---

## 5. Does a service tour land in `audio_tours` with audio? — **UNKNOWN on Cloud SQL**

**Locally: YES, verified.** Today's Beacon Hill run landed as `audio_tours` id 349 with 1,602,144
bytes of audio (see #1). The local `audio_tours` schema has the columns the insert needs, including
`original_tour_id`, `storied_mode`, `i_con_avg/min`, `zip_filename`, `is_test`; the only missing one
(`track`) is self-healed at runtime by `store_audio_tour` (`ALTER TABLE … ADD COLUMN track …`).

**On Cloud SQL: UNKNOWN, and there is a concrete reason to flag it.** `store_audio_tour`
(tour_orchestrator_service.py ~line 508) runs an existence check before inserting:

```sql
SELECT id FROM audio_tours WHERE lower(tour_name) = lower(%s) AND original_tour_id IS NULL
```

`original_tour_id` is referenced here **without a self-healing `ADD COLUMN` guard** — unlike
`audio_tour`, `lat`, `number_requested`, `tour_content`, and `track`, which the function adds on the
fly if absent. And `migration/sql/007_storied_schema_parity.sql` (the file that brings Cloud SQL to
parity, 2026-08-11) **explicitly declines to create `original_tour_id`** or the
`uq_audio_tours_original_name` index: *"applying it against 302 live rows risks a duplicate-title
violation aborting the migration."*

So **if the Storied Cloud SQL instance does not have the `original_tour_id` column**, this SELECT
throws, the exception is caught by `store_audio_tour`'s outer `try/except`, and it returns
`success=False, action="error"` — **the tour would generate and get audio but never land in
`audio_tours`.** That is exactly the device-test failure mode. I cannot query the live Cloud SQL
schema from this environment, so whether the column exists there is genuinely **UNKNOWN** and must
be checked before (or on) the first Preview tour. This is a pre-existing risk, not caused by the new
code, but it directly governs whether check #5 passes on Preview.

---

## The one sentence

**Deploying today would NOT reliably work, because the live Storied image predates the new
venue-parts modules and must be rebuilt — and the rebuild's own deploy script would strip the
Gemini and SERP secrets (silently degrading every tour), while whether a service tour even lands in
`audio_tours` on Cloud SQL hinges on an `original_tour_id` column that migration 007 never added and
that cannot be verified from here.**
