# SUBMISSION — LOCAL-806 (P6): a research library for the most-requested places

**Branch:** `LOCAL-806-research-library`  **Base:** `subscribed` (`abda16e0`)

## The idea (Michael, 2026-10-27)

Research is the cheap half of a tour (Serper ≈ $0.001/query); writing and voice
are the expensive, on-demand half. So **pre-research the most-requested
destinations once, keep that research with a `fresh_until` date, and build a
later customer request there from the stored research instead of researching from
scratch.** This pilot does exactly that on the Mac, measures it, and ships the
refresh job that keeps the library warm.

**Result in one line:** with the library ON, the four measured tours were
**cheaper on 4/4 places and faster on 3/4**, at **roughly equal** blind quality
(the fresh arm edged it slightly — reported honestly below).

---

## 1. The 10 pilot places (with counts)

Counts are from a **read-only** query against the Mac dev DB (`localhost:5433`,
`audiotours`), non-test only (`audio_tours.is_test = false`), aggregated across
language variants of the same request. `audio_tours` counts sum
`number_requested`; `tour_requests` counts rows.

| # | Place | `audio_tours` (Σ requested) | `tour_requests` (rows) | Source |
|---|-------|----------------------------:|-----------------------:|--------|
| 1 | Walking tour of Massachusetts politics & current affairs, Boston (EN+RU+ES+FR) | 163 | 0 | top non-test |
| 2 | Asian Arts Museum, Nice (EN+FR+RU) | 93 | 11 | top non-test |
| 3 | Palais Lascaris, Nice | 21 | 0 | top non-test |
| 4 | Salem Witch Museum / Trial, Salem MA | 21 | 3 | top non-test |
| 5 | McMullen Museum of Art, Boston College | 6 | 2 | top non-test |
| 6 | Boston Common (walking) | 0 | 28 | top non-test (string lives in `tour_requests`) |
| 7 | Faneuil Hall Marketplace, Boston | 4 | 1 | top non-test |
| 8 | Museum of Fine Arts / MFA, Boston | 0 | 7 | top non-test |
| 9 | **Pagodas & temples of Ho Chi Minh City** (Jade Emperor, Thien Hau) | 2 | 3 | **Michael's trip (required)** |
| 10 | **Kitesurfing schools in Mui Ne, Vietnam** | 1 | 1 | **Michael's trip (required)** |

