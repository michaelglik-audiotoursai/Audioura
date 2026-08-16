# The story gate: tiers, and how we measure them

Michael, 2026-08-16: *"What are the tiers 1, 2, + and how do we measure the results?"*

This is the specification. It follows D450 (descriptions and stories obey different
rules), D454 (refusing to answer is a first-class verdict) and D455 (prefer false
rejection; rescue in a second tier).

**Build state, stated up front so nothing here reads as done:**

| | state |
|---|---|
| Tier 0 | live, unchanged, working — do not touch |
| Tier 1 | partially built. **Coverage 13%** — the binding constraint |
| Tier 2 | not built |
| Tier 3 | not built; policy decided |
| Fixture | 6 labelled claims. Needs ~30 before any number below means anything |

---

## Tier 0 — the DESCRIPTION gate (separate rule set, already working)

Not part of the story pipeline, listed because it is the thing we must not break.

**Rule (D450):** the stop description must be **accurate AND relevant**. The listener
is looking at the object while we talk; a description they cannot match to what is in
front of them costs us their trust.

**Verdict:** accurate+relevant, or it does not ship. There is no "held" state here.

Michael: *"We are doing it well and I want to keep it that way."*

---

## Tier 1 — cheap, strict, always runs

**Purpose:** accept only what we have positively checked. Doubt rejects.

**Input:** candidate stories, and within each the sentences that assert something.

**Process:** classify every sentence, then for the checkable ones ask an OPEN question
("who accompanied Dalí to meet Freud") and look for a source naming a *different*
answer. Never a yes/no question — a yes/no search cannot tell a false claim from a
poorly-indexed true one (D450).

**Sentence classes:**

| class | meaning | disposition |
|---|---|---|
| `UNFALSIFIABLE` | weather, interior state, interpretation | **allowed** — this is what makes Freud a person rather than a label (D450) |
| `CHECKABLE` | a named party in a role we can turn into a question | checked |
| `UNCHECKED_FACTUAL` | falsifiable, and we could not form the question | **held** — never silently allowed (D455) |

**Story verdicts:**

| verdict | meaning | goes to |
|---|---|---|
| `PASSES` | nothing contradicted, nothing unchecked | ship |
| `HELD_UNCHECKED` | no contradiction found, but we could not check everything | tier 2 |
| `REJECTED_FALSEHOOD` | a source names a different answer | tier 2 (to confirm the rejection) |

**Cost:** ~2 searches per checkable sentence. Cheap because coverage is what bounds it.

---

## Tier 2 — expensive, runs ONLY on a shortfall

**Purpose:** rescue false rejections when tier 1 has not produced enough stories.
Michael: *"If no such story, then we need to use AI and SERP and Gemini to verify
rejections in case they are false to get the required number of stories."*

**Trigger:** tier 1 returned fewer accepted stories than the tour needs. Never runs
otherwise — that is the entire point of the split.

**Input:** the `HELD_UNCHECKED` and `REJECTED_FALSEHOOD` stories, best first.

**Process, in order of cost:**

1. **Re-form the question.** Most holds are ours, not the story's — we could not build
   an open question for "fled", "sketches" or a bare date. Try further shapes.
2. **Re-retrieve.** Several phrasings, several engines, the full work title rather than
   a truncated fragment (this alone is the cause of the Fridman false rejection, D453).
3. **Adjudicate on citations only.**

**The one hard rule in this tier.** Models are used to *generate questions and find
sources*, never to *rule on truth*. Gemini produced the Leonard Woolf claim; asking
Gemini whether Leonard Woolf was there converts the rescue tier into the fabrication
tier. A rescue is valid only when it produces a **source sentence a human could read**.

**Output:** `RESCUED` (checkable now, and not contradicted) or `REJECT_CONFIRMED`.

---

## Tier 3 (the "+") — what happens when tier 2 still comes up short

Policy, in order. Not built.

1. **Widen the subject.** Different person, different claim, same stop. Cheapest, and
   the ladder already exists.
2. **Ship the weaker verifiable story.** D450: a story beats none — but only a story
   that is not false. A weak true story outranks a strong unverified one, always.
3. **Ship the stop with description only.** SILENCE is an acceptable outcome. Tier 0
   still stands on its own.
4. **Human queue.** Held claims that look valuable go to Michael with their sources
   attached. This is the only path by which an unverified claim may ever ship, and it
   ships because a person decided, not because a gate was tired.

**Never:** lower the bar on the FALSE set to make the numbers work.

---

## How we measure

### A. Per story — is this one good?

| # | measure | how | now |
|---|---|---|---|
| 1 | **Coverage** | `CHECKABLE / (CHECKABLE + UNCHECKED_FACTUAL)` | **0.13** |
| 2 | Verdict | PASSES / HELD / REJECTED | — |
| 3 | **Historic / Detail / Social** | three independent 0–100 (D451), for matching a story to a listener's history | 31 / 0 / 50 |
| 4 | **Object connection** | does a sentence name a physical property of the thing in the case | **no** — the known weakness (D449) |

Coverage is first on purpose. **It bounds every other number:** a verdict computed over
13% of the falsifiable sentences is a statement about 13% of the story.

### B. Per gate — is the instrument any good?

Measured against a **labelled fixture** of claims known TRUE and known FALSE. This does
not exist yet at usable size and must be built before any figure below is quotable.

| # | measure | target |
|---|---|---|
| 5 | **False acceptance on the FALSE set** | **0. Non-negotiable.** A gate that misses a known hallucination is not a gate |
| 6 | **False rejection on the TRUE set** | driven down by improving the QUESTION, never by lowering 5 |
| 7 | Verdict stability | same claim, 3 runs, same verdict. Caught a 1-in-3 flake already |

### C. Per tour — is the system working?

| # | measure | reading |
|---|---|---|
| 8 | **Tier-2 invocation rate** | fraction of stops needing the expensive path. Near 100% means tier 1 is not working — **that is today's reading** |
| 9 | **Tier-2 rescue yield** | of those escalated, how many were false rejections. High = tier 1 too strict. Near zero = tier 1 correctly strict |
| 10 | Searches and cost per story | the escalation budget |
| 11 | Stops shipping with no story | the honest cost of strictness |

### The one number to watch

**False-rejection rate at zero false-acceptance** (5 and 6 together), with **coverage**
(1) as the thing that moves it. Today: 1 in 3 on six cases, and D453 showed the cause
was a malformed query rather than a mis-set threshold — so the work is in question
formation, not in tuning.

---

## What to build, in order

1. **The labelled fixture** (~30 claims, TRUE and FALSE). Nothing above is measurable
   without it, and it is the only item here that cannot be skipped.
2. **Question formation** — "X fled Y", "X is the only/first/Nth Z", "X said Q of Y",
   bare dated events. Drives coverage off 13%.
3. **Markdown stripping and entity typing** — both current false positives came from
   header text becoming the actor (D452), and the Fridman rejection from "Fine Arts"
   being read as a person (D453).
4. Tier 2.
5. Tier 3 policy wiring.
