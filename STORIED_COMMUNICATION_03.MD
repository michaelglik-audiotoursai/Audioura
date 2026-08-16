# STORIED COMMUNICATION — Volume 03

Opened 2026-08-14 at Michael's instruction. Volume 02 was maintained until
11:17 on 2026-08-14 and then dropped for six exchanges — his words: *"it seems
that you stopped maintaining STORIED_COMMUNICATION_02.MD for what ever reason.
I need this document to search for my own words later as this session may no
longer hold our communication."* He is right; it was dropped. Volume 02 stays
where it is and is not edited further.

**The rule, restated so the next session cannot lose it:** Michael's questions
go in VERBATIM, LEAD's conclusion goes in short, and the entry is appended
BEFORE the next task starts — not at the end of a session. Sessions are killed
by design (D252). Anything held only in context is gone.

Keep entries short. Evidence belongs in `DECISIONS.md`; this file is the thread.

---

## 2026-08-14

### 11:2x — the credit_line worksheet, and what stop 1's keyword turned out to be

❯ *"I would like to make one worked example of a story sentence that ties a
person to the object, please provide the tour file and open it in VS Code and
then at least 'credit_line' for me to work through the example."*

Built `story_worksheet.py` (offline, free, re-runnable). The three keywords:
stop 1 `book`, stop 2 `Sigmund Freud`, stop 3 `Pierre Reverdy`.

**Stop 1's story keyword is a common noun, and that is why the stop is SILENT.**
Every person it names is struck off for already occupying another slot — Miró is
the `artist`, Mourlot the `printed_by`, and Louis Broder, the publisher the whole
story is about, the `publisher`. Proven: drop `publisher` alone from the exclude
list and `_pick_credit_line` returns `Louis Broder`. Not fixed — design question.

### 11:5x — Notes 1 and 2, and the phrase-as-credit_line experiment

❯ *Note 1: multiple stories about the same person are not prohibitive — but then
redundancy means same people at the same event or doing the same activity.
Note 2: the same test we use to judge whether a sentence has value applies to
picking a credit_line. In "The convergence of narrative and imagery in this
exhibit prompts reflection on how journeys from obscurity to enlightenment could
be depicted in unexpected ways elsewhere", Part 3 is the most general ("the book"
of the sentence); Part 1 is the most stop-specific and so the most interesting.
Make Part 1 the credit_line — note it is more than one word — and run it.*

Ran it. The phrase scored higher (67 vs 57) and produced the worse story. Both
arms wrote the SAME story from a byte-identical ladder and subject, because
`credit_line` only feeds RETRIEVAL. **The idea is right and was wired to the
wrong place — clause-specificity belongs at SUBJECT SELECTION.** Note 1 recorded
as D442. Details D442/D443.

### 12:1x — "I do not see this as a story at all"

❯ *"Please provide output of all 4 routines you wrote... It should start with the
matrix and end up with the text. The first one makes a query out of the matrix —
and I want to see that query. The next one calls AI with this query and gets back
the resulting story. Then we validate the story... Then if valid and has more
sentences than 5, we ask to summarize in 3 sentences."*

Built `michaels_chain.py` — HIS chain, not `story_pipeline`'s. Four defects
(D444, D445):

1. **The writer had already REJECTED all three stories and the pipeline reported
   STORY** — status was computed from grounding alone and discarded
   `story_writer`'s own verdict. Every score quoted that day was on rejected
   output.
2. Routine 4 summarised despite Routine 3 returning REJECTED — there is no
   valid/invalid branch in the chain.
3. `split_sentences` could not split after a quotation mark, so a 3-sentence
   summary counted as 2. Museum stops are full of quoted titles. Fixed.
4. **The query asks "what story CAN BE TOLD"** — a question about what is
   possible. GPT-4o answered it correctly and was never asked to tell a story.

### 12:2x — try the same query on Gemini before changing it

❯ *"it is a matter of speaking. before we change the query, can you get the query
results from Gemini on the very same question?"*

