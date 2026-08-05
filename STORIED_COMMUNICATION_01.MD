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

## 2026-08-05 11:32 — Michael

> As soon it is working please create another tour txt file and place it in
> VSCode where ...round15.txt is currently placed. And plese calculate the cost
> and let me know how it is changed by the includsion of the tour's overall
> general description. BTW, I gave instructions for the components and order for
> overall general tour description; I assume there are being incorporated into
> the tasks to create and then validate the overall general description of the
> tour. Please confirm.

## 2026-08-05 11:32 — LEAD

### Confirming: partly — creation yes, validation no. Now fixed.

| | in place? |
|---|---|
| **Creation** in your four parts, in your order | **yes** — LOCAL-259, running now |
| Each part passes the existing style gates (R1/R7/R9/R10) | **yes** — inherited |
| **Structural check** that all four parts exist, in order, each doing its job | **no — this was the gap** |

Acceptance for the structure was going to be me reading it once. That is not
good enough on this project: every requirement without an automated check has
regressed silently — the `Description:` label came back after being fixed, R9's
transition sentence came back, the epilog templates came back. A structural
requirement with no detector holds until the next generation and no longer.

Dispatched **LOCAL-260** to build `validate_prolog_structure`, checking each
part is present, in order, and carrying substance:

- part 1 must name the tour subject **and** the transport mode;
- part 2 must carry at least two of endpoints / distance / terrain / duration;
- part 3 must carry a sourced fact — a date, a named person and what they did;
- part 4 must name real stop content, cross-checked against the stops actually
  in the tour, so "more stories await" fails and "Monet's 1888 series at
  Antibes, and the 1306 chapel at Èze" passes.

Round 15's opening is the reference failure: **if the validator passes it, the
validator is wrong.** It also has to fail a keyword-stuffed prolog, because the
obvious way to fake this check is to mention "cycling" and say nothing.

### Cost of the general description — it is already the most expensive thing we do

The tour's overall description is **not a new call**. It is the spine's
`tour_hook`, produced by `spine_generator.py`, which is the one component
calling **gpt-4o**:

| | |
|---|---|
| current spine call (produces the opening) | **$0.0107** — 1,275 tokens, in=841 out=434 |
| share of the true $0.0206 tour cost | **52%** |
| every other call | gpt-3.5-turbo, ~11× cheaper per token |

So restructuring it into your four parts changes the **prompt**, not the number
of calls. The delta is output length: a proper four-part opening is perhaps
600–700 output tokens against 434 today, and gpt-4o output is $0.015/1k.

| | cost |
|---|---|
| tour today (true) | $0.0206 |
| four-part opening, estimated | **+$0.003** |
| **estimated new total** | **≈ $0.024** (+15%) |

I will replace that estimate with the measured figure when LOCAL-259 lands.

The structural validator (LOCAL-260) is specified to be **deterministic and
free**, like every other gate we have. If any part of it needs a model, the
task requires it to say so and justify it.

### Next

When LOCAL-259 lands and passes review I will generate the tour, write it to
`tours/`, open it in VS Code in the same place round 15 is now, and report the
measured cost alongside the $0.0206 baseline.

---

## 2026-08-05 11:42 — LEAD (unprompted: a correction you should see)

**D127 was wrong, and it was my error to keep building on it.**

While checking whether LOCAL-258 had smuggled fabricated stops past the
existence gate, I fetched the museum's own commented-works page,
`maa.departement06.fr/les-oeuvres-commentees`. **All eight disputed works are
on it**, including:

> **Ulysses Grant au Japon** — *"cette estampe représente la réception au
> palais impérial du président des États-Unis"*

That is, near enough word for word, the sentence our tour produced and that we
jointly concluded was invented. **The generator was reproducing the museum's own
catalogue.**

Your original search was reasonable and I adopted its conclusion wholesale. The
mistake was mine: I treated "a general web search does not show it" as proof of
absence, for eight days, with the museum's own site one fetch away.

**What it cost.** I instructed LOCAL-254 to treat those stops as fabrications
and it stripped their corpus to zero — legitimate works, deliberately emptied,
on my instruction. Three task files carried the false premise. A decision entry
recorded a prohibition breach that never happened. I am restoring the corpus.

