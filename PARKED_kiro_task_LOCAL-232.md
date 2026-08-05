**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-232
**Base:** storied
**Branch:** kiro/local232-tests-off-production-db

# ⛔ PARKED — unpark only after Michael's read-evaluation is finished

Changing test fixtures while he is evaluating would change what the suites
report mid-review. LEAD unparks by renaming to
`new_kiro_session_is_required_LOCAL-232.md`.

---

# Tests must stop writing to the production database

Read `DECISIONS.md` **D118**, D109 (`audiotours_subscribed` as precedent),
CLAUDE.md's live-database rules, `tests/db_connection.py`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.10**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `.continuous_dev/*`.

## The problem

Eight test suites `INSERT INTO audio_tours` against the **production**
database:

```
test_local128_stop_metrics_tourid.py   test_local183_controlled_ab.py
test_local183_stop_corpus_wiring.py    test_local186_venue_disambiguation.py
test_local139_acceptance.py            test_local183_evidence.py
test_tour_factory.py                   test_tour_helper.py
```

`audio_tours` went 133 → 138 in two hours of ordinary review work. Every row is
`is_test = true` with NULL coordinates, so nothing reached Michael's app — but
it is one forgotten flag away from **LOCAL-49**, which put two test tours in
front of him.

It also means the row-loss alarm watches a number that drifts for reasons that
have nothing to do with production.

## Scope

1. **A test database.** `audiotours_test`, created by an idempotent migration,
   schema derived from the production schema. The subscribed track already does
   this (D109) — follow that pattern rather than inventing another.
2. **Point the fixtures at it.** `tests/db_connection.py` should resolve to the
   test database when running under pytest, and to production only when
   something explicitly asks for it. Say how you decided which is which.
3. **Fail loudly on a production write from a test.** A guard that raises if an
   INSERT into `audio_tours` happens while pytest is running. This is the part
   that keeps it fixed — the convention alone will erode.

## Do not

- **Do not delete the existing test rows.** They are `is_test = true` with NULL
  coordinates and invisible to users; removing 100+ rows from the live table is
  exactly the irreversible action CLAUDE.md gates, and the tour-29 deletion is
  why. Michael decides that separately.
- **Do not touch production data at all** — creating a new database is
  additive; altering `audiotours` is not.
- Do not weaken any test to make it pass against the new database. If a test
  genuinely needs production data, say so and leave it, listed.

## Acceptance criteria

- `audiotours_test` created by idempotent migration; second run a no-op.
- All eight suites run green against it.
- A production-write guard that raises under pytest — demonstrate it firing.
- **`audio_tours` unchanged before and after your work** — report the count and
  the Nice list `[1,12,14,17,21,24,27,28,29,152]`.
- Any test that genuinely requires production listed with the reason.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Never `DELETE FROM audio_tours`.
**Run every example you paste and confirm the output matches** (D97, D103).
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-232.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
