# DEPLOY_READINESS.md — Storied → GCloud Preview (LOCAL-3496)

**Question:** Are we ready for an end-to-end test on GCloud Preview, or are there holes to
patch first?

**This is an audit. Nothing was deployed, no schema was migrated, nothing was written to
production.** All runs are local, against the running dev containers, marked `is_test=true`.

- **Base:** storied `e1341e6` (`git merge-base --is-ancestor e1341e6 HEAD` → exit 0, verified).
- **Branch:** `LOCAL-3496-deploy-readiness`.
- **Method:** ran one real tour through the *service* path (orchestrator → generator → modernizer),
  inspected the running containers, the DB schema, the deploy script, and the Dockerfile.
- **One limitation, stated up front:** `gcloud` is **not installed on this machine**, so I could
  not query Secret Manager directly. What Cloud Run will actually mount is instead read from the
  authoritative source — `deploy_storied_generator.sh` — which is what defines the container's
  secrets and env. That file is conclusive about what gets mounted; it is not a guess.

---

## Summary table

| # | Check | Verdict |
|---|-------|---------|
| 1 | Does the service path work at all? | **PASS** (with a non-blocking bug) |
| 2 | Do the new modules import cleanly in the container? | **PASS** (rebuild required to ship current code) |
| 3 | Does anything new need a key Cloud Run will not have? | **FAIL** |
| 4 | Does the DB have what the new code writes? | **PASS** (no schema change) |
| 5 | Does a service tour land in `audio_tours` with audio? | **PASS** (audio yes; storied provenance flags no) |

---

## Check 1 — Does the service path work at all? **PASS (with a non-blocking bug)**

The host path calls `generate_tour_text()` directly. The service path is: app →
`tour_orchestrator_service.py` `/generate-complete-tour` → HTTP POST to the generator
(`generate_tour_text_service.py` `/generate` on `tour-generator:5000`) → poll `/status` →
modernizer (audio) → `audio_tours`.

**I ran a real tour through the service and it completed.**

- Request: `Faneuil Hall, Boston, Massachusetts`, 2 stops, `is_test=true`, via
  `POST http://localhost:5002/generate-complete-tour`.
- Result: `status=completed`, `final_tour_id=351`, `actual_stops=2`,
  `coordinates=[42.3634,-71.0535]`, `netlify_ready=true`, zip produced.
- The orchestrator reached the generator over HTTP (`tour-generator:5000/health` →
  healthy, `mode=true`), confirming the delegation wiring works.
- Generator logs prove the **full Storied engine ran** on the service path — not a Beta
  fallback: `STORIED_MODE=true`, spine generation, fact sheets (2/2), the `BLOCKER4c` QA
  correction loop, I-CON evaluation + persistence, `LOCAL-410/488` SERP search
  (95+ snippets/stop), and `D533/D556` Gemini fact injection.

**The shape matches the host path** (text + coordinates + tour file, then audio), so the
service path is not producing a degenerate result relative to calling the function directly.

**Non-blocking bug found (worth fixing before or soon after preview, but does not block):**
The generator logged, twice:

```
[LOCAL-275] Part 2 error: name '_venue_parts_used' is not defined
```