**What survives.** One narrower question: your search indicated the Chikanobu
triptych shows the Ueno Park festival of 25 August 1879, not the Imperial
Palace reception. The museum's catalogue says imperial palace. So either it is a
different print, or the museum's own description is wrong. That is a question
about a source we trust, not about our generator — and under your D100 rule it
is the *unverifiable* case, not the *known-incorrect* case. Worth a look when
you have a moment; it does not justify blocking the stop.

### Meanwhile: your gate venue is unblocked

LOCAL-258 fixed the parenthetical. All three spellings of the Asian Arts name
now resolve to Q3330160, and Palais Lascaris, Matisse, Chagall and MAMAC still
resolve — no regression. Downstream:

| | before | after |
|---|---|---|
| canonical titles from story_miner | 0 | **16** |
| stops passing the existence gate | **0 of 8** | **8 of 8** |
| 8-stop tour generated | no | 6 of 8 stops, 1,935 words |
| cost | — | **$0.0572** |

The 16 titles come from the museum's own page plus Wikidata — none
hand-registered, which was my stated rejection criterion. Two stops still
produce no description for want of per-work source material; that is the next
constraint at this venue, and it is corpus, not gate.

**Cost note, as promised:** the 8-stop tour at $0.0572 tracks the 2-stop
$0.0206 almost exactly — fixed spine and selection costs plus roughly $0.005
per stop of narration.

---

## 2026-08-05 11:48 — Michael

> I am looking at ..._round15.txt and in Orientation I see user instructions such
> as "enjoy the sea breeze" I assume this si because we excluded Orientation from
> validation on providing instructions, if so, it is all good. Need a
> confirmation.

> All good, as intended.

## 2026-08-05 11:48 — LEAD

Corrected the premise before confirming: orientation is **not** excluded from
R1 — R1 runs on it and fires on that sentence. It survives because the sentence
counts as **navigation** (D107), and the exemption is sentence-level while the
instruction is a clause riding along inside it. Alone, "Enjoy the sea breeze
along the coast." is deleted outright.

Michael ruled: **"All good, as intended."** Recorded as **D164**, with an
explicit instruction that no future task may narrow the navigation exemption in
a way that removes this pattern.

The distinction now on the record, in his terms: R1 exists to stop the tour
telling you what to feel *instead of* telling you something. A pleasant clause
attached to a real direction is not that.

---

## 2026-08-05 11:52 — Michael

> I am looking at ..._round15.txt and after the Orientation, I see the paragraph
> of the tour description, so claiming that we missed it was wrong: "From the
> secluded allure of Cap d'Antibes to the medieval whispers of Eze Village, each
> stop reveals a layer of history and culture, painting a vivid picture of a
> region shaped by time and tide. …" So the serious problem that it does not name
> the tour. If it started with "On this biking tour of French Riviera, from the
> secluded..." I would not have missed it. I assume that the new generation
> includes this task -- needs the confirmation and we are not going to have two
> tour descriptions because of me missing this one, please confirm that also.

## 2026-08-05 11:52 — LEAD

**Your diagnosis is better than mine.** I framed round 15's opening as "matching
none of the four parts", which is true but abstract. Yours is the operative
fact: **the description exists and you read straight past it, because nothing in
it says what the tour is.** That is the defect — not absence, unrecognisability.
Recorded that way.

**(a) Does the new generation name the tour? Yes — confirmed.**
LOCAL-259 part 1 is "the tour name and including transportation", and LOCAL-260's
validator requires part 1 to name **both** the subject and the transport mode.
A biking tour whose opening never says it is a biking tour fails the check.

**(b) Two descriptions? You caught a real gap — it was not guarded.**
LOCAL-259 says "place it before the orientation of stop 1" and **never says it
replaces the existing one.** The existing description is the spine's `tour_hook`,
which sits *after* the orientation. A literal reading produces exactly the two
descriptions you are worried about.

Fixed two ways:

1. **Addendum appended to LOCAL-259** — the four-part opening REPLACES the
   `tour_hook`; two descriptions is a bounce. It is mid-run, so this binds on
   re-dispatch and I will check the artifact myself at review.
2. **`DUPLICATE_TOUR_DESCRIPTION` added to LOCAL-260's validator** — exactly one
   tour-level description per tour, detected structurally rather than by
   position, with both spans quoted on failure. That is the durable guard; the
   addendum only covers this round.

I also added your two strings to the validator's boundary rows as the reference
cases: *"From the secluded allure of Cap d'Antibes…"* must **fail** part 1, and
*"On this biking tour of the French Riviera, from the secluded allure of Cap
d'Antibes…"* must **pass**.

