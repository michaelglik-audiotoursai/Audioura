# My evaluation — 8-stop Musée des Arts Asiatiques

Tour: `tours/LOCAL303_museum_8stop_gate.txt` · 2,286 words · 8 of 8 stops · 6 Aug 2026

---

## Headline

**Two things you should know before the number.**

**1. Eight of eight stops delivered.** This venue has never produced a full 8
before. In July it was capped at 6 canonical titles, and as recently as last
night it was dropping stops. That constraint is gone.

**2. The score is 71.9, not the 96.9 the rubric prints — and it does not clear
your 75 gate.**

```
base              +71.9
structural         +0.0
correlation       +25.0   <- spurious, see below
venue identity     +0.0
                  ------
rubric total       96.9
defensible total   71.9
```

The +25.0 correlation bonus comes from two things, neither a narrative callback:

- **stop 7 → stop 4**: both stops are *about Kannon*, so both use the word
  "Kannon". Shared subject matter.
- **stop 8 → stops 1, 3, 4**: the **recap sentence itself** — one sentence naming
  several stops scores a callback for each. That is the recap you and I
  specified, inflating the metric used to judge it (D201).

I am not going to tell you a tour passed your gate on the strength of a term I
spent last night documenting as unsound. **71.9 is the honest figure.**

---

## But the honest figure is probably too low, and that is a defect in the index

Stop 3, *La danse cosmique de Ganesh*, is scored **THIN — 1 fact over 8
sentences**. Read what it actually contains:

> "In the 10th century, this remarkable piece crafted from **chlorite** captures
> Ganesh in a dynamic dance… **eight arms**, each holding a significant item. The
> **tambourine** symbolizes the primordial sound… the **rosary's** beads
> correspond to the Sanskrit alphabet… Ganesh's **axe** signifies physical
> strength… the **serpent's** tail and head… a bowl of **modakas**, round cakes
> symbolizing the germs of the Universe… Originating from the **Bengale** region,
> this sculpture is a testament to the artistry of the **Pala-Sena dynasty**…
> Ganesh, the son of **Shiva** and **Parvati**…"

A reader counts twelve or more concrete facts. The detector counts **one**.

Here is exactly what it saw:

```
dates:        ['10th century']
named_people: []
materials:    []
measurements: []
```

Four blind spots, all structural:

| missed | why |
|---|---|
| **chlorite** | the materials list is a hardcoded twelve-item vocabulary — schist, lacquer, bronze, cypress, silk, gold leaf, cedar… chlorite is simply not on it |
| **eight arms** | the measurement regex requires **digits** (`\d+\s*arms?`); a spelled-out number never matches |
| **Shiva, Parvati, Ganesh** | my person filter requires a verb of doing or a role noun within 90 characters. "embodies", "symbolizes", "originating" are not on that list — and deities are not "people" by any rule I wrote |
| **Pala-Sena dynasty, Bengale, Heian period** | dynasties, regions and named periods are not a category the detector has at all |

**This is the fact-detector version of the blocklist problem** I have been
bouncing agents for all week: a hardcoded vocabulary catches what it was written
against and misses everything else. I built the current one two nights ago and it
carries the same flaw.

So: **71.9 is a floor, not a measurement.** Several stops marked THIN are, on
reading, substantive. I would not act on the gate either way until the detector
counts what a listener would count.

---

## Per stop

| # | Stop | Band | Facts / sentences | My read |
|---|---|---|---|---|
| 1 | L'Armure d'Andô Naoyuki | RICH | 5 / 10 | Genuinely strong. Named armourer, dated, materials. |
| 2 | Statue de Bouddha | ADEQUATE | 2 / 9 | Greco-Buddhist fusion is real content; thinner than it reads. |
| 3 | La danse cosmique de Ganesh | THIN | 1 / 8 | **Misscored.** One of the best stops. See above. |
| 4 | Kannon, bodhisattva de la compassion | RICH | 7 / 8 | The best stop. 12th century, cypress, gold leaf, Heian period dated 794–1185, eleven heads explained. |
| 5 | Ulysses Grant au Japon | THIN | 1 / 8 | Genuinely thin — and this is the print whose catalogue entry we hold (artist, dates, inventory number 2015.6.A.1). We own the facts and did not use them. |
| 6 | Robe de prêtre taoïste | THIN | 2 / 12 | Twelve sentences for two facts. Padded. |
| 7 | Kannon à mille bras | ADEQUATE | 2 / 9 | Overlaps stop 4 heavily; the tour says "Kannon" a great deal. |
| 8 | Masque du vieillard kojô | ADEQUATE | 4 / 14 | Decent, but 14 sentences is long for four facts. |

---

## What is good, and it is a real change

- **The opening works.** No "walking journey" indoors, no "0 meters". It names
  the collection, counts the works, previews two specific stops, and ends on
  "Your first stop is L'Armure d'Andô Naoyuki." All four parts, in your order.
- **No gloss damage.** Zero spliced sentences, doubled names, or orphaned
  possessives — the wreckage you saw yesterday is gone.
- **The recap names real content**, not truncated spans.
- **R7 residual: 0** on this tour, and **groundedness 100%** on all eight stops —
  every fact traces to corpus.

## What is wrong

- **Stop 5 is the Grant print.** We hold its full catalogue entry — Toyohara
  Chikanobu, 1838–1912, medium, donor, inventory number — and the stop delivers
  one fact. This is the exact material I wrongly called fabricated in July (D162).
  The corpus is there; the generator is not using it.
- **Padding.** Stop 6 spends twelve sentences on two facts; stop 8 fourteen on
  four. Length is being produced where content is not.
- **"Kannon" twice.** Stops 4 and 7 are both Kannon figures and read repetitively.
  A selector that knew about subject overlap would spread the eight differently.
- **Five fragment sentences** flagged, and one visible artefact: *"This work,
  crafted in bois, Carved from cypress wood and adorned with…"* — an untranslated
  French word and a broken clause join.

---

## Outstanding work, as you asked

**One improvement task is still in flight, not merged:**

- **LOCAL-303** — R7 catches `azure waters` but not `azure sky`; the sensory
  filter matches fixed word pairs rather than the concept. Dispatched this
  morning, unmerged. It did not affect this tour (R7 residual 0), but it affects
  Riviera tours.

Everything else from last night is merged: gloss composition and degradation,
museum opening, closing recap, stop-existence verification, empty-stop removal,
corpus-depth selection, groundedness scoring.

**And the index defect above is not yet a task at all** — I found it while
scoring this tour. It should be, and it is more consequential than LOCAL-303,
because every quality judgement we make runs through that detector.

---

## My verdict

**A materially better tour than anything you have seen from this venue**, and the
first to deliver all eight stops. The structural faults you have been catching
one by one — the opening, the glosses, the recap, the empty stops — are fixed and
stayed fixed together.

**It does not clear 75 on defensible terms (71.9), and I would not trust 71.9
either.** The fact detector misses materials, spelled-out quantities, deities and
dynasties, so it under-reads at least one stop badly and probably several.

**What I would do before treating the gate as meaningful:** fix the fact
detector, then rescore this same tour. My expectation is that it lands in the
high 70s or low 80s on base alone — but that is a prediction, and I have been
wrong about five of those in the last twelve hours, so I would rather measure it
than argue it.
