# LEAD's review — the tour we are both reading

**Tour file:** `TOUR_MFA_20260812_2030.txt` — repo root, same folder as this file, same
name stem. There is exactly one copy; nothing in `tours/`, nothing in a worktree.
**Generated:** 2026-08-12 20:36–20:39, in `audioura-tour-generator-1`, `code_sha 35cb1d4`,
cache disabled. 181.6s, $0.1191, 6,562 chars, 3 stops.

Reproduce:

```bash
docker exec -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 audioura-tour-generator-1 \
  python -c "
import sys; sys.path.insert(0,'/app')
from generate_tour_text import generate_tour_text
generate_tour_text('Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA',
                   'museum','/app/tours/MFA_TOUR_20260812_2030.txt',3)"
```

---

## First, your question: is the action plan done?

**No. Zero of the five.** I owe you a straight answer on this.

The five fixes I listed at 18:05 — publisher-appositive corruption, the Hogarth
conflation, orientation required on every stop, first-mention rule for people, per-stop
length balance — **none was dispatched.** Everything since went to the *footnote* of that
document instead: the non-determinism I flagged at the bottom became LOCAL-453 (bounced),
LOCAL-454 (partial), LOCAL-456 (parked), and in parallel the fleet-provenance chain
LOCAL-452/455 burned two 60-70 minute runs and produced nothing verified.

So the prose defects you are about to read are, with one exception, the same ones I wrote
down three hours ago. That is on me, and it is the clearest argument for what you asked
for next: a way to work on one thing at a time instead of dispatching around it.

---

## Your observation, checked against the run

You wrote: *"nothing points to the stop, but there are stories — the opposite of what it
used to be… no obvious correlation with the stop though they are about the stop."*

**The first half is measurably right and I can show you where it happens. The second half
is right too, and the instrumentation we have been trusting says the opposite.**

Counting sentences that tell you what you are physically looking at:

| Stop | Body sentences | Orientation tells you where to stand? | Body sentences about the physical object |
|---|---|---|---|
| 1 | 4 | yes — "Stand directly in front of…" | 1 — "publisher's vellum… luxurious sheen" |
| 2 | 9 | yes — "Stand before the display of…" | 0 |
| 3 | 9 | **no** | **0** |

Stop 3 never says where to stand or what the thing looks like. It opens with a definition.
That is the third consecutive generation with this exact hole, and it was defect #3 on the
undispatched list.

**Why the stories feel uncorrelated.** The story material is real and it *is* about the
stop — 8 named people, all correctly assigned:

```
[LOCAL-383] Stop 1 beats: Boris Fridman, Louis Broder, Mourlot Frères
[LOCAL-383] Stop 2 beats: Dalí, Freud, Torf
[LOCAL-383] Stop 3 beats: Juan Gris, Pierre Reverdy
```

I verified all 8 appear in the delivered text. But **not one of them is tied to the object
you are standing in front of.** Broder and Mourlot Frères appear as biography — "a renowned
figure in the world of artist's books" — not as *this copy, this vellum, these 40
lithographs*. The story and the stop are in the same paragraph and never touch. That is
exactly the gap you described, and it is a different problem from "no stories," which is
what we had a month ago.

---

## A measurement problem you should know about before we trust any number

Two instruments in this single run report opposite results:

```
[LOCAL-390] FINAL beat verification (measured from delivered text):
    stop='Le Lézard aux plumes d'or…'  beats_assigned=3 beats_in_output=3 dropped=[]
    stop='Moses and Monotheism'        beats_assigned=3 beats_in_output=3 dropped=[]
    stop='Au Soleil du Plafond'        beats_assigned=2 beats_in_output=2 dropped=[]

[LOCAL-410] CHAIN INSTRUMENTATION (post-generation)
    Le Lézard aux plumes d'or…: serp_results=55 snippets_injected=56 beats_in_delivered_text=0
    Moses and Monotheism:       serp_results=26 snippets_injected=26 beats_in_delivered_text=0
    Au Soleil du Plafond:       serp_results=29 snippets_injected=29 beats_in_delivered_text=0
```

I settled it by hand: **all 8 beat people are present in the text. LOCAL-390 is right and
LOCAL-410 reports a hard-coded-looking zero.** I nearly wrote you a paragraph claiming the
validation gates were eating the stories, on the strength of that 0. They are not.

We have been quoting `beats_in_delivered_text` as evidence. It is broken.

---

## What is genuinely good, and it is not nothing

- **Every fact is real.** Broder, Fridman, Mourlot Frères, Tériade, Gris, Reverdy, Freud,
  Dalí — all exist, all belong to these works. No fabrication anywhere in 6,562 characters.
- **Tériade is credited correctly this time.** Last run fused him with Broder into
  *"Tériade's role as the Louis Broder."* Gone. Stop 3 now says Tériade published *Au
  Soleil du Plafond*, which is true.
- **The gate refused to ship operator-directed text.** Stop 3 failed the positive gate
  three times and fell back rather than shipping prose that named no subject. It cost us
  quality but it did the honest thing.
- **`Mourlot Frères` was suppressed once for lack of evidence** and then reappeared where
  evidence existed. The evidence requirement is live, not decorative.
- **No invented sensory language.** None.

---

## Defects, in the order I would fix them

**1. Stop 3's body contains a sentence fragment with no subject** — blocking.

