**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-335
**Base:** storied
**Branch:** kiro/local335-gate-treats-offer

**Michael asked about this directly.** Small, user-facing, and it should land
before the next tour is delivered.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.40**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**Do not delete or modify any row in `audio_tours`.** Real count stays **29**.
**Do not INSERT into `treats`** — that is ad inventory and Michael's alone.

## The situation, measured

```
treats table               0 rows      no inventory, no vendor links
delivered tours (29 real)  0 mention   nothing shipped makes a promise
generated tour files       73 carry the Treat Page line
```

Michael, 2026-08-06: *"it is not engaged yet, right? We only reference it in
the tours, but no contracts with ad vendors are concluded at this stage."*
Correct on all counts.

`_build_closing_offer` (`generate_tour_text.py` ~1330) folds in a Treat Page
mention and **never queries `treats`**. The app side is location-aware —
`treats_screen.dart` calls `/treats-near/{lat}/{lng}` — so a listener who
follows the prompt reaches an empty screen.

The wording is already correctly hedged by LOCAL-280 ("whether there are
savings", never "for coupons") and that must not change. The problem is not the
claim; it is sending someone somewhere empty.

## Scope

1. **Gate the Treat Page mention on there being inventory near the tour.**
   Query `treats` by proximity using the same rule the app uses
   (`/treats-near/{lat}/{lng}`, `distance_in_feet`) — read the endpoint and
   match its semantics rather than inventing a second radius.
2. **No inventory means no mention.** The rest of the closing offer — the recap
   — must still be produced. Only the Treat Page sentence is suppressed.
3. **Fail closed.** If the lookup errors or coordinates are missing, omit the
   mention. A missing prompt costs nothing; a broken one costs a first
   impression.

## The line you must not cross

**Do not insert test rows into `treats` and leave them there.** If you need
inventory to test the positive path, use a transaction you roll back, or a
row you delete by an id you captured at creation after confirming it is yours
(D141). Report the row count before and after — it must be **0** both times.

**Do not change the approved wording** (LOCAL-280). Do not make the tour claim
savings exist. Do not add a second Treat Page mention anywhere.

**Do not rewrite the 73 existing tour files.** They are historical artifacts and
`tours/` is gitignored anyway.

## Verification
- With `treats` empty: generate a closing offer and show the Treat Page line is
  **absent** while the recap is still present. Quote both.
- With inventory present (rolled back): the mention appears, wording unchanged.
- Missing/NULL coordinates: mention absent, no exception.
- `treats` row count 0 before and after. `audio_tours` real count 29.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147).
- **Your tests must import production and fail against the unfixed version.**
  Break the gate, show a test going red, restore it, include the transcript
  (D242 — this has been an issue on six tasks tonight).
- **Accent-fold any `stop_corpus` join** (D243).

## Acceptance criteria
- Treat Page mentioned only when inventory exists nearby; recap unaffected.
- Fails closed on error or missing coordinates.
- Wording unchanged; `treats` still 0 rows; `audio_tours` still 29.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-335.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
