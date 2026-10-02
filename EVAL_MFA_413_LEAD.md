# LEAD evaluation — MFA **Unbound exhibition** tour (corrected)

**Requested string:** `Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA`
**Stops requested:** 3
**Generated:** 2026-08-11 15:10, current merged `storied`, live search
**Tour file:** `~/Audioura/TOUR_MFA_UNBOUND_EVAL.txt`
**Runner (pins the case so it cannot drift again):** `run_mfa_unbound_eval.py`

---

## First: this document previously evaluated the wrong tour

The earlier version of this file graded
`Museum of Fine Arts, Boston, Massachusetts` at 4 stops — a **generic
whole-museum highlights tour**. That is not the evaluation case and never was.

**Every live run from LOCAL-413 onward used the wrong subject.** 413's agent wrote
its own runner with `gen_tour("Museum of Fine Arts, Boston, Massachusetts", …,
total_stops=4)`. 414, 415 and 417 inherited it. LEAD reviewed all of them, wrote a
detailed evaluation of one, and made merge and bounce decisions on all of them
without noticing the subject had changed.

That is the root of D355 and it is larger than D355 said: the agent did not only
pick a stop count LEAD left unspecified, **it changed what the tour was about.**

---

## The finding that matters: the exhibition tour has regressed badly

| | **10:15 today** (`TOUR_MFA_STORIED_CURRENT.txt`, pre-LOCAL-411) | **15:10 now** (current merged `storied`) |
|---|---|---|
| Stops delivered | **3** | **1** |
| Stop 1 | Le Lézard aux plumes d'or (The Lizard with Golden Feathers) | **"Wednesday, September 16–Wednesday"** |
| Stop 2 | Moses and Monotheism | — |
| Stop 3 | Au Soleil du Plafond | — |
| Words | ~950 | 341 |

**Three real works became one date range.** LOCAL-411 merged at 11:02; the good
version predates it by 47 minutes.

### The two defects, precisely

**1. The exhibition's date range is being used as an artwork title.**

> `Stop 1: Wednesday, September 16–Wednesday`

That is the show's running-dates string ("Wednesday, September 16 – Wednesday,
October 7") scraped from the exhibition page and promoted to a work.

**2. The other half of that date range became the artist.**

> `"Wednesday, September 16–Wednesday" **by October 7**, featured in the 2026
> exhibition…`

The pipeline is telling the listener a date made the artwork.

**3. Two of three stops are simply missing.** The tour asked for 3 and delivered 1.

---

## What still works

Worth stating, because it is the thread to pull:

- **The exhibition framing is correct and well-written.** "works by Spanish artists
  within the livre d'artiste (artist's book) genre", "the Lois B. and Michael K.
  Torf Gallery (Gallery 184)", "how images, words, and typography intersect" —
  that is the real show, described accurately.
- **Real collaborators survive:** "Juan Gris and Pierre Reverdy, a french poet
  associated with surrealism". Grounded, exhibition-specific, correct.

So retrieval and framing are working. **Stop *selection* is what broke.**

---

## Prose defects (your D324 rule), on 341 words

*extraordinary, captivating (×2), intricate, unique, seamless, immersive,
unexpected*.

Seven unearned evaluative adjectives in 341 words — **one every 49 words**, worse
than the 10:15 version. "the intricate details and unique perspectives of the
exhibit come to life" is your exact complaint: two claims, no evidence for either.

Also: `a french poet` (lowercase), and `beats_in_delivered_text=0` — the story
beats the pipeline extracted reached none of the delivered text.

---

## My verdict

**Worse than this morning, and not shippable.** The 10:15 version was a tour with
three real works and thin prose. This is one fake work, a date credited as its
maker, and two missing stops.

The chain merged today (410 → 413) was validated against a generic museum tour the
whole time. **Whatever it improved, it also broke stop selection on the real
case, and the wrong test subject is why nobody saw it.**

---

## What happens next

| Action | Status |
|---|---|
| Fix date-range-as-title and date-as-artist | **dispatching now — highest priority** |
| Restore 3-stop selection on the exhibition | same task |
| Pin the evaluation case in a committed runner | **done** — `run_mfa_unbound_eval.py` |
| 417 (in flight) — its acceptance is on the wrong tour | let it finish; re-validate against the correct case before any merge |
| Consider reverting 411–413 if the fix is not quick | open — the 10:15 behaviour is the better baseline |

**On the earlier findings in this file** (fabricated donors, "Guided Tour Asiatic",
the fake Bartlett thread): those were defects of the *generic museum tour*. They
may still be real bugs, but they are not evidence about the exhibition tour and I
am no longer counting them against it.