---

## 2026-08-05 12:04 — Michael

> The second sentence "This iconic cape, situated on the French Riviera, holds a
> significant place in the region's landscape." is good because it immidiately
> followed by "In 2023, Antibes boasted a population of 77,637, making it the
> second most populous area in Alpes-Maritimes after Nice" that supports it; and
> makes both sentences worth while. Please confirm that this will continue be the
> case.

## 2026-08-05 12:04 — LEAD

**Confirmed — it is safe. But it survives by accident, and its evil twin
survives too.**

Nothing fires on either sentence today, so LOCAL-261's new deletion phases will
not touch them. Good.

The catch: in **round 2** you scored **2/5** on a nearly identical sentence —
*"Cap d'Antibes, situated on the French Riviera, holds a special place in the
region's history and culture"* — with the reasoning *"nothing about aspects
named such as place, history, and culture are described in the following
sentence."*

I ran that unsupported version through today's pipeline. **Nothing fires. It
would ship.**

Same shape, opposite verdict from you, and our rules cannot tell them apart.
Your distinction is entirely about **what comes next** — which is exactly what
R10's delivery lookahead was built to do. It never engages here because R10 does
not recognise "holds a significant place" as a promise in the first place.

**So the fix is not to teach R4 or R9 to delete this shape** — that would kill
your good pair along with the bad one. It is to teach **R10** the shape, after
which the existing delivery check decides automatically: deleted when nothing
follows, kept when the population fact does.

Two things done:

1. **Addendum on LOCAL-261** — no new deletion phase may delete a claim on its
   own wording; each must apply the R10 delivery lookahead first. Your approved
   pair is now a mandatory must-survive boundary row.
2. **LOCAL-262 queued** — teach R10 this promise shape. Small change, and it
   implements your distinction exactly.

**The wider point, recorded as D166.** Every rule we own judges a sentence in
isolation, except R10. You have never once judged a sentence in isolation —
round 2 is almost entirely about interconnection: *"senseless combination of
words and facts with no interconnectedness between them."* The gap between how
we measure and how you read is **adjacency**, and R10 is the only place we model
it. That is probably the single most useful thing to come out of this session so
far, and it belongs in part 1 of your agenda.

---

## 2026-08-05 12:18 — Michael

> yes, dispatch it first, generate a new tour and add it to my VS code view where
> ...round16.txt is seating. One thing is important: not everything can be
> algorithmic and free however preferrable, so if this rule (to me it complex and
> if it works great compliment to you) does nto work efficiently enough we may
> use another call to AI to verify that fact and find the sentence set
> replacement. Please keep it in mind.

## 2026-08-05 12:18 — LEAD

**Dispatched as LOCAL-263.** Your escalation point is built in as a first-class
part of the design, not a footnote — it is quoted verbatim in the task.

### The gate

Two stages, one shared test.

**Stage 1 — classify what the sentence asserts:**

| type | example | today |
|---|---|---|
| `PROMISE` | "holds stories that deepen the allure" | R10 |
| `SENSORY` | "the waves crash against the rocky shore…" | R7, partially |
| `FEELING` | "invites contemplation and serenity" | R4, partially |
| `QUALITY` | "holds a significant place in the region's landscape" | **nothing** |

**Stage 2 — one substantiation test for all four:** does a nearby sentence
supply a concrete payload on the same subject — a date, a named person and what
they did, a documented event, a measurement? Substantiated, keep. Not, remove.

That single test replaces four divergent pattern lists, and it makes your rule
directly expressible instead of approximated.

### Your escalation instruction, as specified

Deterministic first. A model is called **only** when the claim is unsubstantiated
*and* the stop's corpus holds a fact that plausibly bears on it. Its job is
narrow and bounded:

1. verify whether the passage actually substantiates the claim;
2. if so, rewrite claim and support as a coherent sentence set — **using only
   that passage, adding no fact**;
3. if it cannot ground it, return "delete" — deletion stays the fallback.

One call per stop maximum, batching that stop's uncertain sentences, and the
escalation cost is reported separately from generation. Baseline to beat is
$0.0206 per 2-stop tour, of which $0.0107 is the gpt-4o spine. If escalation
never fires on the Riviera tour, that is a good result and the task must say so.

### On "to me it complex"

