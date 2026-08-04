# Evaluation score — recount proposal

**For Michael, 2026-08-04.** You asked to recount the score because new
requirements were added. This is the proposal plus a worked example on the
2-stop Riviera tour generated this morning (tour 163), so we are arguing about
real numbers rather than a schema.

---

## 1. What the score is today

**i-con** (your matrix, 2026-07-08), per paragraph:

| score | meaning |
|---|---|
| **1** | no information — what the visitor sees unaided; unanswered rhetorical questions |
| **3** | information, little emotional appeal — plaque-level facts; tag-claims without explanation |
| **5** | interesting information — grounded specifics that advance a thread |

Stop score = paragraph average. Tour score = stop average.
Gates (proposed, never confirmed): tour avg ≥ 3.5 · no stop < 3 · ≤1 one-scored
paragraph per stop.

Excluded from scoring: the tour prolog inside Stop 1, and `Directions:` lines.

---

## 2. What has been added since, and why i-con alone no longer covers it

Four requirements arrived after the matrix was written. **None of them is a
quality-of-information judgement, which is all i-con measures.**

| # | requirement | source | what i-con does with it today |
|---|---|---|---|
| A | No instructions, questions, or prescribed feelings | your test subject, `wdvrdaxaqj` | nothing — a well-informed paragraph that orders you around still scores 5 |
| B | Claims substantiated from corpus only | `wdvrdaxa7h`, D50 | nothing — an invented specific reads as a 5 |
| C | Every stop must have source material about *itself* | D78 | nothing |
| D | Stop 1's prolog is separate content | D64 | already excluded, correctly |

**A and B are the dangerous gaps.** i-con rewards specificity. Fabricated
specifics are maximally specific. The rubric as written scores a confident
invention higher than an honest generality — which is exactly backwards, and it
is why five rounds of "improvement" moved i-con without improving the tour.

---

## 3. Proposal: keep i-con, add two gates and one multiplier

I am not proposing to rescale i-con. Your matrix works and is calibrated
against 13 hand-scored paragraphs. The additions sit around it.

### 3a. Truth gate — REVISED twice since first written

**First version (superseded):** cap any paragraph with an unsupported claim at 1.

**Why that was wrong (D94).** You scored "depths reaching 320 feet" **5/5**;
`claim_check` marks it unsupported and is right to — we hold no passage saying
it. The rule would have scored your favourite sentence a 1.

**Why a naive fix is also wrong (D94).** Selecting better-sourced stops
*raised* the unsupported rate (0.576 vs 0.364), because a stop with no corpus
gets a restricted prompt, writes vaguely, and vague text has nothing to fail
on. A truth gate alone rewards saying nothing:

| i-con | unsupported | reading |
|---|---|---|
| high | low | what we want |
| high | high | confident invention |
| **low** | **low** | **vague filler that games the gate** |

**Current proposal — two axes, not one number.**

- **Quality** stays i-con, your matrix, unchanged.
- **Publishability** is separate: a sentence may be excellent *and* blocked.
- The truth gate applies **only to sentences that clear an i-con floor**.
  Below the floor the sentence is failing on quality already, and penalising
  it again for having nothing to source would reward vagueness.
- `CONTRADICTED` — the corpus says otherwise — is a hard block at any i-con.
  It is now measured at 0 of 188 corpus-wide with no false alarms (D99).

**What the instrument can and cannot do** (D99):

| | |
|---|---|
| false SUPPORTED (an invention passing) | **0** across all sets |
| false UNSUPPORTED (over-flagging) | ~17% original, 10% holdout |
| judging whether an unsourced claim is *true* | **cannot** — that is your 320 feet |

So at your chosen setting — **(b) score it down now** — roughly one true
sentence in six will be marked down unfairly. That is the price of never
letting an invention through, and it is the right trade while the corpus is
thin.

### 3b. Style gate (blocking, per paragraph)

Any paragraph with an **error-severity style violation** (R1 imperative, R2
question, R3 suggestive exploration, R4 prescribed feeling) is **capped at 3**.

Not capped at 1: the information may be genuinely good, and the fault is in the
delivery. But it cannot be "interesting information" while it is telling the
listener what to feel.

