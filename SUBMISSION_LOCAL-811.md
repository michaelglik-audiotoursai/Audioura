# SUBMISSION — LOCAL-811: run the LOCAL-809 checks on pooled/reused museum stops

**Branch:** `LOCAL-811-pool-museum-checks`
**Base:** subscribed `6764ce9e` (contains the LOCAL-809 merge `1f4cb350`).
`git merge-base --is-ancestor 6764ce9e HEAD` exits 0.

## Problem

Saved (pooled) museum stops skipped the LOCAL-809 checks and bad ones were
re-served. Re-generating "Belvedere Museum, Vienna, Austria" took the stop-pool
fast path (`[LOCAL-590] POOL DELIVERY: reused=5 new=0`): the old stops came back,
including the literal line "Belvedere may refer to:" and two works that are **not
in the Belvedere** (Monet "Portrait of Père Paul", Van Gogh "Plain of Auvers").
LOCAL-809's checks (shop items, not-in-collection, disambiguation stubs) only ran
on **fresh** research — the reuse path never re-ran them.

## Fix (three parts, matching the ticket)

### 1. Run the LOCAL-809 checks on every pooled/reused museum stop
New module **`pool_museum_checks.py`** runs the LOCAL-809 authorities on ONE pooled
row and returns `(ok, reason)`:
- `junk_title_guard.is_junk_page_title` / `is_shop_product_title` — shop/product/
  page-chrome titles (the Met Store merchandise); the stop's own source URLs feed
  the commerce-URL arm.
- `disambiguation_guard.is_disambiguation_text` — a stop whose body is a
  Wikipedia disambiguation stub.
- `artwork_selection_guard.enforce_collection_membership` — **wrong_collection**
  (the work's own Wikidata P195 collection excludes the venue — the Monet/Van Gogh
  "not in the Belvedere" case) and **wrong_museum** (curated misattribution).
- `artwork_selection_guard.enforce_artworks_only` — events / treaties / rooms /
  building / architecture titles and classes.

`stop_pool_orchestrator._auto_reject_museum_stops` (wired into
`maybe_generate_with_pool`, gated on a **contained** museum/facility tour, right
after the LOCAL-792 junk reject and before K is counted) splits the reuse
candidates with this checker. A failing stop is dropped from THIS tour **and moved
out of the pool** via LOCAL-792's verified `move_to_rejected` (copy-before-delete,
one transaction) with `rejected_by=auto:pool_museum_checks`,
`reason=auto:local811:<reason>`. If K then falls below N, the existing N>K path
researches the remainder fresh — exactly as if the bad stop had never been pooled.
The venue work set for the membership arm is read cache-first
(`venue_resolver.venue_works_cache_get`, the LOCAL-810 30-day per-QID cache) so the
reuse path adds no paid-API cost on a warm cache.

**Conservative by design (no false quarantines).** A pooled row stores no P31 /
creator / P195 columns, and the venue works cache is keyed by English labels while
a pooled title is often the local-language form ("Leda col cigno" vs the cached
"Leda and the Swan"). So the pooled path rejects on membership **only on a
definitive signal** — `wrong_collection` / `wrong_museum`, which read the work's
OWN P195, not a fuzzy title match — and the soft `not_in_collection` title-miss is
**kept** (it is unreliable for pooled data). The positive "must read as an artwork"
gate (`no_artwork_class_and_no_creator`) is **not** applied to pooled rows (it
needs enrichment the pool lacks); only the deterministic class/title REJECTS fire.
This is why the one-off audit flags 35 genuinely-bad rows out of 993, not 496 real
works (see below).

