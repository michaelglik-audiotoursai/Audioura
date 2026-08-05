# STORIED — Michael ↔ Claude (LEAD)

**Started:** 2026-08-05 11:20 EDT
**Tour under review:** `tours/LOCAL259_riviera_2stop_round15.txt` (round 15)

LEAD appends each exchange here as it happens. Michael's words verbatim.
Binding decisions are transferred to `DECISIONS.md`; this file is the
conversation.

*(Earlier exchanges cleared at Michael's request. They remain in git history at
commit `2bf3c35` if ever needed.)*

---

## Round 15 — what is in it

Generated 11:20 with **every gate on**, including the two that round 10 was
missing:

| stage | round 10 | round 15 |
|---|---|---|
| stop-existence gate (ENFORCE) | yes | yes |
| style retry, R9, R10, CONTRADICTED, coverage | yes | yes |
| prolog + orientation gating | yes | yes |
| subject routine | disabled | **on** |
| **R7 invented-sensory deletion** | **absent** | **on** |
| **R1 imperative rewrite** | **absent** | **on** |

Run reported: 708 words, R1 2 rewritten / 4 residual, R7 0 residual,
`Description:` labels 0, fragments 3, facts — Cap d'Antibes 2, Èze Village 7.
Cost $0.0099.

**LEAD's own read, before you start:** the reported "R7 residual 0" does not
match the text. The orientation still says *"the gentle sea breeze carries the
scent of pine trees"*, and stop 1 has *"the waves crash against the rocky
shore, blending with the calls of seagulls soaring overhead"* and *"the warmth
of the sun on your skin"*. That is the invented-sensory class you scored 1/5,
reported clean. It is the sixth time this week a metric has read clean over
visibly broken text — so treat the numbers above as unverified and trust what
you read.

Èze Village is the stronger stop, as it was in round 10.

---

## 2026-08-05 11:24 — Michael

> So the first part of the discussion is to address the questions how improve
> the validation. The second part how to improve the scoring evaluation system.
> The third part is how to change the architecture so we can move forward. If
> you can, please try to estimate or calculate the change in price as I suspect
> we will be using AI a lot more, so even if I forget to ask, please keep me
> informed what happens with the price. BTW, what is the price of the current
> tour generation including all validation and corrective actions stages.

> Stop 1 starts with orientation -- that is good, but completely is missing the
> general info about the tour. Was not it a requirement?

## 2026-08-05 11:24 — LEAD

### Cost of a 2-stop tour today — and we have been reporting half of it

Measured from the round 15 run:

| stage | cost | tokens |
|---|---|---|
| PHASE 3A stop selection | $0.0003 | 380 |
| PHASE 3B | $0.0005 | 624 |
| Stop 1 narration | $0.0035 | 4,391 |
| Stop 2 narration | $0.0033 | 4,107 |
| Style retry (corrective) | $0.0020 | 2,462 |
| R1 rewrite | **$0.0000** | 0 — deterministic |
| Prolog subject routine | **$0.0000** | 0 |
| **reported total** | **$0.0099** | 12,347 |
| **spine generator (gpt-4o)** | **$0.0107** | 1,275 |
| **TRUE total** | **$0.0206** | 13,622 |

Two things fall out of this.

**1. Validation is currently free.** Every detector — R1, R7, R9, R10, the
existence gate, the corpus checks — is deterministic. The only AI money in the
whole correction path is the style retry at $0.0020, about 10% of true cost.
So the answer to "what will more validation cost" is: **nothing, until we start
using a model to do it.** That is a genuinely good position to be in and worth
protecting as we design part 1.

**2. The single most expensive call is invisible in every cost table we have
published.** `spine_generator.py` calls **gpt-4o** while everything else uses
gpt-3.5-turbo — 11× the per-token price — and it never registers with the cost
meter, so it is excluded from "Total API cost". At **$0.0107 it is 52% of the
real bill.** Every round's reported cost this week has been roughly half the
truth. I will fix the accounting and report true cost from here on.

At $0.0206 a 2-stop tour: an 8-stop tour is roughly **$0.05–0.06**, and 1,000
of them about **$55**. Cheap enough that quality, not cost, is the constraint —
but only while validation stays deterministic.

### The prolog: yes, it was a requirement, and I never dispatched it

You are right, and this one is a straightforward miss on my part. You wrote the
four-part specification in your round 2 review. LOCAL-244 gated the prolog
through R9/R10 and stated in writing: *"Do not write a new prolog generator.
Michael's four-part structure … is a separate task."* **That separate task was
never created.**

What round 15 emits instead sits *after* the orientation and matches none of
the four parts — no tour name, no transport mode, no route or distance or
terrain, purpose given as "a layer of history and culture", and no forward
connection to the stops.

Dispatched as **LOCAL-259**, built to your spec: part 2 uses the real transport
mode and computes distance from the stop coordinates; part 3 must thread facts
that actually exist in the corpus, with an explicit instruction to write the
plain true version rather than manufacture a causal link; part 4 must name what
the stops really contain so it is not another unfulfilled promise. It stays
inside stop 1's payload because 117 existing tours embed it there and the
Flutter player has no separate rendering path (D64).

### On your three-part agenda

Ready when you are — validation, then scoring, then architecture. The cost
figures above are the baseline to measure any proposal against, and I will flag
the delta on each one without being asked.

---