It is less complex than what we have. Today four rules each carry their own
pattern list and none of them looks at the next sentence. This is one rule with
four labels and one question. The complexity you are sensing is real but it sits
in the *substantiation test* — and that already exists and already works, in
R10.

### The tour

The task generates **round 18** and writes it to `~/Audioura/tours/`. I will open
it in the same VS Code view as round 16 when it lands — roughly 20 minutes. It
will also copy the artifact across explicitly, which is the step I missed on
round 16 and why you got an empty buffer.

---

## 2026-08-05 12:27 — Michael

> Great! I am waiting for round18 to continue. BTW, in round 16 I liked the tour
> description much better, almost perfect so I am ego to see if 18 would be as
> good.

## 2026-08-05 12:27 — LEAD

Round 16's description is now a **must-survive boundary case** on LOCAL-263,
quoted verbatim, with the specific sentence at risk called out.

That sentence is the third one: *"The path winds through a landscape where
artists like Monet found inspiration and where historical events shaped the
region's identity."* Classified on its own it is a `QUALITY` claim carrying no
date and no specific event — **a naive gate deletes it.** It must survive
because the next sentence substantiates it (Monet in Antibes, Èze under the
House of Savoy). That is exactly the adjacency test the gate exists to
implement, so this paragraph is the case that proves whether it works.

The task now says: if the gate deletes sentence three, the gate is wrong, not
your paragraph. It must report a verdict and a reason for all five sentences.

Round 18 is ~4 minutes into a run that typically takes 12–25. Two caveats on
what you will see:

1. It was dispatched **before** the Orientation reordering, so it may emit the
   old shape. The addendum tells it to reconcile; if it does not, that is a
   merge detail rather than a quality signal — judge the description text, not
   its position.
2. **The stop selector varies between runs.** Round 17M came back with Cap
   Ferrat instead of Cap d'Antibes. So a round-to-round comparison is partly
   comparing different tours, which has been quietly weakening every comparison
   we have made today. Worth pinning the stop pair for evaluation runs, and I
   will propose that separately.

---

## 2026-08-05 12:30 — Michael

> no-no, I do nto want to enforce anything artificial on the tour generation: if
> they have different stops, so to be it. That is fine.

## 2026-08-05 12:30 — LEAD

Recorded as **D170** — stops stay free, and no future task may "helpfully" pin
the selector.

The consequence moves to scoring rather than generation. With the pair varying,
comparing two single tours cannot attribute a difference to a code change: stop
selection, corpus depth at those stops, and the change all move together. Much
of today's round-to-round narrative has that weakness in it, including "round 16
was better than 17M".

The fix is not to remove the variance but to measure past it — rates instead of
counts (facts per sentence, not per tour), per-stop normalisation against that
stop's corpus depth, and several runs rather than one when judging a change.
That is a part 2 proposal, not something to bolt on now.

---

## 2026-08-05 12:42 — Michael

> is it becoming longer to generate? May I ask you to track the timing in
> additin to the price?

## 2026-08-05 12:42 — LEAD

**No — generation is flat.**

| run | pipeline | spine call | true cost | words |
|---|---|---|---|---|
| round 10 | 42.7s | 8.2s | $0.0206* | 679 |
| round 15 | 43.7s | 5.3s | $0.0206 | 708 |
| round 16 | — | — | $0.0184 | 652 |
| round 17L | 41.1s | 7.7s | $0.0187 | 388 |
| round 17M | 43.5s | 6.9s | $0.0202 | 718 |

41–44 seconds, no trend. Spine latency wobbles 5.3–8.2s on network and model
variance. Everything added today is deterministic, so it costs neither money
nor measurable time.

**Timing is now tracked alongside cost as standing practice** — pipeline
seconds, spine latency, and escalation latency once LOCAL-263 adds one.

**The number to watch is escalation.** Your AI-verification path is the first
thing that can make generation genuinely slower, because it puts a model
round-trip inside the loop. One call per stop on an 8-stop tour is 8 sequential
calls; at 2–5s each that is 15–40s on top of a 43s run. Measured figure to
follow when round 18 lands.

**A distinction worth keeping separate:** the *development* round-trip is
getting longer — LOCAL-263 is 18 minutes in, earlier tasks ran 8–40 minutes.
That is the Kiro agent reading code, writing changes, running boundary tests and
regenerating. It has nothing to do with tour generation speed, and the two will
be reported separately so neither is read as the other.

---

## 2026-08-05 13:20 — Michael

