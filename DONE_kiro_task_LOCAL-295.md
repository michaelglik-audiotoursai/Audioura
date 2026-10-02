**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-295
**Base:** storied
**Branch:** kiro/local295-placeholder-leak

# "Placeholder leak" is discarding short descriptions that are not placeholders.

Read `SUBMISSION_LOCAL-292.md`, `generate_tour_text.py` —
`_detect_placeholder_leak()` at ~line 6387 and the `[LOCAL-26]` retry around it.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.50**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## What LOCAL-292 uncovered

LOCAL-292 stopped empty stops being shipped. Its verification then showed **why**
stops were empty, and it was not what anyone assumed:

```
- HTTP-level retry (LOCAL-292) did not fire — no 5xx/timeout errors during this run
- Content-level retry (LOCAL-26) fired on 2 stops with placeholder leaks:
  [LOCAL-26] Stop 2: placeholder leak detected (attempt 1), retrying...
  [LOCAL-26] Stop 2: placeholder leak detected (attempt 2), retrying...
  [LOCAL-26] Stop 2: placeholder leak persists after 3 attempts, using fallback
```

**No network faults at all.** Every lost stop was a "placeholder leak". Across
their seven tours, 8 of 26 requested stops were not delivered.

## The hypothesis — verify it before fixing anything

`_detect_placeholder_leak()` returns True on four conditions. Three are sound:
empty text, a bracketed `[... word ... description ...]` echo, and output wholly
enclosed in brackets. **The fourth is not:**

```python
# Output far below the minimum useful length (< 30 words when we asked for 120+)
word_count = len(stripped.split())
if word_count < 30:
    return True
```

A short description is not a placeholder. It is a short description. LEAD's
hypothesis, which **you must confirm or refute with logged evidence before
changing anything**:

> A stop with thin or no corpus produces a legitimately short description →
> under 30 words → misclassified as a placeholder leak → retried three times,
> each retry equally short → discarded → the stop is dropped.

This fits LOCAL-291's measurement that ~32% of fact-claims are ungrounded, and
it fits stops with `passage_count=0` disappearing while well-sourced ones survive.

**It may be wrong.** The short outputs may genuinely be malformed. Log the actual
rejected text for every leak detection and report it verbatim — that single piece
of evidence decides the whole task.

## Scope, conditional on what you find

**If the rejected text is real prose that is merely short:** separate the two
conditions. A true placeholder echo should still be rejected and retried. A short
but well-formed description should be **kept**, and the shortfall reported as
what it is — thin corpus — not disguised as a generation failure.

**If the rejected text is genuinely malformed:** the detector is right and the
problem is upstream in the prompt or the fact sheet. Say so plainly, fix that
instead, and do not weaken the detector.

Either way: **the retry must not repeat an identical request three times.** If
attempt 1 produced 22 words, attempts 2 and 3 with the same prompt will too.
Either vary the request or fail fast.

## The line you must not cross

**Do not pad a short description to clear a word count.** Length is not the
goal; a short accurate stop beats a padded one, and padding is the fabrication
this whole programme exists to prevent (D161, LOCAL-263).

**Do not simply lower the 30-word threshold to 10.** That trades one arbitrary
number for another. The fix is to distinguish *placeholder* from *short*, which
are different things.

**Do not regress LOCAL-292.** A stop with genuinely no narration must still be
removed rather than shipped as a shell.

## Verification

Run **five 2-stop** and **two 8-stop** Riviera tours. Report:

- every placeholder-leak rejection with the **verbatim rejected text** and its
  word count;
- how many were true placeholder echoes vs short-but-valid prose;
- stops requested / delivered, against LOCAL-292's measured 1/2, 2/2, 2/2, 0/2,
  1/2, 7/8, 5/8;
- the empty-stop count, which must stay at zero.

Copy all tours to `/Users/micha/Audioura/tours/` and read them as prose (D161).

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- **D186:** the spine stays on gpt-4o.
- `tests/test_local115_referral_abuse_controls_guard.py` calls `sys.exit()` at
  module scope and aborts any `pytest tests/` run that collects it. Pre-existing
  — run your suites by filename.

## Acceptance criteria

- Rejected text logged verbatim for every leak detection.
- Placeholder echoes and short-but-valid prose are distinguished, with evidence.
- Retry does not repeat an identical failing request three times.
- No padding; no blanket threshold lowering.
- Empty-stop count stays at zero; delivery rate reported against LOCAL-292's.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-295.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