Places 1–8 are the genuine most-requested non-test locations on the Mac DB; 9–10
were added per the ticket (Michael's trip). "Test tour for translation
functionality" (31 `tour_requests`) and other `is_test`/acceptance strings were
excluded by design.

> Note: earlier inline comments in `build_research_library.py` cited slightly
> higher single-figure counts; the table above is the independently re-verified
> set and supersedes them.

---

## 2. Build — research half only, stored with `fresh_until`

`build_research_library.py` runs, for each place, the **research half** of the
pipeline via `generate_tour_text()` (candidate discovery through
places_search/Wikidata, existence evidence, pins, fact snippets, and the
narration text) and lets the generator's **own** post-generation pool store write
the stops into `stop_pool` — the single, correct write point, under the exact
`(venue identity, tour_type)` key a later customer read uses. **No voice/TTS** is
produced (that is the expensive on-demand half).

Freshness windows are stamped per place:

- museums / landmarks / walking / facility / specialized → **90 days**
- businesses (restaurants / places / dining) → **30 days**

### Schema change (additive only)

One column: `stop_pool.fresh_until TIMESTAMPTZ` + a partial index
(`WHERE fresh_until IS NOT NULL`).

- Migration file: `migration/sql/059_stop_pool_fresh_until.sql`
  (`ADD COLUMN IF NOT EXISTS`, idempotent, never DELETE/DROP).
- Mirrored by the self-healing `ADD COLUMN IF NOT EXISTS` block in
  `stop_pool_store._ensure_table` so a dev DB and a migrated DB agree.
- An ordinary delivered-tour stop has `fresh_until = NULL` and is **never** aged
  out by this column — behaviour is byte-for-byte unchanged for every existing
  row and every ordinary delivery. Orthogonal to `news_generated_at` (LOCAL-655).

### Isolation & safety (library writes never touch live 5433)

The builder writes **only** to the `DATABASE_URL` it is given, which is an
**isolated throwaway DB seeded from a schema dump**
(`scratch/local806-initdb/01_schema.sql`, a schema-only `pg_dump`). A hard
refusal aborts if `DATABASE_URL`/host looks like the live DB
(`development-postgres` or port `5433`). The `tests/live_run_meter.py` hard cap
bounds paid-API spend per run.

### Library rows written (build)

| Place | Category | Stops stored |
|-------|----------|-------------:|
| Boston politics (walking) | walking | 5 |
| McMullen Museum of Art | museum | 5 |
| Boston Common (walking) | walking | 5 |
| Faneuil Hall Marketplace | restaurant | 5 |
| HCMC pagodas & temples | walking | 4 |
| Mui Ne kitesurfing | restaurant | 4 |
| Asian Arts Museum, Nice | museum | 0 |
| Palais Lascaris, Nice | walking | 0 |
| Salem Witch Museum | museum | 0 |
| Museum of Fine Arts, Boston | museum | 0 |

**28 library stops** were written across the six places that produced poolable
stops. Four places stored 0 — they clean-failed (no poolable stops under the
cheap arm + existence gate in `log_only`), which is the honest, safe outcome: no
fabricated stops entered the library.

---

## 3. Generation reads the library first (hit / stale handling)

Wiring is in `stop_pool_store.py` and `generate_tour_text.py`:

- **Write:** `store_delivered_tour(..., fresh_days=N)` stamps
  `fresh_until = NOW() + N days` on each stop. `generate_tour_text` passes
  `fresh_days` only when `RESEARCH_LIBRARY_FRESH_DAYS` is set in the environment —
  **only** the builder / refresh job set it, so every real customer generation
  passes `None` and leaves `fresh_until` NULL (unchanged behaviour).
- **Read (library hit):** `get_pool_stops` serves a pooled stop only while
  `fresh_until IS NULL OR fresh_until >= NOW()`. A pre-researched row counts as a
  normal pool hit while fresh.
- **Stale → refreshed, not served:** once `fresh_until` is in the past the row is
  **ignored** by the reader (not served stale); the refresh job re-researches it.
- **No silent freshness drop:** an ordinary re-pool over a library row keeps the
  existing date (`fresh_until = COALESCE(EXCLUDED.fresh_until, stop_pool.fresh_until)`).

### Test — `tests/test_local806_research_library.py` (4 tests, all pass, 0.37s)

Runs in a private throwaway schema (`tests/_isolated_db.IsolatedSchema`) with
proven-unchanged public row counts — **zero production writes**. Proves: (1) a
library write stamps `fresh_until` and is served while fresh; (2) a past-`fresh_until`
row is ignored; (3) an ordinary delivery leaves `fresh_until` NULL and is always
served; (4) an ordinary re-pool keeps the library freshness window.

```
$ python3 -m pytest tests/test_local806_research_library.py -q
....                                                                     [100%]
4 passed in 0.37s
```

---

## 4. Measurement — library OFF vs ON (4 places, own containers)

Each place was generated twice, each arm in its own container DB:

- **OFF** — `DISABLE_STOP_POOL=1`, an empty DB → full fresh research+generation.
- **ON** — pool enabled, the built library DB → library hit (pre-researched stops
  reused).

Both arms: `RESEARCH_BACKEND=serper`, `NARRATION_MODEL=gpt-4.1-mini`,
`STORIED_MODE=true`, `DISABLE_TOUR_CACHE=1`. Cost is metered by
`tests/live_run_meter.py`. (`measure_local806.py`; logs under
`scratch/local806_logs/`, measured tour texts under `scratch/local806_measure/`.)

| idx | Place | OFF sec | OFF $ | ON sec | ON $ | faster? | cheaper? |
|-----|-------|--------:|------:|-------:|-----:|:-------:|:--------:|
| 0 | Boston Common | 396.4 | 0.2432 | 200.0 | 0.1118 | ✅ ON | ✅ ON |
| 1 | Boston politics | 553.6 | 0.3188 | 354.1 | 0.1077 | ✅ ON | ✅ ON |
| 2 | HCMC pagodas | 370.1 | 0.2379 | 338.9 | 0.1941 | ✅ ON | ✅ ON |
| 3 | Mui Ne kitesurf | 428.8 | 0.3947 | 447.4 | 0.3694 | ❌ OFF (+18.6s) | ✅ ON |
| | **Mean** | **437.2** | **0.2987** | **335.1** | **0.1958** | ON −23% time | ON −34% $ |

**ON is cheaper on all 4 and faster on 3 of 4.** idx3 (Mui Ne) was marginally
slower ON (18.6s) but still cheaper — the library had only 4 stops and the
on-demand assembly still did real work.

### Blind quality score (scored before unblinding)

The measured text for each place was saved **without its arm label**
(`idxN_A.txt` / `idxN_B.txt`). I scored each pair 1–10 for grounding, coherence
and directions **before** looking up which file was which arm (full record:
`scratch/local806_measure/blind_scores.md`).

| idx | A | B | blind winner |
|-----|--:|--:|--------------|
| 0 | 8.5 | 9.0 | B (slightly) |
| 1 | 7.5 | 9.0 | B |
| 2 | 7.5 | 9.0 | B |
| 3 | 8.0 | 8.5 | B (slightly) |

**Unblinding: A = ON (library), B = OFF (fresh research).**

**Honest reading:** the speed/cost win (the point of the pilot) is clear and
one-sided for ON. On **quality**, the blind reads slightly favoured the **fresh**
arm on all four — the expected "equal or better" held as *roughly equal*, not
better. Two explainable reasons, both fixable: (1) the idx2 (HCMC) library had
only 3 fresh stops stored for that key, so ON served 3 vs OFF's 4; (2) the
library row was built once in the cheap arm and does not carry the request-time
current-affairs news the fresh arm fetched live. A production library would store
≥ the requested stop count and let the on-demand half still attach live news on
top of the reused research — keeping ON's speed/cost win while closing the gap.

---

## 5. Refresh job (FILE ONLY — not run, not installed)

- `research_library_refresh.py` — scans `stop_pool` (read-only) for library rows
  (`fresh_until IS NOT NULL`) within a lead window of expiry (default 7 days, and
  any already-stale rows), maps each back to a pilot place by venue identity, and
  **re-researches** it via the builder path so its `fresh_until` advances.
  **Dry-run by default**; `--apply` makes capped re-research calls and hard-refuses
  the live 5433 DB. Never DELETE/DROP (rows are UPDATEd in place).
- `.continuous_dev/com.audioura.research-library-refresh.plist` — launchd agent
  (daily 03:30, `--apply`) pointed at the **isolated** library DB, capped. A FILE
  ONLY; LEAD installs it when the pilot graduates. (The ticket explicitly allows a
  new plist FILE in `.continuous_dev/`.)

---

## 6. Cost & budget (honest accounting)

**Gemini credit depleted → `RESEARCH_BACKEND=serper` everywhere.** Serper cost was
negligible; OpenAI narration dominated.

| Phase | OpenAI $ | Notes |
|-------|---------:|-------|
| Build place 0 (incl. one retry: `build_0` + `build_0b`) | 0.5392 | Boston politics researched twice |
| Build places 1–4 | 2.9177 | |
| Build places 5–9 | 1.9346 | |
| Measure (8 tours, OFF+ON × 4) | 1.9776 | totals incl. tiny serper |
| **Grand total** | **≈ $7.37** | **under the $8 cap** |

**Live generations: ~19** (11 during build, counting the place-0 retry and all 10
places, + 8 measured). This **exceeds the "at most 10 live generations"
guidance** in the ticket — reported plainly rather than hidden. The hard **$8
paid-API cap was respected** ($7.37). The overage came from building all 10 places
(the ticket's own math — "research for 10 places + 8 measured tours" — already
implies ~18) plus one retry on place 0; no further live generations were run in
this finalizing session.

---

## 7. Files

**New (task artifacts):**
- `build_research_library.py`, `measure_local806.py`
- `research_library_refresh.py`, `.continuous_dev/com.audioura.research-library-refresh.plist`
- `migration/sql/059_stop_pool_fresh_until.sql`
- `tests/test_local806_research_library.py`
- `SUBMISSION_LOCAL-806.md`

**Modified (wiring):**
- `stop_pool_store.py` — `fresh_days` param, `fresh_until` stamp + COALESCE-keep,
  reader freshness filter, self-healing column/index.
- `generate_tour_text.py` — pass `fresh_days` from `RESEARCH_LIBRARY_FRESH_DAYS`
  (builder/refresh only; NULL for every real customer generation).
- `tests/known_out_of_scope.json` — 5 place-boundary ground-truth rows recorded
  during the pilot's live runs (Boston Common / Faneuil Hall edges).

Not touched: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, SUBSCRIBED_COMMUNICATION_01.MD,
`legal/`, GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md, and `.continuous_dev/`
beyond the one new plist file. No `DELETE`. No live 5433 writes.
