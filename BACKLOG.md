# Backlog — pull from here whenever the queue drops below 3 in flight

Michael, 2026-07-31: *"Please make sure you and Kiro work all the time. If
something is blocked, find another task to do."*

**Rule: the queue is never empty.** If a task is blocked — waiting on a
rebuild, an external service, a decision that turns out to be irreversible —
do not idle. Write the next item below into a
`new_kiro_session_is_required_LOCAL-NN.md` and dispatch it.

Ordered by value, but **pick any unblocked item** rather than waiting for a
blocked higher one. Every item is independent unless marked otherwise.

---

## Tier 1 — Subscribed critical path

- **LOCAL-63 — stale-container guard.** The tour-generator ran two-day-old
  code for two days; 823 lines of story mining never executed, and every
  cost measurement was wrong as a result. Add a startup assertion comparing
  a manifest of source checksums against the image, failing loudly on
  mismatch. Silent staleness has now cost us twice.
- **LOCAL-64 — re-measure true generation cost** once the rebuild lands.
  Fresh tour, corpus mining active, `search > 0` in the breakdown. This is
  the number the whole ×5 pricing rests on. Blocked on the rebuild only.
- **LOCAL-65 — pricing engine.** `our_cost × PRICING_MULTIPLIER`, all values
  from config (`SUBSCRIBED_DESIGN.md`). Depends on LOCAL-60 landing.
- **LOCAL-66 — wallet ledger + balance.** Credits, debits, top-ups, refund
  clawback allowed to go negative. Depends on LOCAL-61.
- **LOCAL-67 — entitlement enforcement at the gate.** `remind_mobile_ai.md:40`
  says the cloud gateway already checks quota/entitlements using `user_id`.
  Investigate and **extend rather than duplicate**. Read before building.
- **LOCAL-68 — wallet API endpoints** matching the contract LOCAL-62 mocked.
- **LOCAL-69 — news-path metering.** LOCAL-60 defined `news_generate` but
  did not wire it. Michael's model explicitly covers *"both articles and
  tours."*

## Tier 2 — quality debt that blocks trust in measurement

- **LOCAL-70 — audit every swallowed ImportError.** The stale-container bug
  hid behind `try/except ImportError`. Same pattern killed the story engine
  for weeks. Find every one in the generation path; make them log at ERROR
  with the missing symbol named, never silently continue.
- **LOCAL-71 — re-verify corpus work that was "approved" against a stale
  container.** LOCAL-24/25/32/33 were reviewed by reading diffs while the
  container never ran them. Re-run their acceptance criteria for real.
- **LOCAL-72 — LOCAL-48 review** (outdoor fact retrieval + 80-word cap on
  factless stops). Unmerged. Michael prefers fact-rich with errors over
  clean and empty — measure distinct facts before/after; **any merge that
  cuts distinct facts is a bounce.**
- **LOCAL-73 — LOCAL-38 (SQ4b theme threads / dominant story).** LIVE with a
  one-file conflict per `BRANCH_RECONCILIATION.md`. This is the feature
  Michael asked for ideas on; `STORY_QUALITY_DESIGN.md` §SQ-S6b specifies it.
- **LOCAL-74 — LOCAL-39 (visitor facts).** LIVE and merges clean. Includes
  the Musée Matisse "Free admission" error — it charges €12.
- **LOCAL-75 — LOCAL-34 (Palais residues).** LIVE, conflicts in 4 files.

## Tier 3 — hygiene, safe to run any time

- **LOCAL-76 — purge test tours from the live DB.** Ids 36, 37, 39–43 are
  test artifacts; I nulled their coordinates to hide them (backup in
  `scratchpad/testrows_backup.txt`). Decide keep-or-delete and enforce that
  tests never write user-visible rows. **Deleting rows is irreversible —
  hide, do not delete, unless Michael has confirmed.**
- **LOCAL-77 — fix `tests/test_local30_acceptance.py`** hardcoding port 5432
  where Postgres publishes 5433.
- **LOCAL-78 — fix or delete `test/widget_test.dart`**, which references a
  non-existent `MyApp` and has failed since before the 188-commit baseline.
- **LOCAL-79 — dev credentials in a public repo.** `postgresql://admin:password123@`
  appears in ~8 files. Low risk (disposable localhost DB) but it trips
  secret scanners. Move to env vars.
- **LOCAL-80 — dispatcher branches off `storied` regardless of task.**
  `setup_worktree()` hardcodes it, which is why `subscribed` stayed empty.
  Make the base branch a task-file field.
- **LOCAL-81 — the 49 dead test files** importing modules that no longer
  exist (removed news/podcast area). They make every suite run look broken.
  Delete or quarantine.

## Tier 4 — Michael's standing asks, not yet scheduled

- **Swipe-to-sway stops** correlated to Historical / Details / Social
  (`STORY_QUALITY_DESIGN.md` §2c/2d; `stop_metrics.class_*` has 411 rows).
- **Photo-of-a-POI → tour extension.** Named as a future higher-cost service
  in `SUBSCRIBED_DESIGN.md`; metering must already handle it by operation type.
- **Tour sharing** between users — expected to be free.
- **Generic feature-development playbook** so Windows can run features in
  parallel. Michael asked for this on 2026-07-29 and it is still unwritten.
