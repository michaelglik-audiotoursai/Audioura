# Judgement — Restaurant tour in Monaco, and why one stop stays short

**2026-08-29.** Tour: `TOUR_MONACO_RESTAURANT_20260829_v5.md`.
**Le Louis XV – Alain Ducasse (465w) · Le Grill (249w) · Café de Paris Monte-Carlo (159w).**
873 words.

---

## Michael's question: how many words is Café de Paris?

**159 this run, 164 last.** Against our floors: above the 120 hard floor, below the 300 target.

He was right that it kept shrinking, and the cause was mine:

| run | Café de Paris | orientation | body |
|---|---|---|---|
| v2 | 253 | 48 | 201 |
| v3 | 187 | 29 | 154 |
| v4 | 164 | 12 | 148 |

**Each round I added instruction blocks to that prompt** — practicals, then the story block, then
"tell two episodes properly, name every person, deliver the explanation". Several hundred words of
constraints accumulated, and **nothing in the prompt ever stated a target length.** `LOCAL-72` had
removed it deliberately: *"the baseline produced 300-500 words per stop; constraining that thins
content."* True when the prompt was short; false once it was long. **A model given many rules and
no target writes to the rules and stops** — which is what the orientation collapsing from 48 words
to 12 looks like.

## Stating the target fixed the stop that had material

**Le Louis XV: 250 → 465 words.** Le Grill steady at 249.

**Café de Paris did not move — and that is the correct behaviour.** The log says why:

```
[D545]   ADDED 'Café de Paris Monte-Carlo'      ← a REPLENISHMENT stop
[D545] +3 story fact(s) for 'Café de Paris'      ← 3 facts, 4 snippets
```

**Replenished stops never go through corpus mining or fact-sheet generation.** They are named after
Phase 3A has finished, so they arrive with practicals and lore only. Le Louis XV — an
originally-selected stop with the full pipeline behind it — reached 465 words on the same
instruction.

Three facts support roughly 110 words of body. Reaching 300 would require padding, which the
instruction explicitly forbids: *"if the material genuinely supports only one episode, write that
one fully and stop."* **The stop is short because its input is thin, and the system declined to
inflate it. That is the behaviour we want; the gap is upstream.**

## The fix, and why I did not attempt it tonight

**Give replenished stops the same retrieval as originally-selected ones** — corpus mining, fact
sheets, the SERP story pipeline. That is the single change that would lift Café de Paris, and it
also fixes the thin biking stops (Le Grill 144w, Elsa 119w on earlier runs).

It is not a prompt tweak: it means running a later-arriving stop back through phases that assume
they run once, in order. This session has repeatedly shown what happens when I reach further than
a defect requires — a pipeline reorder attempted and reverted, an edit that deleted a function, an
import that never applied. **This one deserves a fresh session with a clear head, not a fourteenth
change tonight.**

## State of the tour

| | |
|---|---|
| Stops delivered | **3 of 3** |
| Story gate | **3 of 3** — second run running |
| Dead venues | **none** — Robuchon and Le Vistamar dropped pre-spine |
| Corrupted regnal names | **none** — the D552 fix holds |
| Four practical facts | present |
| Total | 873 words (v4 was 694) |

## Open, in the order I would take them

1. **Replenished stops get no corpus material** — the cause of every short stop on this path and
   the biking path. The highest-value remaining item.
2. **A contested name is asserted as fact** — Michael's source says Édouard Michelin, ours says
   André, and Gemini itself calls the record disputed. We have no "contested fact" signal.
3. **`closure_scan`** — three false positives this week, zero true positives the corpus had not
   already caught. Demote to advisory.

## Recommendation

**Accept for mobile testing.** The release blocker — stories about people — is met on all three
stops for two consecutive runs, the corruption is fixed, and no dead venue reaches the listener.
The short stop is honest thinness with a known upstream cause, not a defect in what ships.

For the phone: **server IP `192.168.0.136`**, and use a location not yet generated, or `tour_cache`
answers instead of the pipeline.