**He was right; finding 4 above is withdrawn.** `gemini-3-flash-preview`, same
query, told an actual story — July 1938, Maresfield Gardens, named people, a
Dalí quote. The phrasing was not the blocker, the model was.

The trade is not free: two runs of the same model disagreed on who took Dalí to
Freud (Stefan Zweig vs Leonard Woolf). Chasing that exposed a false CONFIRM in
`verify()` — it accepted "Leonard Woolf accompanied Dalí" against a sentence that
never mentions Woolf. Fixed. D446.

### 12:3x — "I have a feeling that it is our validator that is misbehaving"

**Confirmed, and it is the day's most consequential finding.** Of Gemini's 30
sentences it flagged 5, and **all five are true**. The 25 it passed include every
sentence that says nothing checkable. Mechanism: it asks whether a capitalised
token appears in the source, so a sentence with no new name and no new year
*cannot* fail. **The vaguer the sentence, the safer it is.**

It also cannot see invented places, numbers or reversals — "in Barcelona", "on
the surface of the moon", "using 47 copper plates" and "refused to illustrate"
all pass. `TRUE_TO_SOURCES` means "contains no unfamiliar name or year". D447.

### 12:5x — go through Gemini's first section one by one

Five claims CONFIRMED from sources: the 19 July 1938 meeting; Freud fleeing
Nazi-occupied Vienna; 20 Maresfield Gardens; Dalí sketching Freud; Dalí comparing
Freud's cranium to a snail. **The three sentences our validator rejected are all
among the true ones.** What is actually wrong is narrow: atmospheric invention in
the same voice as fact, and one unsourced gloss. D448.

### 13:1x — MICHAEL'S RULING: descriptions and stories are judged differently

❯ *"The judgement principles of the stop or exhibit are very different than from
the story. If we describe a stop by providing incorrect or irrelevant description
it annoys our listeners... We are doing it well and I want to keep it that way.
The judgement principles of the story do not have to be relevant or confirmed in
sources, as long as there is not falsehood or contradictions in sources: we
absolutely should not publish a story with wrong facts. But 'Sigmund Freud... who
has just fled Nazi-occupied Vienna' makes Sigmund Freud a human, alive, shows his
state of mind, engages emotions in our listeners... 'it never reaches the object'
— that is a weakness of this story, but to me it is not prohibitive in case if
connecting phrase 'Dali and Freud met only once in London in July 1938' then the
listener knows that the story is about connection of the author and illustrator
of the exhibit. However, my judgement is that this weakness is not prohibitive
and if we do not find a better story, this story is better than none."*

Binding, recorded as **D450**. Description gate = accurate AND relevant. Story
gate = **must-not-be-contradicted**; unconfirmed is allowed, contradicted is not.
"Stakes=0" was a description-shaped ruler applied to a story.

**The actionable half:** to enforce "no falsehood", ask the OPEN question, not
the yes/no question. "Who accompanied Dalí to meet Freud" refuted the Woolf claim
with four sources naming Stefan Zweig and Edward James; every yes/no search had
failed to settle it.

### 13:3x — rebuild the validator, and give me the three scores

❯ *"If we identified the problems in current validator routines we need to change
the validator routines so that it passes through this story **1, correctly
pinpoints errors / hallucinations on the stories we know are not true — this way
we know that the validator is working better instead of not working at all. We
also need to obtain 3 values for this story... History, details, social: all
three independent from 0-100."*

Built `story_validator.py` — the D450 gate. See ANSWERS.MD Q-2026-08-14-3 for
the result, including the one control it still fails.

**Three scores for Gemini section 1: historic 31, detail 0, social 50.**

### 21:3x — three questions about the new gate

❯ *"1. Are all Gemini stories pass our validator? Could it be that some of Gemini
stories actually have incorrect facts in them? 2. Why does the validator wrongly
reject a true obscure claim (and what claim?) about Boris Friedman. 3. How can we
decide how much false rejection is acceptable?"*

