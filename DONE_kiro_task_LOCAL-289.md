**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-289
**Base:** storied
**Branch:** kiro/local289-degrade-path-stubs

# Dropping a name leaves wreckage in the sentence.

Read `DECISIONS.md` **D194**, `unglossed_reference_gate.py` (the DEGRADE path —
LOCAL-287 rewrote Stage 3/4, this is the branch that drops a name instead of
glossing it), `tours/LOCAL287_riviera_2stop_round35.txt`,
`tours/LOCAL287_riviera_8stop_round35.txt`.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## What is wrong

LOCAL-287 fixed gloss **composition** and it genuinely works — verified on
delivered prose. But the **degradation** path, which drops a name when no gloss
can be composed, cuts the name out and leaves the surrounding syntax broken.

Three instances from the two tours it generated, all verbatim:

```
The iconic cape, along with to the northeast, has witnessed centuries of
maritime history.

... showcases nature's enduring power in shaping 's landscape.

The sacred space serves as a sanctuary for both the body and the soul during
your cycling tour a.
```

1. **`along with to the northeast`** — the name was removed from between "with"
   and "to", leaving two stacked prepositions and no object.
2. **`in shaping 's landscape`** — the name went but its **possessive `'s`
   stayed**. The submission added a possessive handler for gloss *insertion*;
   this is the *removal* side and is unhandled.
3. **`during your cycling tour a.`** — a dangling article terminating a sentence.

This is text bound for text-to-speech. A listener hears "in shaping apostrophe-s
landscape".

## Root cause

The degrade path treats the name as a span to delete. It is not — it is a **noun
phrase filling a grammatical slot.** Deleting it leaves the slot empty and the
function words that pointed at it stranded.

## Scope

**Degrading must remove the whole construction the name governed, not just the
name.**

When dropping a reference, also remove:

- a possessive clitic bound to it — `X's landscape` → `the landscape`, never
  `'s landscape`;
- prepositions and articles left with no object — `with to the northeast`,
  `tour a.`, `of the .`;
- an appositive or coordination that becomes empty — `the cape, along with ,`.

**If the sentence cannot be left well-formed, drop the whole sentence.** That is
the correct fallback and it is strictly better than emitting broken syntax. The
gate already has a sentence-level deletion path for other rules; reuse it rather
than adding a parallel one.

## Mechanical guards — assert on final text

Extend LOCAL-287's `validate_gloss()` guards to cover the degrade output, and
run them over the **whole assembled tour**, not just the modified sentence:

| must never appear in delivered text |
|---|
| a bare possessive: `\s's\b` with no word before it |
| two stacked prepositions: `with to`, `of in`, `at of`, `in of`, `to of` |
| a sentence ending in an article or preposition: `\b(a|an|the|of|in|at|to|with|from|and)\.` |
| an empty appositive: `,\s*,` or `,\s*\.` |
| a double space left by the excision |

A guard failure must **drop the sentence** and log it, never ship it.

## The line you must not cross

**Do not fix this by glossing more aggressively.** The degrade path exists
because some references genuinely cannot be glossed from available corpus —
LOCAL-269's own title is "gloss, or lose the name", and losing the name is
correct. The bug is *how* the name is lost, not *that* it is lost.

**Do not touch the composition path.** It is verified working and merged
(`4124068`). Leave `compose_glosses()` and `_host_sentence_already_explains()`
alone.

## Then regenerate

**2-stop and 8-stop Riviera**, plus a **5-stop museum**. Copy all to
`/Users/micha/Audioura/tours/`.

Report: every degradation the gate performed, with the sentence **before and
after**, and the five guards checked explicitly over the full tour text. State
how many degradations resulted in a dropped sentence.

**Read the delivered tours as prose before reporting (D161).** LOCAL-287 passed
28 unit tests and shipped `'s landscape` — the prose read is what caught it.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria

- No bare possessive, stacked preposition, dangling article, or empty appositive
  in any delivered tour.
- Degradation removes the whole governed construction, or drops the sentence.
- Composition path untouched.
- Guards run over the full assembled text and force a drop on failure.
- Three tours regenerated, copied, and read as prose.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-289.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
