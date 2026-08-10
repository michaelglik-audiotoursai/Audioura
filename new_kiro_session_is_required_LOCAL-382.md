# LOCAL-382 (PARKED — unpark when LOCAL-381 merges) — The exhibition has a thesis. Use it.

**Supersedes PARKED_kiro_task_LOCAL-377.md** (delete that file; this is the
stronger version of the same requirement).

**Park reason:** same stop-prose path as LOCAL-381, in flight. LEAD renames to
`new_kiro_session_is_required_LOCAL-382.md` when 381 lands.

---

## Michael's review, 2026-08-10 — the problem this fixes

> "We said nothing about the exhibit narration: why someone put the collection
> together, what entity it is showing… we are treating the works of Spanish
> painters completely outside of the exhibit intent… we are pointing listeners to
> 'the meticulous attention to detail in rendering the reptile's intricate
> plumage' completely forgetting about the main point: **these are a new art:
> illustrated books.**"

He compared our general description against what Google returns for "What is
Picasso, Miró, Dalí: Unbound all about?" and Google was better. That is the bar
we failed.

## The material is already on the page we fetch. We discard it.

`tests/fixtures/mfa_picasso_miro_dali_unbound.html`, the "About" section,
**verbatim** — this is in `page_text` today:

> "Bold, experimental, extravagant, and **unbound**, both literally and in the
> creative minds that produced them, **livres d'artiste had no precedent**. At the
> turn of the 20th century, they **revolutionized the book as an art form**.
> Livres d'artiste attracted many famous practitioners—Pablo Picasso, Joan Miró,
> and Salvador Dalí among them—but they were also **deeply collaborative
> ventures. Authors, publishers, designers, and printmakers played essential roles
> in bringing them to life.** This exhibition introduces the imaginative world of
> this form through a group of extraordinary works by Spanish artists. **Visitors
> can explore how images, words, and typography intersect, often in intricate ways
> that defy expectations.** Some artists interpreted foundational texts, as Dalí
> did in his 1974 illustrations for Sigmund Freud's *Moses and Monotheism*; others
> partnered with writers to devise images and words in harmony at the outset, as
> in Juan Gris and French poet Pierre Reverdy's *Au Soleil du Plafond* (1955).
> **Rarely on view**, and resisting easy categorization, these livres d'artiste
> invite visitors into a world of artistic ambition in which **creativity and the
> power of collaboration** led to some of the most singular and compelling
> achievements of publishing in the 20th century."
>
> "**Lois B. and Michael K. Torf Gallery (Gallery 184)**"

Everything Michael praised in Google's answer is in that paragraph, sourced,
citable, already retrieved. **This task is not about finding new material. It is
about not throwing away what we have.**

## Part A — the general description must carry the exhibition's premise

Today's opening says the three works exist and that the artists "draw inspiration
from diverse sources". Michael's assessment of the *structure* was positive —
introduction, works, forward reference, first stop — so **keep that shape**. What
is missing is the premise, which must appear before the works are listed:

- what a **livre d'artiste** is, and that these works **had no precedent** and
  **revolutionized the book as an art form**
- that this show is specifically **Spanish avant-garde masters** — Picasso, Miró,
  Dalí
- that the works are **deeply collaborative** — authors, publishers, designers,
  printmakers — which is why the show dismantles the solitary-genius picture
- that they are **rarely on view**, so this is an unusual chance
- the gallery: **Torf Gallery (Gallery 184)**

Every one of those is on the page. Nothing may be added that is not.

## Part B — every stop must be framed as the exhibition frames it

This is the deeper half. A stop currently describes *the picture inside the book*
as if it were a painting on a wall. The exhibition's whole claim is that the
**book is the artwork**: image, text, typography, paper, binding, as one thing.

For each stop, the prose must engage at least two of:

- the **collaboration** — who wrote it, who published it, who printed it. Stop 1's
  credit line names **Louis Broder** (publisher) and **Mourlot Frères** (printer);
  stop 2 is **Dalí illustrating Freud**; stop 3 is **Gris with the poet Reverdy**.
- the **form** — lithographs, vellum binding, wrapper, how many plates. Stop 1:
  "40 color lithographs… publisher's vellum".
- **how images, words and typography intersect** — the exhibition's own stated
  subject.

**Forbidden:** describing the depicted image as though the object were a painting,
with no reference to it being a book. That is the exact failure Michael named.

## Part C — WHEN this applies. Do not force a thesis onto a venue that has none.

**Michael's ruling, 2026-08-10.** The framing above is conditional, and getting
the condition wrong would damage ordinary museum tours:

