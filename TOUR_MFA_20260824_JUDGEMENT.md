# My judgement on the tour of 2026-08-24, 10:36

Companion to **`TOUR_MFA_20260824.md`**, which is the tour verbatim. Written after reading it
line by line, not from the scores.

---

## 0. Read this first: I generated two tours today, and I am handing you the second

You asked for **one** tour, not three-and-pick-the-best. I want to be exact about what
happened, because on the face of it two generations look like the thing you told me not to do.

I generated one (10:26). Reading it, I found that **my own fix had introduced a new defect, in
all three stops of three.** I fixed that, regenerated once, and this document is about the
second tour. **The second tour is not the better of the two on the story index — it is worse,
63.7 against 75.7.** I am handing it to you anyway, because it is the one produced by the code
that is now in the repository. Picking the 10:26 tour because it scored higher is exactly the
selection you ruled out.

Both runs are on disk: `TOUR_LOOP_20260824_1026.txt` and `TOUR_LOOP_20260824_1036.txt`.

---

## 1. What you asked for, and what it does

### (1) The append — the story now REPLACES the prose it overlaps

Your instruction, and the sentence in it that decided the design: *"saying things twice is the
worst for listeners — they hear that and get annoyed. **Moreover, selecting the story topic
based on the sentences made this problem** so we need to fix it."*

That second clause is a diagnosis, not a complaint, and it is right. The loop's credit_lines are
mined from the stop's own prose (`story_seeds.seeds_for_stop(stop_text, …)`), so the loop is
*guaranteed* to research whatever the prose already said and then say it again, better. No
amount of tuning the writer could have fixed that; the duplication is structural.

So the fix is subtraction, and it is ours, local, and needs no network. For each prose sentence
I ask whether the story already carries it, judged on shared **anchors** — proper names, years,
quantities — with the work's own title excluded from the comparison on both sides. A sentence
goes when it shares at least two anchors and half its anchors with the story, or when 60% of its
content words are already there. At most 60% of a stop can ever be removed.

**In this tour it removed 6 prose sentences across 3 stops.** Two examples, verbatim from the
run log:

| stop | dropped | evidence |
|---|---|---|
| 1 | *"In 1956, Louis Broder, the publisher of this edition, began a collaboration with Joan Miró…"* | anchors 0.56 (`1971, broder, joan, louis, miro`), content 0.50 |
| 2 | *"In 1927, the Spanish artist Juan Gris completed his work on 'Au Soleil du Plafond,' but…"* | anchors 0.75 (`1927, gris, juan`), content 0.56 |

### (2) The closing — the Treat Page must be earned

Your instruction: **only mention the Treat Page if it is genuinely near a stop of the tour, any
tour type, and it must not be the obligatory closing of every tour.**

It now requires a real treat within 1 km of a real stop — **any** stop, not just the last, since
a listener stands at all of them — and it fails closed on a missing table, missing coordinates
or a query error. Silence costs nothing; an unbacked promise does.

**On this machine's database there are zero treats with coordinates, so the sentence is gone.**
The log says so in as many words: `[D519] Treat Page: no treat within 1.0 km of any of 3 stop(s)
(0 treat(s) with coordinates) — mention OMITTED`. It closed **4 of the 4** previous runs
unconditionally. If a treat is ever loaded near the MFA, it comes back on its own.

---

## 2. The defect my own fix introduced, which is the useful finding of the day

The 10:26 tour had the duplication gone — and every one of its three stops opened like this:

> **"Broder** published this limited edition book…"      — who is Broder?
> **"The project,** originally conceived by L. Rosenberg…" — which project?
> **"Published by The Hogarth Press, Freud's theory** piqued Salvador Dalí's interest…" — which
> theory?

A stop's first prose sentence is the one that **introduces its subject**. That makes it also the
sentence most likely to duplicate a story mined from it — so it is the sentence most likely to
be dropped, and dropping it takes the introduction with it. I had written a repair for this, but
it only caught bare pronouns (*"This marked…"*), and none of these three are pronouns.

**The fix is to move the story to the front when it replaced the opening**, and it repairs all
three without deleting a word — because the story always introduces its own subjects in full:

> "In 1967, Joan Miró and **publisher Louis Broder** produced a suite of lithographs…" — and now
> "**Broder's** decision to publish this collection…" has its antecedent.

It is also the truer reading of your instruction. Replacement should happen *where the prose
was*, not always at the end. All three stops of this tour now open on the story.

**Why I am telling you this at length:** the fixtures I wrote from the 08-23 tour all passed
before the first run, and they were passing while the code was producing three broken stops.
The defect was only visible in a live tour. That is the live-artifact gate earning its keep.

---

## 3. The three defects you told me to watch and not fix

I built `check_known_defects.py` and validated it against the four tours whose answers we
already know, which **corrected the record**:

| defect | 08-23 base rate | this tour |
|---|---|---|
| (a) `"the Louis Broder Tériade"` — two publishers fused | **3 of 4 runs, not the 2 in D516** | **absent** |
| (b) priest/nobility self-contradiction in stop 3 | 1 of 4 | **absent** |
| (c) missing space after a full stop (`depth.Boris`) | **4 of 4 — it is not intermittent** | **absent** |

