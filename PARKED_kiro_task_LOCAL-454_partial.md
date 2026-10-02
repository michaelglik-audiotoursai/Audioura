# TASK LOCAL-454 — A prompt is not a constraint, and a grep is not a test

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-454-validate-phase3a-against-checklist
**Base:** LOCAL-453-checklist-must-bind-candidates

## Why this exists

LOCAL-453's root-cause analysis is the best part of this chain and it stands. It traced
the failure precisely: `prose_llm_extract_works()` is non-deterministic, returned `[]` on
run 1, so `has_works=False`, so the code fell through to Phase 3A with the 8,215 chars of
retrieved page text sitting unused in memory. That diagnosis is correct and this task
builds on it, not over it.

**Layer 1 is genuinely structural and stays.** Retry extraction → deterministic
`poi_list` fill → Phase 3A skipped entirely. There is no path from "deterministic fill
succeeded" back to unconstrained selection. That is real.

Three things are wrong.

## Defect 1 — a test fails on the submitted branch, and the submission says none do

`SUBMISSION_LOCAL-453.md` states: *"13 tests, all pass."*

LEAD ran them on your branch, unmodified:

```
tests/test_local453_checklist_must_bind_candidates.py
  ::TestChecklistPageTextConstrainsPhase3A::test_retry_extraction_binds_candidates
  assert len(result) >= 3
  E  assert 0 >= 3
1 failed, 12 passed
```

An unproven claim stated as complete is the one thing the PROCESS section rules out. The
report was otherwise honest — it says plainly that the live runs were not executed and
hands the gate to LEAD, which is the correct move and is appreciated. That makes this
line an error rather than a pattern, but it has to be named: **run the suite and read the
output before writing "all pass."**

## Defect 2 — the D242 evidence does not bind

The submission offers `TestConstraintIsStructural::test_checklist_binding_variable_required`
as the neutralisation check. It reads the *source text* of `generate_tour_text.py` and
asserts three strings appear in it.

LEAD neutralised the **behaviour** while leaving every one of those strings intact — one
added line blanking `_checklist_page_text_for_phase3a` immediately after it is assigned,
so Layer 2 can never fire:

```
1 failed, 12 passed      (before neutralisation)
1 failed, 12 passed      (after)
```

**Identical.** The binding was destroyed and not one test noticed. A test that greps for
a variable name proves the variable name is present; it says nothing about whether the
code runs. This is the same failure that sank the LOCAL-447 Wayback tests at D408, in a
different costume — there the tests patched the function they claimed to test, here they
read the source instead of executing it.

## Defect 3 — Layer 2 is a prompt, and the code calls it structural

```python
# This is the structural binding: the LLM cannot propose works that
# are not in the checklist text, because the text IS the source of truth.
if _checklist_page_text_for_phase3a:
```

The LLM absolutely can. Nothing compares Phase 3A's returned titles against the text. The
mechanism is four lines of emphatic instruction — `You MUST select works ONLY from the
text below`, `Do NOT use your own knowledge` — and instructions of exactly that kind are
what produced *The Weeping Woman* in the first place, since Phase 3A already carried
LOCAL-425's "list works from THIS EXHIBITION" and ignored it.

The submission's argument, *"It cannot propose The Weeping Woman because that string does
not appear in the MFA exhibition page text"*, is the claim that needs the test, not a
substitute for one.

## What to build

**Validate Phase 3A's output against the checklist text.** After Phase 3A returns
candidate titles, when `_checklist_page_text_for_phase3a` is non-empty:

1. Accent-fold both sides (D243 — the existing `_strip_accents` pattern; French titles
   are the norm here, not the exception).
2. Drop any candidate whose title does not appear in the checklist text.
3. Log every drop with the title and the reason, in the style of the existing
   `[D1v2] DROPPED '<title>' — no canonical title match` lines.
4. If everything is dropped, let the existing clean-fail path run. **Do not** substitute
   works to avoid a failure — a clean fail is the correct outcome and D1v2 already does
   it well.

Keep the prompt constraint. It probably helps. It is just not the guarantee.

## Rewrite the tests so they exercise behaviour

Delete the source-grep tests or keep them only as a supplement — they must not be the
D242 evidence. Every claim needs a test that calls the code:

- Feed a fixture checklist text plus a Phase 3A response containing two in-text titles
  and one out-of-text title (*The Weeping Woman* is the obvious choice). Assert the
  out-of-text title is dropped and the two survive.
- Assert accent-folded matching works: a checklist containing `Le Lézard aux plumes d'or`
  accepts a candidate spelled `Le Lezard aux plumes d or`.
- Assert that when every candidate is out-of-text, the result is a clean fail rather than
  a partial tour.
- Fix `test_retry_extraction_binds_candidates` so it passes, or explain why the assertion
  is wrong and change it. Do not delete it.

**The acceptance bar for the D242 check is the one LEAD used:** neutralise the validator
so it drops nothing, leave every string in the file untouched, and a test must go **red**.
Show the before/after counts.

## Live acceptance (LEAD ran none of this yet; it is yours to run)

LOCAL-453 correctly said it could not run the container. You can — the container is
`audioura-tour-generator-1`, and the command is in `new_kiro_session_is_required_LOCAL-453.md`.
Rebuild the image from your worktree first so it carries your code.

- **Five consecutive runs** of the MFA request. Every run produces a tour; every stop in
  every run appears in the checklist text. Table: run, outcome, chars, stop titles.
- LOCAL-453 argued five suffice because the binding is structural. **With the validator
  in place that argument becomes true**, so five is accepted — the argument was sound,
  it just described code that did not exist yet.
- The three banned works (*The Weeping Woman*, *The Farm*, *The Persistence of Memory*)
  must appear in none of them.
- Regression: `test_sq4_merge.py`, `test_palais_fix_lead_fixture.py`,
  `test_local12_fact_retrieval_fix.py`, and the 447–451 suites (76 tests).
- Regenerate `Musée des Arts Asiatiques, Nice` at 8 stops. LOCAL-453 reasoned it cannot
  be affected because the code sits inside `elif _exhibition_scope is not None:`. The
  reasoning is probably right, but that tour is the **release gate artifact at 81.2** and
  reasoning is not measurement. Run it and report the score.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-454-validate-phase3a-against-checklist`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Record reasoning in `SUBMISSION_LOCAL-454.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever.
- Commit at least once
  (`git rev-list --count LOCAL-453-checklist-must-bind-candidates..HEAD >= 1`).
- Run every test you cite and paste the real output. "Unproven, handing to LEAD" is
  always acceptable; "all pass" when one does not is not.
