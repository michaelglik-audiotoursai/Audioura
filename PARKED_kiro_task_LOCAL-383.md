# LOCAL-383 (PARKED — unpark when LOCAL-382 merges) — This is the Storied release and there are no stories

**Park reason:** same stop-prose path as 381/382. LEAD renames to
`new_kiro_session_is_required_LOCAL-383.md` when 382 lands.

---

## Michael's ruling, 2026-08-10

> "There are no stories. Listeners are not intrigued by the artists, diners,
> curators, MFA, nothing. **This is Storied release, and no stories demonstrate
> our failure.**… We are paying attention to the credibility of sources; and this
> is good, but **without stories, the tour does not worth much, and people will
> not pay for it.**"

This is the product bar, and it sits above everything rounds 376–382 have been
doing. Those rounds made the tour *true*. True and dull is still worthless. Both
properties are required, and grounding is not permitted to slip to get story —
the story must come from grounded material.

## What a story is here, and what it is not

**Not a story:** "This masterpiece challenges the boundaries between reality and
imagination." "The craftsmanship is a marvel to behold." These are the class-1
empty sentences LOCAL-375 measured at 61% of flagged hits. They are adjectives
about art in general, attached to nothing.

**A story** has a person who wanted something, a specific circumstance, and a
consequence. The page gives us people and circumstances. Use them.

## The material, all on the page we already fetch

From `tests/fixtures/mfa_picasso_miro_dali_unbound.html`:

| Source string on the page | The story in it |
|---|---|
| "published by **Louis Broder**, printed by **Mourlot Frères**, Paris, 1971" | A Paris lithography workshop and a publisher — the collaborators without whom the object does not exist. The exhibition's own thesis is that these people matter. |
| "**Gift of Boris Fridman**" | Someone collected these and gave them away. D283 tiering applies: name the donor and the gift; do not invent their motives. |
| "**Lois B. and Michael K. Torf Gallery** (Gallery 184)" | The room the listener is standing in is itself named for people. |
| "as **Dalí** did in his 1974 illustrations for **Sigmund Freud's** *Moses and Monotheism*" | A surrealist illustrating the founder of psychoanalysis on the origins of religion. That is a story on its face. |
| "**Juan Gris** and French poet **Pierre Reverdy's** *Au Soleil du Plafond* (1955)" | A painter and a poet devising images and words together "in harmony at the outset". |
| "**Rarely on view**… normally in the archives" | Why the listener is lucky to be standing there today. |
| "**had no precedent**… **revolutionized the book as an art form**" | The stakes: this was new, and it changed what a book could be. |
| Sponsors: Sharf Exhibition Fund, Poorvu Fund, Creighton, Rhodes, Cohn Fund, Jaffe Fund | Who paid for it to exist. Lower tier — use sparingly, per D283. |

**Every row above is a verbatim page string.** No new source is needed.

## The task

- Each stop must carry at least one **grounded story beat** — a named person and
  what they did, or a specific circumstance and its consequence — not a general
  claim about art.
- The tour as a whole must give the listener a reason to care about the
  *exhibition*, not only the objects: why anyone assembled this, why it is rare,
  what was at stake in inventing the form.
- Prefer the concrete over the evaluative. "Printed by Mourlot Frères in Paris,
  the workshop that pulled lithographs for half the School of Paris" is a story
  **only if the page supports the second clause** — if it does not, stop at what
  it does support. **Never trade grounding for colour.**
- Where the page genuinely supports nothing further for a stop, say less rather
  than padding. D289 forbids filling with invented objects; it also means a thin
  stop is a signal, not a licence to embellish.

## Hard constraint — everything rounds 376–382 won must survive

No fabricated persons. Correct artists named. Correct medium. Book framing. Stop
count honest. ≥120 words per stop. The gate in
`prose_entity_grounding_gate.py` stays and stays last.

**If a story beat cannot survive the person gate, it is not a story we may tell.**

## Acceptance — live, per D284, checked case-insensitively in python (D299)

`Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested. Paste
the full delivered text, plus:

- **Named collaborators/people present, grounded:** at least four distinct of
  {`Broder`, `Mourlot`, `Fridman`, `Freud`, `Reverdy`, `Torf`}
- Each stop contains at least one sentence naming a **person** and **what they
  did** — quote the sentence per stop in the submission
- All LOCAL-382 checks still pass (livre d'artiste framing, collaboration,
  per-stop book framing)
- All LOCAL-379/381 checks still pass (zero fabricated persons; zero `ceiling`,
  `installation`, `mural`, `sculpture`, `painting`, `glass`, `stand beneath`,
  `look up`, `gaze up`)
- `empty_sentence_count` per stop **reported** for before/after — this is the
  metric LOCAL-375 characterised, and a story-rich stop should reduce class-1
  empties. Report it; do **not** gate on it (D295: the heuristic still has ~22%
  false positives on visual description and must be narrowed before enforcing).

Then unscoped `Palais Lascaris, Nice, France` at 4 → 4/4 real instruments; bounds
`score_tour_file(f,4)`=**81.2**, `score_tour_file(f,8)`=**75.0**.

Env: `DISABLE_TOUR_CACHE=1`,
`DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
`STORIED_MODE=true`.

## Tests

Expected red-on-revert count stated; revert breaks the **logic, not the symbol**
(D296); confirm the patch applied. No mirrors, no `inspect.getsource` (D277).

## PROCESS
- Branch `kiro/local383-stories` off `storied`.
- Write `SUBMISSION_LOCAL-383.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
