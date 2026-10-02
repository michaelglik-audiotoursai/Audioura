# My judgement on the tour of 2026-08-23, 18:21

Companion to **`TOUR_MFA_FINAL_20260823.md`**, which is the tour verbatim. Written after
reading it line by line, not from the scores.

---

## 1. The measurement you asked for

Three tours under D515, run with the rule exactly as approved — **the two amendments I proposed
were deliberately not applied**, because changing the rule mid-measurement measures something
else.

| arm | runs | tour-mean index | sd | range |
|---|---|---|---|---|
| loop OFF | 3 | 58.0 | 7.19 | 49.7 – 62.3 |
| loop ON, old gate | 3 | 63.2 | 1.33 | 61.7 – 64.0 |
| **loop ON, D515** | **3** | **67.8** | 4.11 | 64.3 – 72.3 |

**D515 vs loop-off: +9.8** (Welch t = 2.04, df 3.2). **D515 vs the old gate: +4.5** (t = 1.82).
Adding the 17:46 run, which was the same configuration, gives n=4, mean **68.8**, +10.8 over
loop-off (t = 2.35).

**Still not significant at p<0.05, and I am not going to dress it up as if it were.** But it is
the first result here that is *directionally consistent across every cut*: every D515 run beats
every loop-off run except one, the worst D515 run (64.3) beats the loop-off mean by 6, and the
effect survives dropping any single run — which is exactly what the +5.2 in D513 did **not** do.

**The parts that are not statistics at all:**

| | old gate, 3 runs | D515, 3 runs |
|---|---|---|
| stops that published a story | 4 of 9 | **9 of 9** |
| loop cost per tour | $0.10 – $0.17 | **$0.045 – $0.060** |
| loop time per tour | 290 – 465 s | **98 – 149 s** |
| credit_lines bought per stop | 3.0 | **1.1** |

Nine of nine stops published, at a third of the cost. Six of those nine would have been rejected
by the old gate; three would have passed either way. **Moses published in all three runs**, and
in run 3 it scored 75 — the highest Moses has ever scored, against 54.3 loop-off and 42.7 under
the old gate.

**One useful sighting:** in run 1 the first Moses candidate scored 37 and was rejected on the
index floor, and the *second* passed at 59. The iteration still works when the first candidate is
genuinely weak — the rule is not a rubber stamp, it just stops early when it can.

---

## 2. What is actually good in this tour

**Stop 1 has a real story, and it is the one this whole month was spent finding.**

> In 1967, Joan Miró and publisher Louis Broder completed an initial edition… After printing, a
> defect came to light, but the original printing plates had already been erased. Because the
> first set of plates could no longer be used, Miró had to create an entirely new series from
> scratch.

Something goes wrong, it cannot be undone, and a man does four years of work twice. It carries
its sources inline. This is the material that was sitting in a Christie's `<div>` we were not
reading three days ago.

**Stop 3 tells its disagreements instead of hiding them — twice in four sentences.**

> Depending on the account, Dalí's illustrations were then printed onto lambskin, or across a
> combination of sheepskin and silk. The loose-leaf folios were paired with a sculptural
> bas-relief cover… described by some sources as silver-plated and by others as finished with a
> silver patina.

That is your D509 ruling working as designed: a disagreement is material, and it is told. It also
happens to be the most trustworthy-sounding writing in the document, which was your argument for
it.

**Stop 2 does the same on the one number that matters:** *"some recording that he produced eleven
finished lithographs and others stating he completed only half the intended set."*

---

## 3. What I would not ship, in severity order

### (a) "the Louis Broder Tériade" — stop 2, and it is reproducible

> Nearly three decades later, in 1955, **the Louis Broder Tériade** brought Gris's vision to life…

Louis Broder is **stop 1's** publisher. Tériade is the correct name, and the loop's own story four
sentences later gets it right: *"publisher Tériade revived the abandoned work."* So the tour
contradicts itself inside one stop, and the wrong version is the one a listener hears first.

**This is not a one-off.** The identical corruption appeared in the 17:46 run — in the *loop's*
sentence that time, in the *descriptive prose* this time. Two different generators produced the
same cross-stop name contamination, which points at shared context between stops rather than at
either writer. **This is the first thing I would fix**, and D515's veto is structurally blind to
it: nothing in the adjudication ever flagged it, because the error was introduced when the prose
was written, not carried in from a source.

### (b) The tour contradicts itself about Freud's own thesis, in one stop

Stop 3's descriptive prose: *"Moses was not a Hebrew but an Egyptian **priest**."*
Stop 3's story, six sentences later: *"Moses was of Egyptian **nobility** rather than Hebrew
origin."*

The story is right — Freud argued nobility, a follower of Akhenaten. The prose is wrong, and the
closing line repeats the prose's version: *"suggests Moses was an Egyptian priest, not Hebrew."*
**The append put a corrected fact next to the uncorrected one and kept both.**

### (c) The seam and the duplication, unchanged since this morning

Every stop still reads as two documents stapled together — descriptive prose that has finished
speaking, then the story. On stop 2 the prose already tells you Gris died in 1927 leaving the work
incomplete with eleven lithographs, and the story tells you again with better detail. D515 made
this *more* visible, not less: now that every stop carries a story, every stop repeats itself.
This is `description + ' ' + story` in `generate_tour_text.py:14209` and it has not been touched.

### (d) Smaller, still user-visible

- **`depth.Boris Fridman`** — missing space, stop 1. Third sighting of this class today.
- **A non-sequitur about the room, mid-story**, stop 2: *"The gallery, named after its patron,
  Torf, displays works rarely seen publicly, usually housed in archives."*
- **Unsourced biography**, stop 1: *"their friendship endured until Broder's death"* — and *"In
  1956… began a partnership"*, which no retrieved source in this run supports.

---

## 4. My judgement, plainly

**The rule is better than what it replaced and I would keep it.** It publishes nine stops of nine
instead of four, costs a third as much, scores ~10 points higher than loop-off across three runs,
and the single story it chose over the old gate's pick — the erased plates — is the best writing
in the tour. The `eventful` classifier it demotes had labelled that story **inert**; it had not
earned a veto.

**But this tour is not shippable, and the story loop is no longer the reason.** Every defect above
lives in the descriptive prose or in the join between prose and story — the part of the pipeline
none of this week's work touched. The loop is now the most reliable component in the stop, and it
is being let down by the paragraph it is glued to.

**What I would do next, in order:**

1. **Fix the append.** Have the story replace the overlapping prose rather than follow it. That
   one change fixes (b) — the priest/nobility contradiction — and (c) entirely, and it is ours,
   local, and needs no network.
2. **Find the Broder/Tériade contamination.** Two runs, two different generators, same wrong name.
   Shared per-tour context is the suspect.
3. **The two amendments to your rule** — require at least one confirmed-or-corrected claim, and
   treat `C0 X0` as a failed adjudication rather than a clean one. Note that `C0` did **not**
   recur in any of these three runs (counts ran C2–C5), so this is a rare case, not a common one.
4. **Then re-measure.** With the append fixed, the index will move for reasons that are about the
   writing rather than about duplication, and 67.8 becomes a number worth comparing against.

**On the gate itself I have changed my mind and should say so.** This morning I wrote that Moses
publishing nothing was the system telling the truth. On the evidence of these four runs that was
half right: the gate was honest, and it was also measuring the wrong thing — it rejected a story
about an edition destroyed by a paper defect as `inert` while passing a list of credits. Your rule
found that; the old thresholds hid it.