> "Rosenberg, but Gris's untimely death in 1927 left it incomplete."

It begins mid-sentence. This is the **third** consecutive generation with a garbled
sentence in this exact slot (previously *"Tériade's role as the Louis Broder"*, and before
that *"handpicked by Tériade, the Louis Broder"*). Three different corruptions, same
position, and this one came from the 3-attempt fallback path. A recurring failure in one
slot is a template defect.

**2. The Hogarth attribution is now worse** — blocking, fourth occurrence.

> "Commissioned by The Hogarth Press, this collaboration was published to merge Freud's
> profound theories with Dalí's vivid surrealism."

Hogarth published Freud's English *text* in 1939. It did not commission the 1974
Dalí-illustrated edition. Earlier runs said Hogarth "produced this edition"; this run
promotes it to commissioner. **This is the one defect I asked you to check last time and I
still have not verified it against the MFA's own page** — if the MFA says Hogarth, the
error is theirs and we are reporting faithfully. Worth settling before anyone writes code.

**3. Stop 3 has no orientation.** Same as last time. Cheap, and it is the difference
between an audio guide and an essay.

**4. Empty sentences — your D324 complaint, verbatim.** Three, and the tour ends on one:

> "The room may hold additional hidden details that offer insight into the artist's vision
> of enlightenment."
> "…prompts reflection on how journeys from obscurity to enlightenment could be depicted
> in unexpected ways elsewhere."
> "…note how it contributes to the exhibition's argument that such collaborative ventures
> are unprecedented."

The first says nothing at all. The second is about *elsewhere*. The third tells the
listener what to conclude and calls the ventures "unprecedented" with nothing behind it.
This is exactly the population LOCAL-416 was written to re-read under your standard — and
LOCAL-416 has been parked since before this chain started.

**5. An internal contradiction about where you are standing.** Stop 1 says **Gallery 184**;
stop 2 says **the Torf Gallery**. Both cannot be the frame unless they are the same room,
which nothing in the run establishes. A listener walking between them is being told two
different things.

**6. `"printed on the Louis Broder's vellum"`** — stop 1. The vellum is not Broder's; it is
publisher's vellum, and Broder was the publisher. Same appositive-fusion mechanism as
defect 1, milder.

**7. Missing space: `created in 1971.The choice`** — stop 1, and a TTS engine will read it
as one word.

**8. Prompt leakage in the closing.** The user-facing recap contains the literal word
`Closing:` — "…introduced monotheistic beliefs. Closing: The Treat Page shows…"

---

## What I built while you were out, and what it already found

`story_lab.py` — the subroutine-at-a-time harness you asked for. Six stages, your order:

```
S1  fact -> stop -> exhibition   assemble the stop record
S2  making the query             work_story_searcher.synthesize_queries
S3  result + evaluation          search_stories_for_stop, then snippet_ranker
S4  the right size               corpus_coverage, then targeted refinement
S5  writing                      the material handed to the story pass
S6  validation                   the gates
```

Each stage reads and writes one JSON state file, so you can run a stage, look at the
state, **edit it by hand, and run the next stage on your edit.** S2 is free and
deterministic, which makes it the cheapest place to experiment.

```bash
python3 story_lab.py stages
python3 story_lab.py s1 --tour TOUR_MFA_20260812_2030.txt --stop 1 \
    --artist "Joan Miró" --publisher "Louis Broder" --credit-line "Gift of Boris Fridman"
python3 story_lab.py s2
```

**It found something in its first run.** Six of the nine queries for stop 1 are exact-phrase
searches on a string that cannot exist anywhere on the internet:

```
1. "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)" Joan Miró story visitors …
3. "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)" Joan Miró
4. "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)" history
```

The English gloss in parentheses is **our own addition**. No source writes the title that
way, so the quotes guarantee those queries return nothing about the work. The production
log confirms it reaches the real search: `[work_stories] MISS for le lezard aux plumes dor
the lizard with`.

`generate_tour_text.py:4000` already has `_strip_parenthetical_translation()`, and it
returns exactly the right thing — `'Le Lézard aux plumes d'or'`. **It is simply not applied
to the stop record before the queries are built.** Stop 1 issued 9 queries and got 55
results; stops 2 and 3, whose titles carry no gloss, issued 4 each and got 26 and 29. Stop
1 is working harder for material about the wrong string.

**One honest limitation of the harness:** stage S5 cannot actually run the writer. The
story-writing prompt is inline inside `generate_tour_text()`, a 10,443-line function, so it
is not callable on its own. S5 shows the material that *feeds* the prompt. Extracting that
prompt into a real subroutine is the piece that would let us iterate on the writing the way
we can already iterate on the queries — and I think that is the single highest-value
refactor on the board for what you want to do.

---

## What I want you to check when you are back

1. **Is the Hogarth attribution actually ours or the MFA's?** One look at the museum's own
   page settles a defect that has now survived four generations.
2. **Gallery 184 or Torf Gallery?** If they are the same room, defect 5 evaporates.
3. **Does stop 1 read better to you than stop 3?** It is the shortest and has the fewest
   named people, and I think it is the best of the three — which would say something about
   how much material a stop actually needs.
4. **The correlation question is yours to define.** I can see that Broder is introduced as
   a biography rather than as the maker of the object in the case. Tell me what the right
   version of that sentence sounds like and I will make the gate enforce it.