This is a real scope bug in `generate_tour_text.py`. The closing-offer / upsell helper
(around lines 2352–2404) reads `_venue_parts_used`, but that variable is a local of the
*main* generation function, assigned only at line 6539. On this path the name is not in
scope, so a `NameError` is raised and swallowed by the `except Exception` at line 2407. The
tour and audio are still produced — but the **closing upsell (news / restaurant / "more
tours like this" offers) is silently dropped**. It fires on an ordinary walking tour, so it
is not an edge case.

---

## Check 2 — Do the new modules import cleanly in the container? **PASS (rebuild required)**

All six modules exist at repo root and **import cleanly inside the running tour-generator
container**:

```
docker exec audioura-tour-generator-1 python -c "import venue_parts, tragedy_context_gate,
  sentence_split, geo_refutation, tour_quality, preflight"  →  CONTAINER IMPORTS OK
```

`generate_tour_text.py` inside the generator container is byte-identical to the worktree
(`md5 = 513bb6a5…` on both). The generator container was rebuilt ~2h ago and carries current
code.

**Staleness (D531) — real, but not where it bites the generator:**

- The **tour-orchestrator** container is **8 days old (built 2026-08-12)**. It does *not*
  contain the six modules (`import venue_parts` → `ModuleNotFoundError`).
  *However*, the orchestrator's source imports **none** of the six modules — it delegates
  generation to the generator over HTTP. So the orchestrator does not need them, and this
  ModuleNotFoundError does not break the service path. This maps cleanly onto Cloud Run,
  where the generator is its own service.
- The stale orchestrator does show two other pre-`LOCAL-474` behaviours that will surprise a
  tester: it **rejects an empty `tour_type`** ("location and tour_type are required") and
  **requires a valid `user_id`**. The current source relaxes `tour_type`. A rebuild picks
  this up.

`Dockerfile.cloudrun` ships current code correctly: `COPY *.py /app/` includes all six
root-level modules, and it explicitly copies the two `tests/`-only modules
(`db_connection.py`, `stop_anchor_detector_v2.py`), `story_type_taxonomy.json`, and
`templates/` that the generator needs at generation time.

**Bottom line: a fresh image built from `e1341e6` will import everything. You must rebuild
and redeploy (especially the orchestrator) — do not point preview at the current stale
images.**

---

## Check 3 — Does anything new need a key Cloud Run will not have? **FAIL**

This is the hole. The generation path uses three paid services; the deploy wires only one.

`deploy_storied_generator.sh` is authoritative for what the Cloud Run generator gets:

```
GEN_SECRETS="OPENAI_API_KEY=openai-api-key:latest,DB_PASSWORD=db-password:latest,PGPASSWORD=db-password:latest"
GEN_ENV="STORIED_MODE=true,...,DATABASE_URL=...,VENUE_CACHE_DB_URL=..."
```

- **`GEMINI_API_KEY` — NOT mounted** (not in `GEN_SECRETS`, not in `GEN_ENV`).
- **`SERP_API_KEY` — NOT mounted** (same).
- A grep for `GEMINI_API_KEY|SERP_API_KEY|GOOGLE_API_KEY` across **every** `deploy_*.sh` and
  `Dockerfile.cloudrun` returns **zero** hits. No `.env` is baked into the image
  (`Dockerfile.cloudrun` has no `COPY .env`). OpenAI is the only generation key that reaches
  Cloud Run.

Why that matters — the code that just ran on the service path depends on both:

- **Gemini:** `story_leads.available_providers()` only lists `gemini`/`gemini_grounded` when
  `GEMINI_API_KEY`/`GOOGLE_API_KEY` is present. The live run used "3 providers" and injected
  `D533/D556` Gemini facts. Without the key those providers disappear.
  `preflight.py` treats **Gemini as REQUIRED** (`preflight(required=('OpenAI','Gemini'))`) —
  by the project's own preflight, no Gemini = "DO NOT RUN A BATCH".
- **SERP (Serper):** used by `work_story_searcher`, `exhibition_checklist`,
  `interpretive_enrichment`, `dining_corpus_harvester` — the `LOCAL-410/488` search that fed
  95+ snippets per stop in the live run. `preflight.py` reads it as `SERP_API_KEY` and
  degrades (not fatal) without it.

The failure mode is exactly the one the task warned about: **a missing key fails silently
into a degraded tour.** No Gemini and no SERP means the Storied evidence pipeline runs on
OpenAI alone — thinner facts, failed searches, and in the worst case a `thin_evidence` clean
failure — with nothing at deploy time telling you why.

**Fix before preview:** create the `gemini-api-key` and `serp-api-key` (Serper) secrets and
add them to `GEN_SECRETS`, e.g.
`GEMINI_API_KEY=gemini-api-key:latest,SERP_API_KEY=serp-api-key:latest`.

---

## Check 4 — Does the DB have what the new code writes? **PASS (no schema change)**

The venue-parts path does **not** write evidence to the database, so **no migration is
required.**

- `venue_parts.py` persists to a **local JSON file cache**
  (`.venue_parts_cache.json`, next to the module — `_CACHE_PATH`, `cache_get`/`cache_put`),
  not a table.
- The evidence dict `_venue_parts_evidence` flows **in memory** through
  `generate_tour_text.py`. A grep for it against any `INSERT`/`execute`/DB column returns
  nothing — it is never persisted to Postgres.
- The tables the delivered tour does touch — `audio_tours` and `stop_metrics` — already have
  the needed columns (`audio_tour`, `stops_count`, `storied_mode`, `i_con_avg`, `i_con_min`,
  and `stop_metrics` with `i_con`, `class_*`, `verified`). Both are present in the dev DB.

**No STOP condition here.** One caveat, not a blocker: the JSON cache is ephemeral on Cloud
Run (lost on cold start / new instance). That is acceptable — it is a cache and regenerates;
it is not a system of record.

---

## Check 5 — Does a service tour land in `audio_tours` with audio? **PASS (audio yes; provenance flags no)**

The tour from Check 1 landed:

```
id=351 | "Faneuil Hall, Boston, Massachusetts - Walking"
audio_tour = 1,865,556 bytes (~1.8 MB real audio) | stops_count=2 | text_len=6064 | is_test=t
```

That is what a device test needs: a row with real audio bytes and content. **PASS.**

**Two honest caveats a tester should know:**

1. **`storied_mode=f` and `i_con_avg=NULL` on the row, and 0 `stop_metrics` rows** for the
   orchestrator's job id. The row is written by the **stale 8-day-old orchestrator/modernizer**,
   which predates the storied-provenance wiring and does not set those flags. The Storied
   gates *did* run in the generator (I-CON was persisted under the generator's own internal
   job id `6f4f1d70…`), but the provenance did not propagate to the `audio_tours` row.
2. **No row in the entire `audio_tours` table has `storied_mode=t`** — consistent with the
   task's premise that nothing has gone end-to-end through the Storied service into the DB
   with provenance. A rebuilt orchestrator should fix the flag propagation; verify it after
   redeploy.

---

## Deploy guards (checked while here)

- **Guard 4 (untracked `.py` in build context):** `git status --porcelain -uall | grep '^??'`
  finds no untracked `.py`. `COPY *.py` will not smuggle history-less code. **Passes.**
- **B4b build-context completeness:** `Dockerfile.cloudrun` copies `tests/db_connection.py`,
  `tests/stop_anchor_detector_v2.py`, `story_type_taxonomy.json`, `templates/`. **Passes.**
- **Base floor:** `e1341e6` is an ancestor of HEAD. **Passes.**

---

## Verdict

**Deploying today would _not_ work as a clean Storied end-to-end test, because the Cloud Run
generator would be started without `GEMINI_API_KEY` or `SERP_API_KEY` — keys the generation
path actively uses — so tours would silently degrade (Gemini is required by the project's own
preflight; SERP search would fail), and that single gap (Check 3) is the blocker; the service
path itself works, no schema change is needed, and audio lands, so once those two secrets are
added to `GEN_SECRETS` and the images (orchestrator especially) are rebuilt from `e1341e6`,
preview is ready.**