### 3c. Coverage multiplier (per stop)

| stop coverage | multiplier | rationale |
|---|---|---|
| COVERED | 1.0 | normal |
| CREATOR_ONLY | 0.7 | honest, but it is a biography, not a stop (D80) |
| VENUE_ONLY / EMPTY | 0.4 | the stop is filler |

This makes the corpus visible in the score. Today a venue with no material can
score identically to one with a rich corpus, because the model writes fluently
either way.

---

## 4. Worked example — tour 163, generated this morning

Both stops, all gates on, gpt-3.5-turbo (current default).

**Coverage going in:** Cap d'Antibes `COVERED` · Villefranche-sur-Mer `NO_CORPUS`.

| ¶ | stop | words | i-con (my read) | style | truth | after gates |
|---|---|---|---|---|---|---|
| 1 | Cap d'Antibes | 88 | 3 | **R1** | Villa Eilenroc "lavish parties of the 19th-century elite" — unsupported | **1** |
| 2 | *(prolog)* | 122 | — | R1 | — | excluded (D64) |
| 3 | Cap d'Antibes | 251 | **5** | clean | Monet 1888, Château de la Pinède, Maupassant, Tire-Poil 2.7 km — **all corpus-traceable** | **5** |
| 4 | Villefranche | 52 | 3 | **R1** | Rue Obscure 13th-century — unsupported | **1** |
| 5 | Villefranche | 143 | 3 | clean | "depths reaching 320 feet", "Free City on Sea" — unsupported | **1** |
| 6 | transition | 16 | 1 | clean | none | 1 |

**Scores**

| | old (i-con only) | proposed |
|---|---|---|
| Cap d'Antibes | (3+5)/2 = **4.0** | (1+5)/2 = 3.0 × 1.0 = **3.0** |
| Villefranche | (3+3+1)/3 = **2.3** | (1+1+1)/3 = 1.0 × 0.4 = **0.4** |
| **Tour** | **3.2** | **1.7** |

The old score says this tour is close to the 3.5 gate. The proposed score says
it is not close, and names why: **one paragraph out of six is doing real work.**

Paragraph 3 is genuinely good — Monet's 1888 visit, staying at the Château de
la Pinède on Maupassant's advice, the 2.7 km Tire-Poil trail. All of it traces
to corpus. That paragraph is the product working.

---

## 5. Three things the example exposes that no score captures

**The prompt is leaking into the narration.** Paragraph 3 contains:

> "One concrete sensory detail that envelops you in the atmosphere of Cap
> d'Antibes is the sound of the waves crashing against the rugged rocks…"

That is the model narrating its own instruction. No rule catches it today.

**Paragraph 3 is 251 words; paragraph 4 is 52.** A 5× swing between adjacent
stops. The listener experiences that as one stop mattering and the other not.

**The gate marked Villefranche SHORTENED and it still produced 143 words of
specifics** — "depths reaching 320 feet", "Free City on Sea", the 13th-century
Rue Obscure. The museum version of this gate worked (−76%, D80). The outdoor
version did not. Different code path; that is a bug, not a tuning problem.

---

## 6. What I need from you

0. **Does the two-axis split match your intent?** Quality score and
   publishability kept separate, and the truth gate applied only above an
   i-con floor — so that writing nothing cannot be the cheapest way to pass.
   This is the one that changes the shape of everything else.

1. **The two caps** (1 for unsupported, 3 for style) — right levels?
2. **The coverage multiplier** — 0.7 / 0.4, or should a VENUE_ONLY stop simply
   be disqualified from shipping at all?
3. **Whether the 3.5 gate still stands** against the recounted scale. Under the
   proposal, 3.5 is a much harder number. It may be right to keep it hard and
   accept that no current tour passes — that is honest — or to set the first
   milestone lower and move it.
4. **The 75-at-N=8 target** in `CLAUDE.md` is a different scale entirely
   (corpus-size-capped, with the cross-stop correlation bonus). Do you want the
   two reconciled into one number, or kept as separate gates? My lean: keep
   them separate. i-con measures the writing; the 75 target measures the
   corpus and structure. Collapsing them would hide which one is failing.
