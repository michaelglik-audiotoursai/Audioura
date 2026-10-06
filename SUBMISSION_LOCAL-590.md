# LOCAL-590 — Stop pool: a bigger tour of the same place reuses the stops already written and writes only the new ones

**Branch:** `LOCAL-590-stop-pool` · **Base:** subscribed @ `85e3616` (includes LOCAL-589) · **Agent:** Mac Mini Kiro

Michael, 2026-10-05: *"Stop pool (LOCAL-495): keep the stops already made and only write the new ones. Please build it."*

Today `tour_cache_layer1` caches **whole tours** per (venue, type, stop bucket 1–3 / 4–6 / 7–10). A smaller request is trimmed; a larger one is a **full regeneration** and no stop is ever reused across sizes. This change makes a stop the unit of reuse: a tour of N is now a selection from the venue's **pool** of already-written stops plus only the genuinely new ones.

---

## What was built

Four new modules + a small, contained hook in the generator. No existing behaviour changes when `DISABLE_STOP_POOL=1`.

| File | Role |
|---|---|
| `stop_pool_store.py` | The additive `stop_pool` table + store/retrieve of each delivered stop as an **audio-independent unit**. |
| `stop_pool_assembly.py` | Merge pooled + new stops per the building / outdoor rules; re-stitch orientation, directions, conclusion. Pure, no LLM/DB. |
| `stop_pool_orchestrator.py` | The entry point: read the pool, decide reuse, generate only the new stops, assemble, store back, report counts. |
| `generate_tour_text.py` | Hook: pool fast-path before the impl; `exclude_titles` param + one exclusion filter; exact-count cache bypass; pool store on fresh delivery. |

### 1. Pool store — additive, never DELETE (deliverable 1)

