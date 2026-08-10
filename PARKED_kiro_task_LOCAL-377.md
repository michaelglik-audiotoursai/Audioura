# LOCAL-377 (PARKED — do not dispatch until LOCAL-376 is merged)

**Park reason:** touches the same stop-prose path as LOCAL-376. Concurrent
workers on that path collide. LEAD renames this to
`new_kiro_session_is_required_LOCAL-377.md` once 376 lands.

---

# The "Unbound" tour never mentions that these are books

## The failure

`REVIEW_MFA_UNBOUND_2026-08-10.md`. The MFA show is called **"Unbound"** because
it is an exhibition of **livres d'artiste** — artists' books. The page says so in
its own opening paragraph:

> …others partnered with writers to devise images and words in harmony at the
> outset, as in Juan Gris and French poet Pierre Reverdy's *Au Soleil du Plafond*
> (1955). Rarely on view, and resisting easy categorization, these **livres
> d'artiste** invite visitors into a world of…

The delivered tour mentions books **zero times**. It describes two paintings and
a ceiling mural. A visitor is given no idea what kind of show they are standing
in.

## Why this is the D289 task, not a nice-to-have

Michael's ruling (D289): when there are too few objects, fill with **story, not
objects** — the exhibition's own theme, the form itself, provenance, the venue's
relationship to the work. He named this exact case: *"the bound-versus-unbound
dispute the show is named for"* and *"what a livre d'artiste is and why it
mattered."*

LOCAL-369 built Thread A and Thread B for precisely this and D289 promoted them
from enhancement to the **primary fallback for thin exhibitions**. On the live
run they contributed nothing. Find out why they did not engage, and make them.

## The task

- Establish why LOCAL-369's Thread A / Thread B produced no content on the live
  MFA run. Report the mechanism before changing it — do not rebuild them blind.
- A scoped exhibition tour must carry the show's **own subject**: what the
  exhibition is about, in its own terms, sourced from the page. For this show
  that is the livre d'artiste and the bound/unbound question in its title.
- Where a stop's object is a book, the prose should be able to say what that
  means — the collaboration between artist and writer, why these are rarely on
  view — **when the page supports it**. Never from parametric memory.

## Do NOT

- Do not invent works, and do not backfill from the permanent collection
  (D275/D284). This is story, not objects — that distinction is the whole ruling.
- Do not weaken grounding to make room for the story. Everything asserted must
  survive the page check, including LOCAL-376's person gate.

## Acceptance — live, per D284

- `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested.
  Delivered text must convey that these are artists' books and what the show is
  about, with every claim traceable to the page. Paste the full text.
- LOCAL-376's guarantees still hold: no `Rousseau`, no `Corbusier`, correct
  artists present, no "look up at" a book.
- Unscoped `Palais Lascaris` 4/4 unchanged; museum bounds 81.2 (n=4) / 75.0 (n=8),
  scored with the correct `n`.

## Tests

Expected red-on-revert count stated and both runs pasted (D294); the revert
breaks the **logic, not the symbol** (D296). No mirrors, no `inspect.getsource`
(D277).

## PROCESS
- Branch `kiro/local377-exhibition-own-subject` off `storied` **after 376 merges**.
- Write `SUBMISSION_LOCAL-377.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
