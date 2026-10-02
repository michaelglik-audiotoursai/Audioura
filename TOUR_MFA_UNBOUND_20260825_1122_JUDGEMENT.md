# My judgement on the tour of 2026-08-25, 11:22

Companion to **`TOUR_MFA_UNBOUND_20260825_1122.md`**. One generation, no selection.

Two tours were generated today and **both are reported here**, because they are two different
builds and the difference between them is the finding. The deliverable is the second — the run
under the code that is now on `storied`. I am not showing you the better of two attempts at the
same thing; that rule holds.

---

## 1. The headline

**A stop published two stories for the first time.** Stop 3 carries stories at index 77 and 70,
from two different seeds. Every previous run published exactly one per stop, and on 08-24 the
answer to "why only one" was *"the second candidate is the first one paraphrased."* It no longer
is.

**LOCAL-468 works, and its first tour was a regression.** Both are true, and the second is why
there is a D527.

| | baseline 08-24 | LOCAL-468 only | **LOCAL-468 + D527** |
|---|---|---|---|
| stop index mean | **75.7** | 60.7 | **73.7** |
| range | 73–81 | 45–80 | 60–83 |
| stops publishing 2 stories | 0 | 0 | **1** |
| max pairwise seed overlap | ~1.0 | 0.17–0.24 | 0.16–0.29 |
| known-defect checks | 9/9 clean | — | 9/9 clean |
| cost / wall | $0.178 / 550 s | $0.177 / 887 s | $0.162 / 819 s |

73.7 against 75.7, one run each, is not a difference I would defend. 60.7 was.

---

## 2. Acceptance criterion 4 failed, and the acceptance script could not have told me

You set it deliberately hard: diverse candidates **and** indices that do not collapse, because
*a diverse set of weak stories is not an improvement.* The first run is exactly that case —
overlap 0.08–0.24 on every stop, and the index mean down 15 points with the floor at 45.

The submitted script reports `INDICES: PASS — mean 52.2 >= 50`. That compares **candidate story
indices** against the **D515 floor**, while your 75.7 / 73–81 baseline is the **LOCAL-485 stop
index** — a different metric computed over different objects. Two numbers wearing the same word.
The script could not have tested criterion 4 whatever the tour did.

---

## 3. Why the first run collapsed

The composition, run 1:

| stop | seeds | stop index |
|---|---|---|
| Le Lézard | **4 matrix, 0 prose** | **80** |
| Au Soleil | 1 matrix, **3 prose** | **45** |
| Moses | 1 matrix, **3 prose** | **57** |

The mechanism does not rest on that correlation. `ask` means two different things, and LOCAL-468
read it as one. `_agent_seeds` writes *"What did Mourlot actually do, and what came of it?"* — a
retrieval question. `seeds_for_stop` writes:

> *What did {subj} actually DO that would justify "{phrase}"? If nothing, cut the phrase.*

That is an **audit** question. It asks whether our own prose survives scrutiny, and its final
clause is an instruction to a checklist — meaningless to a search model, and an open invitation
to return nothing. LOCAL-468 used `seed['ask']` for every seed kind because agent seeds were the
case in front of it.

**D527:** prose seeds revert to the story-seeking question they had before LOCAL-468, with the
phrase as credit anchor. Nothing else on the prose path changed. The agent-seed fix — the
measured win — is untouched.

**The prediction was differential, and it held where the change acts:**

| stop | seeds | run 1 | run 2 | Δ |
|---|---|---|---|---|
| Au Soleil | 3 prose | 45 | **83** | **+38** |
| Moses | 3 prose | 57 | **78** | **+21** |
| Le Lézard | mostly matrix | 80 | 60 | −20 |

The two prose-heavy stops gained enormously. The stop that fell is the one D527 barely touches —
its candidates came in at 41, 51, 10, 47 against 53, 74, 57, 5 the run before. That is variance
on the same code path, and it is why I will not quote 73.7 as an achievement.

**This is still n=1 per condition.** The differential is better evidence than the mean, but your
own note stands: three runs under one build is the first measurement that means anything.

---

## 4. A defect in the tour that the checks passed

Stop 3, on the Dalí *Moses and Monotheism* portfolio:

> **"The Louis Broder issued a limited run of two hundred and fifty numbered copies…"**

Louis Broder is **stop 1's** publisher. Stop 3's publisher is named two sentences earlier —
Éditions Art and Valeur. This is a false attribution carried across stops: the same family as
`"the Louis Broder Tériade"`, the longest-lived unfixed defect on the list.

Check (a) reports clean. I tested it both directions against this tour:

```
actual tour                     : []
same tour + "the Louis Broder Tériade" injected : ['the Louis Broder Tériade']
```

So the check is **not** broken — it fires on the shape it was written for. Its regex requires at
least two capitalised words before the tail name, so it sees a **three**-name fusion and is blind
to a **two**-name transplant. Written around one example, generalised only within that example's
shape. That is the eighth time this pattern has produced a false clean, and the lesson from D526
this morning is the same one: validate against a case whose answer you know, **in both
directions**, and against the population rather than the fixture.

I have not fixed it in this pass. It is a one-line widening, but widening a name check invites
false positives on legitimate phrases like "the Museum of Fine Arts", and that trade deserves its
own measurement rather than a same-day guess.

**Two other things in the text I would not ship, neither of them checked for:**

- Stop 1: *"gifted to the museum by Boris Fridman, the collector who gave this work to the
  museum"* — the same fact twice in one sentence. Check (e) targets literal repeated actions and
  does not see the paraphrase.
- Stop 3 opens with three sentences of pure filler before the first fact (*"has the potential to
  change how we understand the foundation of our beliefs"*). Stop 1 is the weakest at 60 and
  reads as catalogue prose.

Stop 2 is the best writing in any run so far — Rosenberg, the collapse, Gris dead at eleven
gouaches, Tériade reviving it thirty years later, 220 copies. That is a story, not a description.

---

## 5. What I did to LOCAL-468 before merging

Full record in D526 and `SUBMISSION_LOCAL-468.md`. Two defects, both repaired:

**Its prose-seed filter was a 40-character cutoff.** `_clean()` strips terminal punctuation, so a
seed *cannot* end in `.!?`, and `len(seed) >= 40 and seed[-1] not in '.!?'` reduces to
`len(seed) >= 40`. Over 33 real seeds: 0 truncated, 16 rejected, all 16 by the length half —
including `'Mourlot Frères, a renowned French lithographic printing company'`. **The premise was
false, and it was mine:** the "truncated fragments" I quoted in the task file were log lines
clipped for display. Removed.

**`compile_for_seed` had zero importers** while the call site carried an inline copy — the D511
orphan pattern recreated inside the fix for D511. Wired to its call site.

---

## 6. Where this leaves it

**Better:** seeds genuinely diverge (Mourlot's answer is about Mourlot; Fridman's is about a
Boston collector giving artists' books to the MFA — material no earlier run produced). A stop
publishes two stories. 9/9 defect checks clean. Cost down.

**Not yet:** the index floor is 60, not 73. The cross-stop attribution defect is live and
unwatched. Three of the four checks I leaned on today were, on inspection, fitted to their own
examples.

**Next, in order:** (1) three runs under this build — the first number that would mean anything;
(2) widen check (a) to two-name transplants and measure its false-positive rate on past tours;
(3) stop 1 is the weak stop in both runs and it is the one with the richest object record, which
is worth understanding on its own.

`storied` carries LOCAL-468 r2 + D527.