`stop_pool` is `CREATE TABLE IF NOT EXISTS`, PK `(pool_key, title_norm)`. A stop is stored once per
**(venue identity, tour_type, pool version)** as a unit: title, artist/year, **narration body**, the
structured renderer fields (address, coordinates, type/specialty, examples, operational details),
sources, story elements, and a per-stop `generated_at` (the design's per-stop freshness, D581.3).

- **Venue identity is QID-first** (`venue_resolver` Wikidata QID when resolved) **else normalised
  location** — reusing `tour_cache_layer1._normalize_location` so "Miró" and "Miro" share one pool.
- **Orientation and Directions are NOT pooled.** They are properties of a *sequence*, not a stop
  (D581.1), so they are recomputed per selection by the assembly layer.
- **Nothing in this module DELETEs or DROPs.** A superseded stop is UPDATEd in place; retiring a
  generation is a `TOUR_CACHE_VERSION` bump (LOCAL-588), shared with the whole-tour cache so one bump
  retires both.
- `order_seq` records the venue's original delivery order so "best N from the pool" leads with the
  core stops, not an alphabetical accident.

### 2. Single-building tours (museum, facility) — deliverable 2

*"for the one building tours you add 2 new stops before the 5 … regenerate the overall tour general
description … the conclusion can be left alone … ask our listeners to return back if needed."*

- **N > K:** generate exactly **N−K** new stops with the pooled titles **excluded** from selection
  (R4 replenishment still fills the count); place the new stops **before** the pooled ones;
  regenerate the overall orientation; reuse the pooled narration verbatim; recap over the full order
  **plus a walk-back line** for the now-later pooled stops.
- **N ≤ K:** serve the best N from the pool, same order rule, **no LLM call at all**.

### 3. Outdoor tours (walking / biking / driving) — deliverable 3

*"identify the right sequential order and then rewrite the stops before and after the new stops …
potentially 4 stops will have to be rewritten instead of 2."*

- Compute the route order over pooled + new with the existing `stop_route_sequencer` (NN + 2-opt).
- Reuse the **narration bodies verbatim**; rewrite **only the directions/transition text of the stops
  adjacent to each insertion** (the stop before and the stop after). Report rewritten vs reused.

### 4. Exact counts — deliverable 4

With the pool in place the bucketed whole-tour cache read is skipped (`_skip_bucket_cache`), so a
request generates **exactly N** (plus R4 replenishment), never a rounded bucket. `DISABLE_STOP_POOL=1`
restores the old bucket cache.

### 5. Translations / audio — deliverable 5

Audio is not part of the English pool — it is a rendering of a stop's **text** in one voice/engine,
synthesized downstream and keyed on `(text, voice_id, engine)`. The pool guarantees the
**precondition** for reuse: a reused stop's narration is **byte-identical**, so a text+voice+engine
-keyed renderer returns the same audio when the voice/engine match, while a new or
transition-rewritten stop has different text and gets new audio. Translation follows the delivered
(merged) tour exactly as today — it iterates the `Stop N:` blocks the pool assembled.
`stop_pool_orchestrator.audio_reuse_identity` formalises this contract (4 unit tests).

### 6. Metering — deliverable 6

The pool delivery writes `reused_stops`, `new_stops`, `rewritten_transitions` into
`_LAST_GENERATION_COST.breakdown`. `generate_tour_text_service.py:324-341` already passes that
`breakdown` to `cost_meter.record_operation`, which stores it as the `cost_ledger.breakdown` JSONB —
so Michael sees the saving per tour with no service change. Verified live (the actual `POOL DELIVERY`
lines emitted by the two reuse runs):

```
# MFA 5→7 (building, N>K):
[LOCAL-590] POOL DELIVERY: reused=4 new=3 rewritten_transitions=0 (pool held 4)
breakdown = {"llm": 0.6317, "tts": 0.0, "search": 0.0,
             "reused_stops": 4, "new_stops": 3, "rewritten_transitions": 0}

# Boston Common 4→6 (outdoor, N>K):
[LOCAL-590] POOL DELIVERY: reused=4 new=2 rewritten_transitions=4 (pool held 4)
breakdown = {"llm": 0.0927, "tts": 0.0, "search": 0.0,
             "reused_stops": 4, "new_stops": 2, "rewritten_transitions": 4}
```

---

## Tests

**42 unit tests, all green** (`python3 -m pytest test_local590_*.py`):

- `test_local590_pool_store.py` (18) — parse delivered stops into audio-independent units
  (Orientation/Directions/recap/Sources excluded from narration), QID-first identity with
  accent-folded location fallback, pool key namespacing, title normalisation.
- `test_local590_assembly.py` (16) — building new-before-pooled + walk-back + museum transition
  templates; outdoor route re-sequence + only-adjacent-transitions rewritten + verbatim narration
  reuse; exact reused/new/rewritten counts.
- `test_local590_orchestrator.py` (8, 4 DB-backed) — N>K asks for exactly N−K excluding pooled and
  places new-before-pooled; N≤K serves from the pool with the generator asserted **not called**;
  empty pool → normal path; walking re-sequences; the audio-reuse contract.

---

## Isolated live runs (deliverable 7)

Every run was a **disposable container** on `development_default` (never `audioura-*`); the image was
removed after each scenario. Per-tour cost ceiling `COST_HARD_LIMIT_USD=2.00`; total OpenAI spend for
the reported runs well under the $5 cap. Harness: `run_local590_live.sh <scenario>` →
`run_local590_live.py` (step1 full N1, step2 pool N2, baseline full N2 with pooling off). Nothing was
DELETEd.

### Single-building 5 → 7 — Museum of Fine Arts, Boston (QID Q49133, empty pool first)

| step | what | stops | time | cost | reuse |
|---|---|---|---|---|---|
| step1 | full generation of 5 | delivered 4* | 691 s | **$1.0262** | pooled 4 |
| **step2** | **request 7, POOL** | delivered 7 | **403 s** | **$0.6317** | **reused 4, new 3** |
| baseline | full 7, `DISABLE_STOP_POOL=1` | delivered 7 | 740 s | **$1.1286** | — |

\* one step-1 stop was dropped by a content gate, so the pool held 4; step2 reused those 4 verbatim
and generated **only 3 new** stops — *Ancient Nubia Now, Sons of Liberty Bowl, Sargent's Daughters* —
placed **before** the pooled ones (new-before-pooled confirmed in the delivered order).

> **Saving: $0.6317 vs $1.1286 → 44 % cheaper, 403 s vs 740 s → 46 % faster**, same 7 stops delivered.

### Outdoor 4 → 6 — Boston Common, Boston (walking, QID Q49132, empty pool first)

| step | what | stops | time | cost | reuse |
|---|---|---|---|---|---|
| step1 | full generation of 4 | delivered 4 | 341 s | **$0.2064** | pooled 4 |
| **step2** | **request 6, POOL** | delivered 6 | **211 s** | **$0.0927** | **reused 4, new 2, rewritten_transitions 4** |
| baseline | full 6, `DISABLE_STOP_POOL=1` | — | — | — | *see note* |

step1 pooled *Massachusetts State House, Boston Common, Parkman Bandstand, The Central Burying Ground*
(delivered order: State House → Boston Common → Parkman Bandstand → Central Burying Ground). step2
generated **only 2 new** stops — *The Soldiers and Sailors Monument, The Frog Pond* — the **route was
re-sequenced** (delivered order State House → **Soldiers & Sailors Monument** → Parkman Bandstand →
**Frog Pond** → Boston Common → Central Burying Ground: the new stops interleave the pooled ones by
geography rather than being appended), and **4 transitions** were rewritten (the two neighbours of each
of the two insertions — exactly Michael's *"potentially 4 rewritten for 2 added"*). The four pooled
narrations were reused verbatim. This step2 result (`pool_reuse=true`, reused 4 / new 2 /
rewritten_transitions 4) is the verified proof of deliverable 3.

> **Baseline caveat (verified from the run log):** the `DISABLE_STOP_POOL=1` baseline for Boston Common
> did **not** produce a valid full-6 comparison — with pooling off it hit the whole-tour **bucket cache**
> (`CACHE HIT: Boston Common / walking / 6`) seeded by step1 and returned a **trimmed 4-stop** tour at
> $0.00 / 0 s. So the outdoor scenario proves the reuse mechanics and the $0.0927 pool cost, but it does
> **not** have a clean full-generation cost/time to subtract against. The clean cost/time saving is the
> **MFA building** scenario above (step2 $0.6317 / 403 s vs baseline $1.1286 / 740 s), where the baseline
> ran a true full generation. A clean outdoor baseline needs a fresh venue (empty bucket cache) or
> `DISABLE_TOUR_CACHE=1` on the baseline step; it was not re-run to stay under the OpenAI cap.

### Griffin Museum of Photography (museum) — store seeded; N ≤ K reuse NOT captured live

Griffin was used to seed and exercise the store, but the captured Griffin runs do **not** demonstrate the
N ≤ K pool-reuse path, and an earlier draft of this write-up over-claimed that they did. What the logs
actually show:

- **step1** (request 5): full generation, delivered 5, $1.0128, `pool_reuse=false` — seeds the pool.
- **step2** (request 7): **full generation, delivered 7, $1.5092, `pool_reuse=false`, reused 0** — the
  pool was *not* reused on this run. The first Griffin run had stored the pool under the **location**
  key (the QID lookup failed that time) while step2 **resolved** the QID and read the **QID** key, so it
  saw `pooled=0` and regenerated. That split is exactly the D582 bug described below.

The D582 union-read fix (reading both the QID and location keys) addresses the root cause, and the
**MFA** scenario — a clean empty-pool-first run on this fixed code — is the live proof of pooled reuse
(step2 `pool_reuse=true`, reused 4). The **N ≤ K serve-from-pool-only** path is covered by unit tests
(`test_local590_orchestrator.py`: request ≤ pool size serves from the pool with the generator asserted
**not called**, $0 LLM) but was **not** reproduced in a captured live Griffin run. Re-running Griffin
step2 on the fixed code to capture a live N ≤ K / N > K reuse was deferred to stay under the OpenAI cap.

---

## One bug found and fixed during the live runs (D582 class)

The first Griffin run stored the pool under the **location** key (the Wikidata QID lookup, a network
call, failed that time) but the next run **resolved** the QID and read the **QID** key → `pooled=0`,
no reuse. A flaky network call had silently split one venue's pool across two keys — "could not
resolve" looking like "nothing pooled". **Fix:** `get_pool_stops` now reads **both** the QID key and
the normalised-location key and unions them (dedup by title), so a stop is found however the resolver
behaved when it was stored. (Also: the harness passes `DB_HOST/PORT/NAME` so the `tests/db_connection`
helper — which ignores `DATABASE_URL` — reaches `postgres-2` instead of flooding "DATABASE
UNREACHABLE" against `localhost:5433` and hanging assembly.)

---

## How to run

```bash
# unit tests
python3 -m pytest test_local590_pool_store.py test_local590_assembly.py test_local590_orchestrator.py -q

# isolated live run (disposable container, never audioura-*)
./run_local590_live.sh mfa            # building 5 → 7
./run_local590_live.sh boston_common  # outdoor 4 → 6

# disable the whole feature (restores the old bucketed whole-tour cache)
DISABLE_STOP_POOL=1 …
```

## Files

- `stop_pool_store.py`, `stop_pool_assembly.py`, `stop_pool_orchestrator.py` — new modules.
- `generate_tour_text.py` — pool hook + `exclude_titles` + exact-count cache bypass + pool store.
- `test_local590_pool_store.py`, `test_local590_assembly.py`, `test_local590_orchestrator.py` — tests.
- `run_local590_live.py`, `run_local590_live.sh` — isolated live-run harness.
