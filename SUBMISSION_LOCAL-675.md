# SUBMISSION — LOCAL-675 (four follow-ups, night of Oct 10–11)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-675-followups`
**Base:** `subscribed` = **d71bfed7** (`Merge LOCAL-672/672B …`), which contains the LOCAL-672 merge.
**No paid calls. Own containers only. No GCloud. No DELETE of anything but each test's own `TEST-*` rows.**

## Base / branch correctness

The worktree was checked out at `subscribed = d71bfed7`. An earlier pass of this
work had been branched from the **stale** `subscribed @ 0ac9c4b9` (the LOCAL-670C
merge, which predates LOCAL-672). That is the exact failure the BASE note warns
about, and it mattered: the Addendum's item-4 file (`test_local670c_sync.py`)
only errors *after the LOCAL-672 merge*, so it cannot be reproduced or fixed on
`0ac9c4b9`.

Fix: the four item commits were rebased onto `d71bfed7`
(`git rebase --onto d71bfed7 0ac9c4b9 …`), and item 4 was then completed for the
post-merge world. Ancestry is verified:

```
git merge-base --is-ancestor d71bfed7 HEAD   # exit 0 ✓
```

Commits (one per step, on top of `d71bfed7`):

```
e245778a  LOCAL-675 item 4: fix test isolation so the full suite runs the 670 tests green
79fbc459  LOCAL-675 item 3: make critic rubric criterion 3 category-aware
ad862250  LOCAL-675 item 2: relative-time phrases must match the dates
ba8fe3ff  LOCAL-675 item 1: keep bilingual 'Local (English)' header through Phase 3B
```

---

## Item 1 — bilingual stop headers now render "Local (English)"

**Symptom (fixture `~/Audioura/.continuous_dev/bench/AB17/run_OFF-1.log`):** the
LOCAL-669C final identity gate logs `bilingual titles: set 4 '<local> (<English>)'
header(s)` (line 205), yet the delivered HCMC stops are bare Vietnamese
("Stop 3: Bác Hồ với thiếu nhi", lines 566–574) with no English.

**Root cause:** the gate writes the bilingual title to `display_title`
(`identity_dedup.py:640`), and the PHASE 6 header build prefers it
(`generate_tour_text.py:25316`). But **PHASE 3B** rebuilds every stop with a
fresh `_new_poi()` dict and only carried `verified` across — it silently dropped
`display_title`, so the header fell back to the bare `name`.

**Fix (`generate_tour_text.py`):**
- Carry `display_title` through the Phase 3B rebuild, next to `verified`.
- Harden the LOCAL-22 final sanitizer so a delivered bilingual header is
  recognised as a REAL header (both the exact-set and the normalised fallback
  now compare against `display_title`), and is never stripped as injected text.

**Tests:** `tests/test_local675_bilingual_header.py` → **8 passed, exit 0**
(includes a fixture-symptom assertion). Offline; no paid run.

---

## Item 2 — relative-time phrases must match the dates

**Symptom:** Boston 557 v12 said "Three years later, … In 1770" after a prior
sentence dated 1742 — the real gap is 28 years.

**Fix (`date_consistency_guard.py`):** extend the LOCAL-630 item-8 year-span
check (`recompute_year_spans`) beyond the digit form to the non-digit
relative-time phrases, each measured against the **previous dated sentence** in
the same stop:
- `"<word-number> years later/after"` ("Three years later")
- `"a decade later/after"` (= 10 years)
- `"the following year"` / `"the next year"` / `"the year after"` (= 1 year)

New `_recompute_relative_spans()` walks the body sentence by sentence, anchoring
each phrase to the date that actually precedes it (not the whole-body min/max).
It **corrects** the phrase to the true span when the arithmetic is off (within a
2-year tolerance), or **drops** it (re-capitalising the sentence) when two anchor
years cannot be found — an unverifiable computed number is worse than none. The
guard now triggers on `has_digit OR has_relative`; idempotent; on every delivery
path (not museum-gated).

**Functional proof:**
```
"… founded in 1742. Three years later, in 1770, the spire rose."
  -> "… founded in 1742. 28 years later, in 1770, the spire rose."   (corrected 3 -> 28)
"… founded in 1742. Three years later, the spire was completed. In 1770 it burned."
  -> "… founded in 1742. The spire was completed. In 1770 it burned."  (dropped: only one anchor in that sentence)
```

**Tests:** `tests/test_local675_relative_time.py` → 12 passed; together with the
existing LOCAL-630 item-8 suite and the other guard consumers
(`test_local630_venue_truth.py`, `tests/test_local626_invented_facts.py`,
`tests/test_local654_no_midclause_collision.py`) → **54 passed, exit 0**, no
regression. Offline; no paid run.

---

## Item 3 — critic rubric criterion 3 made category-aware

The listener-critique harness is **`~/Audioura/.continuous_dev/calib/critique.sh`**.
It lives *outside* the git worktree (the worktree root is
`/Volumes/AudiouraSSD/audioura-worktrees/LOCAL-675`), and `.continuous_dev/` is
gitignored (only top-level `*.sh` are negated, not files in sub-directories), so
it cannot be captured directly by a branch commit.

**Change applied to the live harness:** criterion 3 was museum-only —
`"hours and admission are SPOKEN, not 'check the website'"` — which penalises
walking tours that have no admission desk. The script now reads `Tour-Category:`
from the raw `tour_content` (BEFORE the field lines are stripped out of the
spoken text it critiques) and selects criterion 3 accordingly:

