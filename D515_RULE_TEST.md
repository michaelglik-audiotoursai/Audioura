# Michael's acceptance rule, tested on 41 stories and one live tour

**2026-08-23.** His rule, verbatim:

> *"If none of the stories on a step pass, but the index is more than 50 — accept with the
> highest index. If a story passes with index 50+, then this is the story and we do not need
> to verify more. The only reason for not accepting/fail should be positively identify as
> factual wrong events."*

Built as **D515**, on by default; `STORY_GATE_D515=0` restores the old gate exactly.

`eventful` and `confirmed ≥ 3` no longer decide admission — they are reported as
*preference* only. The index floor drops 60 → 50. Two hard vetoes remain: an **invented
person**, and a **positively identified factual error**, which I had to define narrowly or it
would have become the old gate under a new name:

| status | counts as wrong? | why |
|---|---|---|
| `UNATTESTED` | **no** | we found no source. D510 measured that most of these were our own truncation. |
| `DISPUTED` | **no** | sources disagree; the prompt asks for the disagreement to be *told*. |
| `CONFIRMED` | no | supported. |
| `CORRECTED` | **only if it survived** | the adjudicator contradicted the claim and PART 2 still asserts the version it corrected. |

That last line is the whole veto: *a fact we hold to be false, in text we are about to
publish.* Matching is by distinguishing tokens, so `1974 → 1975` is caught when 1974 survives
and 1975 is absent, and a harmless rewording is not flagged.

---

## 1. Replayed over 41 stories already on disk — free, before spending anything

`test_d515_replay.py`, over the 37 D510 lab stories and today's 4 production candidates.

| work | old gate | D515 | examined |
|---|---|---|---|
| Le Lézard aux plumes d'or | publishes 13.1 | accepts **2.1** at 60 | 1 of 16 |
| Au Soleil du Plafond | publishes 2.1 | accepts 2.1 at 62 | 1 of 12 |
| Moses and Monotheism (lab) | **nothing** | accepts 1.1 at 63 | 1 of 9 |
| Moses (today, production) | **nothing** | accepts A1 at 51 | 1 of 4 |

**Publishes 4 of 4 instead of 2 of 4, and buys 37 fewer candidates.**

**The fallback clause never fired — 0 of 4.** Accepting anything ≥ 50 is permissive enough
that the *first* candidate almost always qualifies, so "if none pass, take the highest" has
no case to handle. It is implemented and correct; it is close to dead code.

### The finding that matters: it takes the FIRST above 50, not the best

On Moses the rule accepts 1.1 at index 63 and never sees 7.1 at 71. **Order now decides the
outcome**, where the old gate's `eventful` key did some of that work.

**On Le Lézard this turned out in the rule's favour, and it is the strongest argument for it.**
D515 accepts credit_line 2.1, which the old gate rejected as `fail: eventful`:

> In 1967, Joan Miró and publisher Louis Broder produced the first edition. After publication,
> a defect came to light, but the original printing plates had already been erased. Because the
> initial prints could not simply be run again, Miró drew an entirely new series of plates.

A defect, erased plates, an edition abandoned, the work redone. `material_kind` called that
**inert**. Meanwhile the story the old gate did publish, 13.1, is *"collaborated with… printed
by… on display as a gift from Boris Fridman."* **The classifier had it exactly backwards, and
the index did not.** That is direct evidence for removing `eventful` as a blocker — not a
threshold argument, a misclassification argument.

---

## 2. The live tour, rule on — `TOUR_LOOP_20260823_1746.txt`

| | stories published | loop cost | loop time | tour-mean index |
|---|---|---|---|---|
| old gate, 3 runs (D513) | 1.3 of 3 | $0.10–0.17 | 290–465 s | 63.2 |
| **D515, 1 run** | **3 of 3** | **$0.046** | **98 s** | **71.7** |

Every stop accepted on its **first** credit_line. **72% cheaper, 3× faster, and the highest
tour mean measured to date** — the previous best was 64.0 and the loop-off mean was 58.0.
One run, so the D484 noise caveat applies to the 71.7 and not to the 3-of-3 or the cost.

Per stop: Le Lézard **84** (was 61.3 loop-off mean), Au Soleil **72**, Moses **59** (was 42.7
under the loop, 54.3 loop-off). **Moses publishes for the first time.**

Stop 1 now delivers the paper-defect story with citations — the D510 material, reaching a
tour on its first attempt instead of not at all.

---

## 3. Two things the rule lets through, and you should decide on both

### (a) Stop 3 published with **zero confirmed claims** — `C0 X0`

The log line is `kind=active idx=58 C0 X0 PASS [old gate: eventful,index,confirmed]`. The
adjudication produced **no parseable verdicts at all**, so nothing was confirmed, nothing was
contradicted, and the veto had nothing to bite on. What published:

> Decades later, Salvador Dalí illustrated the text by drawing directly onto massive gold
> plates with a diamond-tipped stylus. The resulting engravings were printed in color on
> lambskin.

That is probably true — it appeared in the lab run too. But **it went out with no evidence
attached**, and `confirmed ≥ 3` was the only check that had ever required *something* be
verified. Removing it as an admission key also removed the floor. Options, cheapest first:
require `CONFIRMED + CORRECTED ≥ 1` (not 3) as a second veto; or treat an unparseable
adjudication as a veto in itself, since C0 X0 usually means the parse failed rather than that
the model found nothing.

### (b) The veto cannot see an error the adjudicator did not make

Stop 2 published: *"Nearly thirty years after Gris's death, **the Louis Broder Tériade**
revived the stalled undertaking."* Louis Broder is **stop 1's** publisher. Tériade is the
right name. This is a corrupted, factually wrong sentence in the delivered tour, and D515's
veto is structurally blind to it: it only catches claims **the adjudicator itself corrected**.
An error introduced when PART 2 is written has never been adjudicated, so nothing flags it.

Not an argument against your rule — the old gate would not have caught it either. But
"positively identified as factually wrong" is only as strong as what we positively identify,
and right now that is one narrow class.

---

## 4. Also fixed, because the veto depends on it

`ungrounded_names` flagged **`Parisian`** (from *"the Parisian publisher Art & Valeur"*) — a
demonym read as a person, discarding a candidate before the gate was consulted. Under D515
that check became one of only two hard vetoes, so it had to be right first. A capitalised word
**followed** by a role word is now read as modifying the role, the mirror of the existing rule
for a role word **preceding** a name. Verified that `printer Celestin` — the case the check
exists for — is still flagged.

## 5. My read

**Keep it.** On this evidence the rule is better than what it replaces: it publishes three
stops instead of one, costs a quarter as much, and the one story it picks over the old gate's
choice is the better story. The `eventful` key was rejecting a paper-defect narrative as inert
while passing a credits list, which is a classifier that has not earned a veto.

**Two amendments I would make before calling it settled**, both small: require at least one
confirmed-or-corrected claim, and treat `C0 X0` as a failed adjudication rather than a clean
one. Neither reintroduces `eventful`, and both address (a) above, which is the only case here
where the rule published something we had genuinely not checked.

**One measurement outstanding:** 71.7 is a single run. Three runs under D515 against the three
already recorded loop-off runs is ~$0.60 and ~15 minutes, and would tell us whether the jump
from 58.0 is real.
