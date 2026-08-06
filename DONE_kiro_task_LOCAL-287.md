**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-287
**Base:** storied
**Branch:** kiro/local287-gloss-composition

# The gloss gate splices raw sentences into the middle of other sentences.

Read `DECISIONS.md` **D194**, D177, `unglossed_reference_gate.py`,
`generate_tour_text.py` PHASE 5.157 (~line 7388),
`tours/LOCAL286_riviera_2stop_round34.txt`, and the **two BOUNCED sections at
the bottom of `new_kiro_session_is_required_LOCAL-280.md`** — they describe this
exact defect in a different feature, and the fix here is the same fix.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**LOCAL-286 is editing the spine prompt (~lines 7784–7870) in the same file.**
You are in PHASE 5.157 (~7388) and `unglossed_reference_gate.py`. Stay out of the
prolog composition; rebase rather than fight it.

## What shipped

LOCAL-269 is merged on `storied` (`91b02f4`). It fires — the log shows
`PHASE 5.157: Unglossed-reference gate` — and its output is unreadable. From a
tour generated for Michael tonight:

```
attracting luminaries like Jean-Paul Sartre, The influential French philosopher
and playwright known for existentialism., and Pablo Picasso

the village bustled with the presence of French actors Yves Montand, During the
1960s, the village was frequented by French actors Yves Montand, Simone
Signoret., Simone Signoret, and Lino Ventura

established in 1964 by Marguerite and Aimé Maeght, The Fondation Maeght was
established by Marguerite and Aimé Maeght in 1964 on the., stands as a beacon

designed by Spanish architect Josep Lluís Sert, The building was designed by
Spanish architect Josep Lluís Sert., is a masterpiece
```

Four faults, all from one cause:

1. **A whole sentence is inserted mid-sentence** — capital letter and full stop
   intact, producing `existentialism., and`. Every gloss does this.
2. **The gloss repeats the name it is glossing** — "Josep Lluís Sert, The
   building was designed by Spanish architect Josep Lluís Sert".
3. **The gloss repeats the host sentence** — the Montand gloss restates the
   clause it was inserted into, so the listener hears it twice in a row.
4. **Truncation** — "established by Marguerite and Aimé Maeght in 1964 **on
   the.**"

## The root cause, stated plainly

**The gloss is a span cut from source text and pasted after a name.** Cutting
produces the truncation; pasting produces the doubled name, the doubled sentence
and the stray capital and period.

This is **the same defect, in a second feature**. LOCAL-280's recap was bounced
twice for it (D194). The fix that task was given is the fix here:

> **Compose the clause. Do not concatenate source text.**

A gloss is a short appositive phrase that reads aloud as part of the host
sentence:

```
Jean-Paul Sartre, The influential French philosopher and playwright known for
existentialism., and Pablo Picasso
    ->  Jean-Paul Sartre, the existentialist philosopher, and Pablo Picasso

Josep Lluís Sert, The building was designed by Spanish architect Josep Lluís
Sert., is a masterpiece
    ->  Josep Lluís Sert, the Spanish architect, is a masterpiece
        (or drop the gloss — the host sentence already says "Spanish architect")

Marguerite and Aimé Maeght, The Fondation Maeght was established by ... on the.,
    ->  Marguerite and Aimé Maeght, the gallerists who founded it,
```

**An LLM call is appropriate and authorised**, as it was for LOCAL-280 — Michael
said so this morning about this feature specifically: *"not everything can be
algorithmic and free however preferrable, so if this rule does not work
efficiently enough we may use another call to AI."* Same constraint as always:
**it may only rephrase the supplied fact, never add one.** Batch all glosses in
a stop into a single call.

## Suppression is a valid outcome and is often the right one

If the host sentence already identifies the person — *"Spanish architect Josep
Lluís Sert"* — **the reference is not unglossed and the gate must not fire.**
Half the damage above is the gate glossing names that were already explained.
Check the host sentence before deciding anything is unexplained.

If no short clause can be composed from the sourced fact, **drop the name**
rather than emit a bad gloss. LOCAL-269's own title says "gloss, or lose the
name" — losing the name is the designed fallback and it is barely used.

## Mechanical guards — assert these on the final text

| must never appear |
|---|
| `., ` produced by an inserted gloss (capital-letter sentence spliced mid-sentence) |
| the glossed name appearing twice within 120 characters |
| a gloss ending in a preposition or article — `on the.`, `of the.`, `in.` |
| a gloss longer than ~12 words |
| a gloss whose text duplicates ≥6 consecutive words of its host sentence |

Add these as a post-gloss validation that **rejects the gloss and falls back**
rather than emitting it. A silent fallback is a good outcome; the current
behaviour is not.

## Then regenerate

A **2-stop** and an **8-stop** Riviera tour, every gate on. **Copy both to
`/Users/micha/Audioura/tours/`** — `tours/` is gitignored and worktree artifacts
do not survive the merge.

Report, for each: every gloss the gate produced, verbatim, with its host
sentence; how many were suppressed as already-explained; how many fell back to
dropping the name; the five guards above checked explicitly. Plus words,
generation time and cost against **$0.0257 / 54.5s** for 2 stops.

**Read the delivered tours as prose before reporting (D161).** The unit tests
passed on this feature and it still shipped unreadable — that is exactly why the
prose read is mandatory and not a formality.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria

- Glosses are composed clauses, never spliced sentences.
- No doubled name, no doubled host text, no truncation, no stray capital/period.
- Already-explained references are not glossed at all.
- Unglossable references lose the name instead of getting a bad gloss.
- The five mechanical guards assert on final text and force a fallback.
- Both tours regenerated, copied, and read as prose.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-287.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
