# LEAD evaluation — MFA storied tour (LOCAL-413 live run)

**Tour under review:** `~/audioura-worktrees/LOCAL-413/tours/local413_live_run.txt`
**Generated:** 2026-08-11 11:47, live search (16 queries, 102 results), N=4
**Evaluator:** Storied_Tours (LEAD) · written 2026-08-11 14:47
**Purpose:** so Michael and LEAD can compare verdicts stop by stop and find out
where we disagree.

---

## Headline

**The retrieval works. The writing does not.**

Two facts in this tour provably came from the web and survived into the prose —
`Cyrus Edwin Dallin` and `Rembrandt in 1629`. That had failed sixteen rounds
running, and it is the one thing worth celebrating here.

Everything else is weaker than it looks on first read. **Two of four stops carry
real information. One is written from the wrong sources entirely. One is padding
around a single fact.** And there are at least two outright fabrications that no
gate caught.

My overall verdict: **not shippable, and not close.** If I scored it against the
gate honestly I would put it well under 75.

---

## Stop 1 — Appeal to the Great Spirit · **the best stop**

**Right:** Names Cyrus Edwin Dallin in full. Bronze, monumental, in front of the
museum — all correct and all checkable. The full middle name came from search, not
from the model's memory; that is the retrieval chain working end to end.

**Wrong:**

- **Date conflict, unflagged.** The tour says "created … in 1909". The source
  snippet says a *1908* equestrian statue, installed at the Huntington Avenue
  entrance in *1912*. Three dates, and the tour asserts one without noting the
  others.
- **The orientation is not an orientation.** It is the entire tour introduction —
  four stop names, the Bartlett thread, the Homeric epics — crammed in before the
  listener has looked at anything. Standing in front of a bronze horse, they are
  being read a table of contents.
- **Circular sentence:** "symbolizing a spiritual connection to the Great Spirit."
  That says the thing is named what it is named.
- **`adds a timeless quality`** — your D324 complaint exactly. An adjective with no
  earning clause.
- **The interesting thing is missing.** The retrieved material mentions this
  sculpture's place in monument controversies. That is a real story about a real
  object in a real dispute — and the tour replaced it with "the period's
  fascination with Native American spirituality," which is a generalisation about
  an era, not a fact about this statue.

---

## Stop 2 — Ancient Nubia Now · **contains fabrications**

**Right:** The collection detail is genuine and specific — Kerma pottery, royal
statues of Napatan kings, imports from Greece and Rome, one of the largest such
collections outside Africa. This is the most *informative* paragraph in the tour.

**Wrong, and seriously:**

- **"Ruth's bequest and Rajput's collection"** — I can find no basis for either.
  "Rajput" is a North Indian community, not a donor to the MFA's Nubian holdings.
  This reads as garbled entity extraction presented as fact.
- **"The gallery … is named after the Guided Tour Asiatic"** — this is not a
  person. A pipeline label has been parsed as a human being and given a gallery.
  **This is the clearest fabrication in the tour and nothing flagged it.**
- **Broken grammar:** "the Museum of Fine Arts, one of the largest art museums in
  the U.S, Boston".
- **`intricate details`** — again, unexplained. Your exact objection.

---

## Stop 3 — Adam and Eve · **the worst stop, and the reason 414/415/417 exist**

**Wrong throughout:**

- **Written from creationist apologetics.** The sources ranked into this stop were
  `answersingenesis.org` and `biblicalarchaeology.org`. The output shows it: "the
  perfect beginning of humanity and the subsequent fall into sin", "the
  consequences of disobedience", "innocence and temptation".
- **It never names the artwork's artist.** A museum stop about a specific object,
  and we do not say who made it.
- **It name-drops the wrong artist instead** — Dürer's 1504 engraving is a
  *different work by a different artist*, offered as if it were context.
- **"Created in 1515" and "Pope Leo X's entrance into Florence in 1515"** are
  asserted flatly with no traceable source.
- **`inviting contemplation on human nature, morality, creation, and redemption`** —
  the banned phrase, in a prompt that explicitly bans it.

This stop is not a weak description of the object. **It is a short essay about the
Book of Genesis that happens to mention a museum.**

---

## Stop 4 — Artist in his Studio · **one fact, then filler**

**Right:** "by Rembrandt in 1629" — traceable to its snippet. Correct.

**Wrong:** After that single fact the stop has nothing and keeps talking. "prompting
viewers to consider the creative process", "a sacred space for artistic
expression", "sanctuaries where they could channel their creativity", "gain a deeper
appreciation for the artistry and craftsmanship". This is the longest stop in the
tour and the least informative — it is atmosphere generated to reach a word count.

Also: **"the Museum Boston"** — the venue's name is broken.

What is missing is what makes the painting worth standing in front of: it is a tiny
panel, the artist is dwarfed by his own easel, and he is looking at the back of a
canvas we cannot see. None of that is here.

---

## The closing

> "That's 4 stops — Adam and Eve, depicted in the Garden of Eden with symbolic
> animals and an artist's studio, considered a sanctuary for creativity during the
> 17th century."

Ungrammatical, and it summarises two stops while claiming to summarise four.

**The Bartlett thread is not real.** "The Influence of Francis Bartlett's Donations"
is announced in the introduction and stated again in the closing, and **Bartlett is
never mentioned in any of the four stops.** A thread that appears only in the
wrapper is a label, not a story. The Homeric epics line has the same problem — it
comes from an unrelated retrieved page and connects to nothing.

---

## Empty-adjective count (your D324 rule)

Across ~1,115 words: *captivating, renowned (×2), monumental, timeless, remarkable,
exquisite, magnificent, brilliant, poignant, beautifully, intricate (×2), grandeur,
vividly, comprehensive, enduring*.

**Roughly one unearned evaluative adjective every 60 words**, and almost none of
them are followed by what earns them. This is the same signature as D324's
measurement, not better.

---

## Where I expect we may disagree

I have graded this harshly. Two arguments against my own verdict, stated fairly:

1. **Stop 2 is genuinely informative** despite its fabrications. If the two invented
   donors were removed, it would be a decent stop. You may weigh the real content
   more heavily than I have.
2. **The retrieval milestone is real** and I may be underweighting it because the
   prose is disappointing. The machinery that gets a verified fact from the open web
   into the delivered text is now working, and that was the hard part.

**Where I would not move:** the "Guided Tour Asiatic" gallery and the Genesis essay
are not stylistic problems. They are the system stating false things confidently,
and no amount of prose polish addresses them.

---

## What is already dispatched against these findings

| Finding | Status |
|---|---|
| Stop 3 sourced from apologetics | tier gate — 414 (bounced), 415 (bounced), **417 in flight** |
| Model meta-text shipped as content | positive-assertion gate — **417 in flight** |
| Unearned adjectives | `PARKED_kiro_task_LOCAL-416` — re-read under your D324 rule |
| Fabricated donors / "Guided Tour Asiatic" | **not yet dispatched — new from this evaluation** |
| Fake narrative thread (Bartlett) | **not yet dispatched — new from this evaluation** |
| Orientation carrying the tour intro | **not yet dispatched — new from this evaluation** |

The bottom three are findings this evaluation produced that no task currently
covers. I will write them up once 417 lands, rather than dispatch concurrently into
the same file.