**1.** No. The full 30-sentence story is REJECTED — but the number that matters is
that only **5 of 30 sentences were checked at all**. Both contradictions are
spurious: unstripped markdown made the wrong word the actor, giving the queries
"who printed Salvador Dali" and "who founded Salvador Dali". The one real claim in
that sentence — the Woolfs founding The Hogarth Press, which is true — was never
tested. **And yes, Gemini does produce false facts:** the Leonard Woolf claim is
refuted by four sources naming Stefan Zweig and Edward James.

**2.** Not a threshold problem. `named_people` counts "Le Lezard" and "Fine Arts"
as PEOPLE, the query is built from them and becomes *"who gave Le Lezard Fine Arts
2021"*, which cannot find Boris Fridman — so results drift to Alexander Calder's
*Lizard*, Fridman is absent, and absence is read as refutation. The gate asked a
broken question and then believed the silence.

**3.** Don't set a tolerance — the errors are asymmetric. A false acceptance is
**silent** (an untrue sentence in a visitor's ears, never reported); a false
rejection is **loud and recoverable** (we see it, and under D450 we can ship the
story flagged). Make "no usable evidence" a first-class verdict so a contradiction
is only pronounced when the search demonstrably landed on target. Then require
**100% on a labelled FALSE set** before shipping and drive false rejections down by
fixing the question, never by lowering the bar. Track **false-rejection rate at
zero false-acceptance** — today 1 in 3, and D453 shows the cause is a broken query.

Full evidence: D452, D453, D454.

### 21:5x — MICHAEL'S RULING on false rejection: prefer it, and rescue in a second tier

❯ *"it is better to accept false rejection — meaning reject the correct claim than
accept the incorrect one. We can create a logic of going from claim to claim and
getting the best story which is accepted. If no such story, then we need to use AI
and SERP and Gemini to verify rejections in case they are false to get the required
number of stories."*

Recorded as **D455**. Tier 1 strict and cheap: walk the claims, take the best
ACCEPTED story, doubt rejects. Tier 2 expensive and only on a shortfall: re-examine
the rejections with several models and searches to rescue the false ones.

**Implementing it exposed the real bottleneck.** The old gate silently allowed every
sentence it could not form a question about — 25 of 30 — which is the opposite of
this ruling. Now three-way: UNFALSIFIABLE (allowed), CHECKABLE, UNCHECKED_FACTUAL
(held). Measured:

```
full Gemini story   REJECTED_FALSEHOOD   coverage 0.13   3 of 23 checked
Gemini section 1    HELD_UNCHECKED       coverage 0.00   0 of 5  checked
```

**Section 1 — the story you like — now HOLDS**, because we cannot form an open
question for any of its five factual sentences: `fled`, `sketches`, `considers` and
a bare date are all outside the role-verb list. Not a reason to loosen the rule; it
names the priority. **The binding constraint is question formation, not the
threshold.** Coverage is the number to drive up. Evidence: D455.

## 2026-08-16

### — what are the tiers, and how do we measure

❯ *"What are the tiers 1, 2, + and how do we measure the results?"*

Written in full as `STORY_GATE_TIERS.md`; recorded as **D456**.

**Tier 0** description gate — accurate AND relevant, live, not to be touched.
**Tier 1** cheap, strict, always runs; open questions only; PASSES / HELD_UNCHECKED /
REJECTED_FALSEHOOD. Partially built, coverage 13%.
**Tier 2** expensive, only on a shortfall: re-form the question, re-retrieve, and
**adjudicate on citations only** — models find sources, they never rule on truth.
Not built.
**Tier 3 (+)** widen the subject → ship the weaker verifiable story → ship
description-only → human queue with sources. The human queue is the only path by
which an unverified claim ships.

**Measured at three levels.** Per story: coverage, verdict, Historic/Detail/Social,
object connection. Per gate against a labelled fixture: false acceptance on the FALSE
set (target 0, non-negotiable), false rejection on the TRUE set, stability over 3
runs. Per tour: tier-2 invocation rate, rescue yield, cost, stops with no story.

**Coverage is first because it bounds everything else** — a verdict over 13% of a
story's falsifiable sentences is a statement about 13% of the story.

**Build order:** the labelled fixture (~30 claims) first and unskippable; then
question formation; then markdown stripping and entity typing; then tiers 2 and 3.