> "When the tour is about an exhibition a curator created, then we must say about
> the exhibition and then find our stops' meaning in the exhibition's goals. That
> is not true when a listener asks us to generate a tour in a general art museum —
> **unless** we find the museum was created for a specific cause/reason, then this
> reason can become a similar theme as the curated exhibition."

So there are **three cases** and the code must distinguish them:

| Case | Framing thesis | Stops derive meaning from |
|---|---|---|
| **1. Curated exhibition** (scoped request, `_exhibition_checklist_result`) | the exhibition's curatorial premise, from its own page | the exhibition's goals |
| **2. Venue with a stated founding purpose or mission** — a single-artist museum, a collection assembled for a cause, a house museum with a bequest | that founding purpose | the venue's reason for existing |
| **3. General museum with no stated thesis** | **none — do not invent one** | the objects themselves, as today |

**Case 2 is common and must be detected, not assumed.** Palais Lascaris is a
Baroque palace holding a musical-instrument collection; Musée Matisse exists for
one artist. A venue page that states why the institution or collection exists —
a founder, a bequest, a mission, a dedication — supplies the same role the
exhibition premise plays in case 1.

**Detection rule:** the thesis must be a *stated* purpose found in the venue's own
page text, on the same grounding terms as everything else. Phrases like "founded
in… to…", "bequeathed", "dedicated to", "the collection was assembled to",
"mission". **If no such statement is found, case 3 applies and the tour proceeds
exactly as it does today.** Absence of a thesis is a valid outcome, not a failure
to search harder.

**Never synthesise a purpose from the venue's name, its collection's subject, or
parametric knowledge.** That is D300 one level up — inferring identity from a
name is precisely how "Plafond" became a ceiling.

Log which case fired: `[LOCAL-382] framing=exhibition|venue_purpose|none
source='<verbatim page phrase or ->'`.

## Do NOT

- Do not fetch Google, Wikipedia, or any new source for this task. The page has
  it. If a *later* task needs multi-source, that is LOCAL-23's lineage, not this.
- **Do not apply exhibition framing to a general museum tour.** A forced thesis is
  worse than none — it invents a curatorial intent nobody had.
- Do not invent works (D275/D289) or loosen grounding (D284, LOCAL-379's gate).
- Do not lose what rounds 376–381 won: no fabricated persons, correct artists
  named, correct medium, stop count honest, ≥120 words per stop.

## Acceptance — live, per D284, checked case-insensitively in python (D299)

`Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested. Paste
the full delivered text.

**The general description must contain, grounded:** `livre d'artiste` (or
`artist's book`), `collabor*`, and at least two of {`no precedent`,
`revolutionized`, `rarely on view`, `typography`, `Torf Gallery`}.

**Each stop must name at least two of:** its author/poet, its publisher, its
printer, its binding/plate count, or the image/word/typography relationship.

**Still zero (case-insensitive):** `ceiling`, `installation`, `mural`, `canopy`,
`vault`, `overhead`, `dome`, `sculpture`, `painting`, `glass`, `stand beneath`,
`look up`, `gaze up`, `Rousseau`, `Corbusier`, `Lalanne`, `Matisse`.

**Still present:** `Miró` stop 1; `Dalí` and `Freud` stop 2; `Gris` and `Reverdy`
stop 3; `book` in ≥2 stops; every stop ≥120 words; `That's N stops` == heading
count.

**Then the two control cases — these are acceptance, not afterthoughts:**

1. **`Palais Lascaris, Nice, France` at 4** → still 4/4 real instruments. Report
   which framing case fired and the verbatim page phrase that triggered it. If it
   is `venue_purpose`, the phrase must be quotable from the venue page; if it is
   `none`, the tour must read as it does today. **A fabricated curatorial premise
   here is an automatic bounce.**
2. **One general museum with no stated thesis** — pick a large encyclopedic venue
   and generate 4 stops. Expected `framing=none`, and the output must not contain
   invented language about why the museum exists or what it "sets out to show".

Bounds: `score_tour_file(f,4)`=**81.2**, `score_tour_file(f,8)`=**75.0**.

Env: `DISABLE_TOUR_CACHE=1`,
`DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
`STORIED_MODE=true`.

## Tests

State the expected red-on-revert count; revert must break the **logic, not the
symbol** (D296); confirm your patch applied before believing an all-green. No
mirrors, no `inspect.getsource` (D277).

## PROCESS
- Branch `kiro/local382-exhibition-thesis` off `storied`.
- Write `SUBMISSION_LOCAL-382.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