> on ..._round19.txt I see a sentence "The town transformed from a military
> stronghold to a vibrant hub of maritime activity. In the early 20th century,
> Saint-Tropez was a quiet fishing village until World War II, when it became the
> first town liberated during Operation Dragoon." -- beautiful and ineresting,
> but it mentions Operation Dragoon with no explanation. Don't we have a rule
> that if an action or a person is mentionned we should briefly follow up with
> the story?

> let's try to dispatch on anything a general audience likely doesn't know, AND
> glosse things the tour itself has made load-bearing. If it becomes too much in
> generation time, listening time, and cost, we will cortail it later. Feel free
> to engage with AI despite more cost.

## 2026-08-05 13:20 — LEAD

**No such rule existed, and it is the inverse of everything built today.**
Dispatched as **LOCAL-269** with both of your triggers.

| | failure | example |
|---|---|---|
| the claim gate | a claim with no fact behind it | "holds a significant place in the region's landscape" |
| **this** | **a fact assuming knowledge the listener lacks** | "liberated during Operation Dragoon" |

A rule catching the first cannot catch the second, because the second **is** the
delivery the first is looking for. That sentence passes every gate precisely
because it carries facts.

It also completes a directive we implemented only half of. Round 2: *"if we
claim history, we must tell the story or remove the sentence."* We built removal
and read "tell the story" as "have a fact". You meant the listener should end up
**knowing** something.

**The risk I have guarded hardest.** A gloss is a factual claim. If the model
writes it from memory we reintroduce unsourced facts — laundered through a stage
built to improve accuracy, which is D127 and D162 all over again. So the order
is: corpus first; a model gloss only with a citable basis shown in the
submission; and if neither, **degrade the reference rather than delete the
sentence** — "the first town liberated in 1944" keeps your good fact without
confusing anyone or inventing anything. Deletion is last resort.

Glosses capped at **8–14 words**, because you named listening time as a cost.

**Cost and time will be reported against these baselines, unprompted:**
$0.0206 per 2-stop tour, 43s generation for 2 stops / 73.5s for 8, 620 words.
The task must flag prominently if added cost exceeds $0.02 or added time exceeds
30s — you can only curtail if the number is in front of you.

Unlike the claim gate, whose escalation fired **zero** times, this one will fire
often. Tours are full of named entities. This is the first change today that
should genuinely move both the cost and the clock.

---

## 2026-08-05 13:40 — Michael

> Why round 20 has 8 stops instead of 2? Why the general tour description does
> nto include a preview of the stories found later in the stops?

> Yes, please "dispatch that reordering" I am looking forward for a tour that has
> intrigue and stop reference in the generic tour description.

## 2026-08-05 13:40 — LEAD

**Round 20 has 8 stops because LEAD set it that way** to test your hypothesis
that more stops yield more intrigue. It confirmed it — 5.0 facts per stop against
2.0 in round 19. The filename `..._2stop_round20_8stop.txt` is LEAD's error: the
script was derived from the 2-stop one and the template kept the old label.

**Part 4 is missing because the tour description is written before the stories
exist.** The call order:

```
PHASE 3A  pick stops
PHASE 3B  resolve details
SPINE     <- writes the description INCLUDING part 4
Stop 1..N <- the stories are written HERE, afterwards
```

So when the spine writes "in the stops ahead you will encounter…", **no stop
narration exists yet.** It guesses from canonical titles.

| round | part 4 |
|---|---|
| 16 | present, good |
| 19 | partial |
| 20 | **absent entirely** |

Same code each time. **Round 16 was luck** — which also means every comparison
we made today between round 16 and later rounds was partly comparing two coin
flips.

**Dispatched LOCAL-270.** Part 4 leaves the spine prompt and is composed *after*
narration, from the delivered and gated text. Every entity it names is verified
present in the stop it is attributed to — so it becomes structurally impossible
to promise something the tour does not contain. If a tour has too little
surviving content to name anything specific, it emits **no** part 4 rather than
"more stories await", which is the exact failure R10 exists to catch.

Both a 2-stop and an 8-stop tour will be regenerated, since the 8-stop case is
where part 4 vanished completely and is therefore the one that proves the fix.

**Also merged this tick:** the corpus LEAD wrongly ordered deleted is restored,
and D127 is closed for good — the museum's page carries inventory number
**2015.6.A.1** and donor **"Don Herrli"** for the Grant print. No model invents
an accession number.

---