D516 recorded (a) as appearing in two runs. It is in three: the 18:16 run has it too, and nobody
looked, because the judgement was written about 18:21. My first version of the check reported the
17:46 run clean because it required the second name to appear somewhere else in the tour — and
there `Tériade` appears exactly once, inside the fusion. **A check that demands corroboration is
blind to the worst form of the thing it hunts.**

**Do not read the three "absent"s as three fixes.** With n=1 against base rates of 3/4, 1/4 and
4/4, only (c) is even suggestive — it had appeared in every previous run and did not appear
here, and I cannot explain why, since nothing I changed touches sentence spacing (the merge joins
with a single space and collapses whitespace, so it cannot produce or remove `works.This`). For
(a) and (b) the honest statement is: they did not occur, one run.

---

## 4. What is good in this tour

**Stop 1 opens on the story, and it is the strongest writing here.**

> In 1967, Joan Miró and publisher Louis Broder produced a suite of lithographs to accompany
> Miró's poem… Shortly after printing, Miró and Broder discovered a defect in the paper that
> distorted the ink colors. Because the original printing plates had already been erased, Miró
> could not simply reprint the images and had to create an entirely new set of plates, which
> Louis Broder published in 1971.

Something goes wrong, it cannot be undone, and a man does the work twice. That is the material
this month was spent learning to find, and it now opens the tour instead of arriving late.

**Stop 2 tells its disagreement instead of hiding it**, which is D509 working as designed:

> Sources differ on how much artwork he finished before his death: one account notes he produced
> only eleven pieces, while another states he completed half of the planned work.

And the prose that survives beside it earns its place — *"published by Éditions Verve and printed
by Mourlot Frères"* is not in the story, so it was kept.

---

## 5. What I would not ship

### (a) Stop 3 is thin, and the index says so — 44, the weakest stop measured today

Its story was accepted at **index 52 with `C1 X3`** — one confirmed claim, three unattested —
and the old gate would have rejected it on three counts (`eventful, index, confirmed`). What it
says is that Freud published in 1939, that Dalí illustrated a deluxe French edition, and that he
signed it in 1975. The 10:26 run had the diamond stylus, the gold plates, the lambskin and the
Michelangelo relief cover, with the sources disagreeing about the metal. **This run lost all of
it.** That is retrieval variance, not the merge — but it is the same Moses stop that has been
the weak one in every measurement since D513.

### (b) Two of three stops carry no inline sources

Stop 3 cites `dokumen.pub, baumanrarebooks.com, jstor.org`. Stops 1 and 2 cite nothing. In the
10:26 run all three did. I do not know why and I have not chased it.

### (c) A sentence that says the same thing twice inside itself, stop 1

> **Boris Fridman, the collector who gave this work to the museum**, later **donated this
> important work to the Museum of Fine Arts, Boston**…

The merge works between sentences, not inside one, so it cannot see this. It is the same disease
in a smaller space.

### (d) Filler, stop 3

Three consecutive sentences say the exhibition's thesis in three different ways — *"expanded the
dialogue between psychoanalysis and art"*, *"exemplifies the exhibition's thesis"*, *"transform
the book into a visual and intellectual exploration"*. That is what fills the space where stop
3's missing material should be.

---

## 6. The numbers, and what they are worth

| | loop OFF (D513, 3 runs) | old gate (D513, 3) | D515 (D516, 3) | **10:26** | **10:36 — this tour** |
|---|---|---|---|---|---|
| stop index, mean | 58.0 | 63.2 | 67.8 | **75.7** | **63.7** |
| range | 49.7–62.3 | 61.7–64.0 | 64.3–72.3 | 69–82 | 44–77 |
| rubric base score | — | — | 66.7 / 75.0 / 75.0 | **75.0** | **75.0** |
| stops publishing a story | — | 4 of 9 | 9 of 9 | 3 of 3 | 3 of 3 |
| loop cost | — | $0.10–0.17 | $0.045–0.060 | $0.046 | $0.044 |
| characters | — | — | — | 7,354 | 5,873 |

**I am not going to claim the append fix moved the score, in either direction.** Two single runs
that differ by 12 index points, against a measured single-run sd of ~5–7, is noise; the rubric
base score is identical at 75.0 and sits at the top of the 08-23 band. What the fix changes is
not measured by either number: **the tour no longer says things twice**, which was your
complaint, and no metric here was ever going to register that.

The number I would watch is **44 on stop 3**. D515's floor is doing what it was designed to do —
publishing something rather than nothing — and here "something" is thin. That is the amendment I
proposed in D515 and you have not ruled on: require at least one confirmed-or-corrected claim.
Stop 3 has exactly one. It would still have passed.

---

## 7. What I would do next, in order

1. **Three runs under D518/D519**, against the three D515 runs already recorded, before anyone
   treats 63.7 or 75.7 as meaning anything. ~$0.60, ~20 minutes.
2. **The intra-sentence duplication in §5(c)** — the merge is sentence-level by construction, and
   Boris Fridman gave the work away twice in one sentence.
3. **Why stops 1 and 2 lost their inline citations** (§5b), which is a transparency regression
   between two runs an hour apart.
4. **Your two D515 amendments**, now that stop 3 has published at `C1 X3` and scored 44 — this is
   the case amendment (a) was written for.
5. **Defect (c), the missing space** — absent today after 4 of 4, which I cannot explain and
   therefore do not trust.