```
CAT = lowercased Tour-Category value
walking  -> "directions between stops are clear, with distances"
otherwise -> "hours and admission are SPOKEN, not 'check the website'"   (unchanged)
```

Everything else — criteria 1, 2, 4–8, the output format, the read-only contract —
is untouched. Category match is case-insensitive; unknown/missing category falls
back to the original criterion (museum and restaurant tours score exactly as
before).

**Captured on the branch** under `submission_artifacts/local675/`:
- `critique.sh` — a vendored copy of the modified harness (byte-identical to the
  live file: `diff` exits 0).
- `critique_sh_change.md` — records what changed, why it is vendored, and the
  verification.

**Verification (offline, no paid call):** `zsh -n critique.sh` → syntax OK; the
`Tour-Category` → criterion-3 selection exercised in isolation:
`walking → directions/distances`, `Museum`/`WALKING`/missing/`restaurant` →
original hours/admission criterion.

---

## Item 4 — test isolation (full-suite green for the 670 family + killswitch)

`tests/test_local670_tour_ratings.py`, `tests/test_local670b_listened_gate.py`
and **`tests/test_local670c_sync.py` (Addendum)** passed alone but ERRORed at
setup in the full `pytest tests` run; `tests/test_gcs_ks1_user_stops_killswitch.py`
also had three orchestrator-entry tests FAILING in the full run — the same
family, surfaced by the LOCAL-672 merge at `d71bfed7`.

**Root causes** (leaks that cross test-module boundaries and were never torn
down, plus a stub that went stale on the merge):

1. **psycopg2 stub leak.** `test_gcs_ks1_user_stops_killswitch.py` overwrote
   `psycopg2.connect` with a `RuntimeError("no DB in test")` stub and never
   restored it, so every DB-backed test later in the session failed at setup.
   This was *the* full-suite blocker for `test_local670*`.
   **Fix:** capture the real (conftest-guarded) connect once and restore it in a
   new `tearDownModule()`.

2. **Production-target env leak.** `test_local447` / `test_local448` set
   `AUDIOURA_DB_TARGET=production` at module scope. That var outranks pytest's
   test-DB auto-detection, routing later tests at the production DB and tripping
   the conftest write-guard. **Fix:** scope the production target into the
   live-integration `setUp`/`tearDown` (saving/restoring `AUDIOURA_DB_TARGET`,
   `DATABASE_URL`, `PGOPTIONS`), removing the module-scope leak.

3. **[Addendum / LOCAL-672] stale quota-gate stub.** After the merge the
   orchestrator's authoritative generate gate became
   `entitlements.check_operation` (the LOCAL-595 levels model), which opens the
   DB. The killswitch test only stubbed the old `check_tour_quota`, so with
   psycopg2 stubbed the gate failed closed → 429 and the switch logic never ran
   (3 FAILED). The orchestrator also calls `orchestrate_tour_async` positionally
   via `threading.Thread`, and the merge added an 11th arg (`mode`), so the old
   10-arg thread stub raised *"takes 4 to 10 positional arguments but 11 were
   given"*. **Fix:** stub `check_operation` to an allow (captured and restored in
   `tearDownModule`) and widen the thread stub to accept `mode`.

**Belt-and-braces:** all three 670 modules now carry an autouse fixture that
pins `AUDIOURA_DB_TARGET=test` (and clears any leaked `DB_NAME`/`DATABASE_URL`)
for their DB-backed tests and restores the environment afterwards —
`test_local670c_sync.py` gained this fixture in this pass.

### Full-suite proof (offline, no paid calls)

Two full `pytest tests` runs on this machine:

| run | failed | passed | errors |
|-----|-------:|-------:|-------:|
| clean `d71bfed7` base | 179 | 4215 | 286 |
| this branch           | **161** | **4505** | **43** |

Every count moves in the right direction (errors −243, failures −18, passed
+290) — a strict improvement with no regressions. **All four target files show
ZERO FAILED/ERROR lines in the full-suite run on this branch**, and were
confirmed ERRORing/FAILING on the clean base (8 + 9 + 8 errors across the three
670 files, 3 killswitch FAILs). The suspicious files that fail only in the full
run (`test_local325_db_target_isolation`, `test_local672_verified_reviews`,
`test_local597_guard`) were verified **already failing on the clean base** — a
pre-existing cross-module contamination unrelated to this ticket. The remaining
161/43 are pre-existing live-service tests (wallet, newsletter, cloud, zip) that
need running microservices, outside this ticket.

### Per-item suite exit codes (this branch)

```
item 1  tests/test_local675_bilingual_header.py                                  8 passed  exit 0
item 2  tests/test_local675_relative_time.py + 630/626/654 guards               54 passed  exit 0
item 4  670 + 670b + 670c + killswitch (together)                               49 passed  exit 0
item 4  killswitch + 447 + 448 + 670 + 670b + 670c (leak-source ordering)       74 passed  exit 0
```

---

## Process notes

- Commit after each step; one commit per item, all on top of `d71bfed7`.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md` or
  `.continuous_dev/STATUS.md`.
- No paid calls, no network generation, no GCloud, no destructive DB operations;
  the DB-backed tests only ever delete their own `TEST-*`-prefixed rows by exact
  id.
- Push: `git push origin LOCAL-675-followups`.
