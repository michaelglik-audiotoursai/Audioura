# Why the Riviera lost stops, and a fairer way to score

For Michael — 6 August 2026

---

## Part 1 — Why the biking tour got fewer stops than asked

You were right that there is no shortage of towns. Nothing about the Riviera was
the limit. **Six separate faults were dropping stops, and five of them were ours.**

| # | Fault | Status |
|---|---|---|
| 1 | The selector proposed **7 candidates for a request of 8** — one short before verification even ran | fixed, LOCAL-290 |
| 2 | The existence gate rejected **real places** — `Old Town of Menton`, `Corniche d'Or` — because "verified" meant *present in our own scraped corpus*, not *exists in the world* | fixed, LOCAL-290 |
| 3 | `verify_landmarks` matched **0 of 28** discovered landmarks, because the landmark cache held Wikipedia **section headings** ("Origin of term", "Canton of Sainte-Maxime") instead of places | fixed, LOCAL-293 |
| 4 | The SPARQL path admitted **cantons and railway stations** as landmarks, diluting the real ones | fixed, LOCAL-294 |
| 5 | Nothing **replenished** after the gate dropped a stop — 8 became 5 and stayed there | fixed, LOCAL-290 |
| 6 | A stop whose description failed to generate shipped as an **empty shell** — header, address, no narration — and *counted as delivered* | fixed, LOCAL-292 |

Fault 2 is the one worth dwelling on, because it is the same mistake I made
myself for eight days over the Grant print (D127/D162): **treating absence from
our data as absence from the world.** Menton's old town is real, famous, and
documented. We rejected it because we had not scraped it yet.

**Measured effect on 8-stop Riviera requests:**

```
before the fixes   5/8   (and one of those five was an empty shell)
after              7/8, 8/8, 8/8
```

So the answer to your question is: the towns were always there. We were throwing
them away and then scoring ourselves down for their absence.

---

## Part 2 — Your objection is right, and here is what I would change

You said you are not convinced a shortfall should be punished as severely as it
is now, especially when the data exists — and that where the world genuinely
holds less material, its influence on the score should be smaller.

I agree, and the current rubric cannot make that distinction at all.

### What is wrong now

```
MISSING     = −1.0 × share
FABRICATED  = −1.0 × share
```

Two problems in those two lines.

**First, a missing stop costs exactly what a fabricated one costs.** Omitting a
stop disappoints a listener. Inventing one *misleads* them — and everything we
have built this week exists to prevent that. The rubric is indifferent between
them, which is wrong on the merits.

**Second, and this is your point: every missing stop is treated identically,
whatever the reason.** An 8-stop request that yields 5 loses **37.5 points**
before a single word is judged, whether that happened because our gate rejected
Menton or because the location genuinely has nothing to say.

### The distinction the rubric should make

A stop can be missing for two very different reasons:

- **PIPELINE-LOST** — the stop was proposed, it exists, and we lost it. A
  generation failure, a gate bug, no replenishment. **Our fault. Penalise it
  fully.** All six faults above were this.
- **UNAVAILABLE** — the area genuinely does not offer N places that pass an
  honest existence check. An obscure village with three documented sites cannot
  yield eight stops and should not be marked down for it. **The world's limit,
  not ours. Little or no penalty.**

**This is now computable, and it was not before.** LOCAL-290 separated "not in
our corpus" from "not real", so we can finally ask whether a stop is missing
because the world lacks it or because we do. The gate already logs the reason for
every drop.

### What I would actually change

**1. Split MISSING into two outcomes.**

```
PIPELINE-LOST   −1.0 × share      our failure, full cost
UNAVAILABLE     −0.15 × share     honest scarcity, a nudge not a punishment
FABRICATED      −1.5 × share      misleading is worse than omitting
```

The small residual on UNAVAILABLE matters: a 2-stop tour of a rich city should
still score better than a 2-stop tour of a place with nothing in it, because the
listener's hour is worth more in the first. But it should be a nudge, not −12.5
per stop.

**2. Report coverage separately from quality, and stop collapsing them.**

```
quality   = how good are the stops we delivered   (normalised per stop)
coverage  = delivered ÷ achievable
achievable = stops in this area that pass a genuine existence check
```

Right now these are fused into one number, so a selector bug and thin prose move
the same needle and you cannot tell which. Two numbers tell you what to fix. One
number tells you only that something is wrong.

**3. Normalise quality against what was obtainable.**

This is your "esoteric tours" point, generalised. A stop with six corpus passages
that delivers six facts has done everything available to it. A stop with six
passages that delivers one has not. Scoring both against a fixed absolute bar
punishes the first for the world's stinginess. LOCAL-291 already measures
groundedness per stop, so the denominator exists.

### What I would not change

**Keep the requested count visible.** If you ask for eight and get five, you
should see "5 of 8" prominently — even when all three missing stops were
genuinely UNAVAILABLE. The score should not punish us for the world, but you
should never have to hunt for the fact that the tour is shorter than you asked.

**Keep FABRICATED uncomputable.** Nothing in the scorer checks whether a fact is
true, so it stays a human judgement. Absence of FABRICATED is not evidence of
accuracy, and no weighting change should imply otherwise.

---

## What this needs from you

The three weights — **−0.15 for UNAVAILABLE, −1.5 for FABRICATED, and whether
coverage appears alongside the score or inside it** — are product judgements
about what harms a listener most. I have given my view; I have not implemented
any of it. Say which you want and I will dispatch it.

The rest (splitting MISSING by reason, normalising quality against available
corpus) I would treat as straightforward correctness work and do without asking,
once you have set the weights.