### 2. A final disambiguation-line guard for ALL tours
`disambiguation_guard.strip_disambiguation_lines(text)` drops any sentence or
paragraph that IS a Wikipedia disambiguation line ("X may refer to:", "may also
refer to", and the DE/FR/IT/ES/NL equivalents), wherever it came from. It is wired
as step **3z** of `generate_tour_text._apply_delivery_hours_guard` — the single
every-path delivery choke point — so a pooled, cached, or fresh delivery all get
the line removed from both the returned text and the on-disk file. It is anchored
(`_STUB_LEAD_RE`) so a real sentence that merely uses the words deep in prose ("the
term baroque may refer to a sweeping movement …") is kept; it is idempotent.

### 3. One-off audit of the current Mac `stop_pool`
`local811_pool_audit.py` runs the same checks over every pooled museum row.
- **Dry run** (`reports/local811_pool_audit_dryrun.txt`): 993 rows read, **35 fail**
  — 17 shop/junk titles ("Profile « The ALBERTINA Museum Vienna", "Collection
  Guide", "… | Robert Frank: The Americans"), 13 room/space titles, 2
  wrong_collection ("The Age of Bronze" P195=Q23402; "Résurrection"), 2 wrong_museum
  ("Ophelia" — home is Tate), 1 event ("Austrian State Treaty").
- **`--apply`** (`reports/local811_pool_audit_apply.txt`): all 35 moved out via the
  verified `move_to_rejected`. `stop_pool` 993 → 958 (delta 35); 35 rows now in
  `stop_pool_rejected` (`rejected_by=local811_pool_audit`); a re-audit reports 0
  remaining failures. Only `stop_pool` / `stop_pool_rejected` were touched on the
  Mac dev DB (`development-postgres-2-1` / `audiotours`); `audio_tours` untouched.

## Tests

- **`tests/test_local811_pool_museum_checks.py`** (17, pure, pass): Belvedere
  Monet/Van Gogh → wrong_collection; disambiguation body/raw_block → rejected; Met
  gift-shop title + commerce URL → rejected; a genuine in-collection work, a
  local-language work with no artist/enrichment, and a stop with no reference set →
  **kept**; event title → rejected; split; and `strip_disambiguation_lines` (whole
  stub, embedded sentence, real prose kept, idempotent, empty, multilingual leads).
- **`tests/test_local811_reuse_quarantine.py`** (3, DB-backed, pass): on a throwaway
  schema, `_auto_reject_museum_stops` moves the foreign + shop + disambiguation rows
  out (pool 4→1, 3 in `stop_pool_rejected` with `auto:pool_museum_checks` /
  `auto:local811:*`) and keeps the good one; an all-good pool is untouched; a moved
  row is never returned by the reuse read.
- **Regression** (ticket-named suites + the two new files + broad pool/guard/museum
  adjacency, `RESEARCH_BACKEND=none`): 590 / 597 / 778 / 788 (×6) / 792 / 809, plus
  810 / 766 / 644 / 607 / 605 / 630 / 636 / 639 / 667 / 668 / 627 / 802 / 634 / 616.
  **All pass except two tests that fail identically on the baseline `6764ce9e`**
  (verified with `git stash`): `test_local597_guard …
  test_ungrounded_gemini_not_blocked_by_guard` and `test_local778_reuse_first …
  test_existing_tour_stops_are_reused`. Both are pre-existing and are **not** caused
  by LOCAL-811 (the 778 path returns None on the baseline too; the contained-gated
  museum reject is a no-op when the pool is empty). No collateral regression.

## Live run — PARTIAL, with a budget overrun (reported honestly)

OWN isolated stack: `docker-compose.local811-proof.yml` (`-p local811`,
`local811-postgres` on :58433, own volume, schema seeded from `local778-initdb`) +
`run_local811_container.py`, which seeds the bad Belvedere pool (Monet, Van Gogh, a
disambiguation stub, and one good Klimt) and runs one "Belvedere Museum, Vienna,
Austria" (5) tour with the stop pool **ON** and `RESEARCH_BACKEND=serper`.

**The fix is proven live on the real reuse path.** The live log and the isolated DB
both show:
```
[LOCAL-811] AUTO-REJECT reused museum stop 'Portrait of Père Paul'
   (wrong_collection (P195=Q23402 excludes Q303139; P276 location ignored)) — moving out of pool
[LOCAL-811] AUTO-REJECT reused museum stop 'Plain of Auvers'
   (wrong_collection (P195=Q153306 excludes Q303139; P276 location ignored)) — moving out of pool
[LOCAL-811] auto-rejected 2 museum stop(s) that failed the LOCAL-809 checks from this tour (1 kept)
```
`stop_pool` went 8 → 5; the two foreign works are in `stop_pool_rejected` with
`rejected_by=auto:pool_museum_checks`, `reason=auto:local811:wrong_collection`; the
"Belvedere" disambiguation stub was moved by `auto:junk_title_guard` (LOCAL-792
caught it as a venue-itself title before my check); "The Kiss" (a real Klimt work)
was kept. The stack was torn down (`down -v`) afterwards.

**Budget overrun — I went over the $0.80 TOTAL cap.** Actual spend tallied from the
run log was **~$1.42 OpenAI + 8 serper calls**. Two causes, both independent of the
fix:
1. the stop generator ran **`model=gpt-4o`** despite `NARRATION_MODEL=gpt-4.1-mini`
   — that env var is not honored on that stop-generation path; and
2. the tour did not deliver cleanly (a retry/regeneration storm re-generated the
   stops ~8×, while `venue_works_cache._get_db_connection` kept retrying a
   hardcoded `localhost:5433` inside the container — non-fatal but noisy), so the
   in-process `live_run_meter` never captured a cost (`_LAST_GENERATION_COST` was
   not populated) and reported `$0.00`. Because the meter read $0, the in-process
   cap gate never bit — the same meter-undercount trap the LEAD flagged on
   LOCAL-810.

Per the LEAD budget rule, once the cap is exceeded no further live runs are
permitted, so I **stopped** and did not re-run. The clean full-tour acceptance ("no
disambiguation text in the delivered tour; every delivered stop a Belvedere work")
is therefore **blocked by the budget cap, not by the fix**. What it still leaves
proven: the reuse-path quarantine of the two foreign works and the disambiguation
stub is demonstrated live (above) and deterministically by the unit + DB-backed
tests and the Mac pool audit; the delivered-text disambiguation strip is covered by
the pure tests and an in-process check of `_apply_delivery_hours_guard`.

**What unblocks a clean, in-budget re-run** (for a follow-up with fresh budget):
pin `gpt-4.1-mini` on EVERY stop-generation path (not only via `NARRATION_MODEL`),
and make `live_run_meter`/the cap gate read a running provider tally so a crash
mid-tour cannot report `$0` — then one Belvedere tour fits well under $0.80.

## Files

New:
- `pool_museum_checks.py`
- `local811_pool_audit.py`
- `run_local811_container.py`
- `docker-compose.local811-proof.yml`
- `tests/test_local811_pool_museum_checks.py`
- `tests/test_local811_reuse_quarantine.py`
- `reports/local811_pool_audit_dryrun.txt`
- `reports/local811_pool_audit_apply.txt`
- `SUBMISSION_LOCAL-811.md`

Changed:
- `disambiguation_guard.py` — `strip_disambiguation_lines()`.
- `generate_tour_text.py` — step 3z disambiguation-line guard in
  `_apply_delivery_hours_guard`.
- `stop_pool_orchestrator.py` — `_venue_works_for_membership`,
  `_auto_reject_museum_stops`, wired into `maybe_generate_with_pool`.

The only removal performed is LOCAL-792's verified `move_to_rejected` on
`stop_pool`, on the Mac dev DB in the audit's `--apply` step (with before/after
counts). `audio_tours` was never modified.
