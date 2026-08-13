# TASK LOCAL-457 — stop searching for a title that does not exist

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-457-strip-gloss-before-query
**Base:** storied

> **PARKED — do not dispatch until LEAD removes the `PARKED_` prefix.** Michael asked to
> work on story generation jointly when he is back (2026-08-12 ~22:30). This task edits the
> path that feeds the story pass; running it underneath that session would waste it. It is
> ready otherwise — one rename dispatches it.

## The defect

Stop titles carry an English gloss we add ourselves. That glossed string is then used to
build search queries, as an **exact phrase**:

```
"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" Joan Miró
"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" history
```

No source on the internet writes the title that way. The quotes guarantee those queries
return nothing about the work. Six of stop 1's nine queries are built this way.

Production confirms the glossed title reaches the searcher:

```
[work_stories] MISS for le lezard aux plumes dor the lizard with
  Stop 1 'Le Lézard aux plumes d’or (The Lizard with Golden ': queries=9 serp_results=55
  Stop 2 'Moses and Monotheism':                               queries=4 serp_results=26
  Stop 3 'Au Soleil du Plafond':                               queries=4 serp_results=29
```

Stop 1 — the only stop with a gloss — spends more than twice the queries and is the only
one hunting a string that cannot be found.

`corpus_coverage.assess_stop_coverage` has the same problem downstream: it derives content
words `['lezard','plumes','lizard','golden','feathers']` and looks for the English ones in
French sources.

## The fix already exists and is not wired

`generate_tour_text.py:4000` defines `_strip_parenthetical_translation(title)`. Verified by
LEAD:

```python
>>> _strip_parenthetical_translation('Le Lézard aux plumes d’or (The Lizard with Golden Feathers)')
'Le Lézard aux plumes d’or'
```

Correct output. It is simply not applied to the stop record before
`work_story_searcher.synthesize_queries` and `corpus_coverage.assess_stop_coverage` see it.

## What to do

1. **Find every place the stop record is built** for the story-search path and apply the
   strip to `canonical_title` there. Keep the glossed title for anything user-facing —
   the tour text should still say the gloss; only the *query* and *coverage* keys change.
   Say in your submission which call sites you found and which you changed.
2. **Do not strip in the wrong direction.** `local_title` may legitimately be the
   non-English title. If both keys end up identical, say so and explain why that is right.
3. **Check `normalize_work_key`** — the cache key currently embeds the gloss
   (`le lezard aux plumes dor the lizard with`). Changing it changes cache hits. Decide
   whether to change it, and justify either way; a stale-key miss is cheap, a wrong hit
   is not.

## Acceptance (live-artifact gate)

- A unit test that feeds a glossed title through the real query builder and asserts no
  query contains the gloss. **Neutralise it** — revert the strip at the call site — and
  show the test go **red**, then green. Source-grep tests do not count (D418, D421).
- A live run of the MFA tour showing stop 1's queries without the gloss, pasted verbatim,
  next to tonight's 9-query log line for comparison.
- Report `serp_results` for stop 1 before and after. **A drop is not automatically a
  failure** — fewer, better-targeted results may be the right outcome. Report it honestly
  either way; do not tune to make the number go up.
- Regression: `test_sq4_merge.py`, `test_palais_fix_lead_fixture.py`,
  `test_local12_fact_retrieval_fix.py`, and the 447–451 suites.

## Docker rules — read before your first container command

- Build from the worktree is fine: `docker build -f Dockerfile.generator -t audioura-tour-generator-local457 .`
- `docker run --rm --network development_default`, **never with `-p`**.
- **Never `docker-compose up/down/recreate` from the worktree.** Compose names the project
  after the directory and will remove the canonical container and seize its host port.
  Port 5000 is the iPhone app's. It was taken for ~1 hour on 2026-08-12 (D419).
  The guard that was supposed to prevent this does not work (D422) — nothing will stop you.
- To use the running generator, `docker exec` against `audioura-tour-generator-1`.
- `docker ps --filter publish=5000` must show `audioura-tour-generator-1` when you finish.

## Time

Your three predecessors died or were stopped at 62, 37 and 71 minutes with **nothing
committed**, and LEAD salvaged all three by hand. **Commit as soon as anything works.**
Partial and committed beats complete and lost.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-457-strip-gloss-before-query`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Record reasoning in `SUBMISSION_LOCAL-457.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever.
- Commit at least once (`git rev-list --count storied..HEAD >= 1`).
- Run every test you cite and paste the real output. "Unproven, handing to LEAD" is always
  acceptable; "all pass" when one does not is not.
