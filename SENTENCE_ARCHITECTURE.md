# Sentence-level generate → evaluate → rewrite

**Michael's proposal, 2026-08-04, and what his own evaluation proves about it.**

> "After we generate the paragraph we should evaluate it sentence by sentence
> and then try to rewrite it. This is also can be beneficial when we get to
> multiple stories and can select on user preferences."

I agree, and his evaluation of the Riviera tour is the strongest evidence for
it we have. This document sets out why, what it changes, and the two places
where his judgement contradicts the scoring I proposed.

---

## 1. His scores

Eleven sentence groups across six paragraphs:

| ¶ | group | score | why |
|---|---|---|---|
| 1 | A — cycling directions | **5** | |
| 1 | B — "listen to… Look out for…" | 1 | instructions to the user |
| 2 | prolog | 3 | conditional: *only if* the promises are kept later |
| 3 | A — Monet, 1888, Tire-Poil 2.7 km | 3 | |
| 3 | B — "take in the sight… Pedal… envisioning" | 2 | "too many without substance" |
| 4 | A — "pause to take in" | 1 | instruction |
| 4 | B — "Look for the Rue Obscure" | 1 | instruction, and the story is missing |
| 5 | A — Free City on Sea, 320 ft anchorage | **5** | |
| 5 | B — "whispers tales of a bygone era" | 1 | |
| 5 | C — "consider how these hidden paths…" | **0** | "can be placed in millions of stops" |
| 6 | transition | **0** | same |

**Mean 2.0 / 5.** The gate is 3.5. He is right that this is far from acceptable.

---

## 2. The paragraph is the wrong unit, and his data proves it

Every paragraph he split has a good half and a bad half:

| ¶ | parts | paragraph average | what averaging hides |
|---|---|---|---|
| 1 | 5, 1 | 3.0 | a perfect sentence and a failing one |
| 3 | 3, 2 | 2.5 | — |
| 5 | 5, 1, 0 | 2.0 | our best sentence and our worst, in one score |

A paragraph score of 3.0 tells you to improve the paragraph. The sentence
scores tell you to **delete two sentences and keep the rest** — which is a
different, cheaper, and more reliable action.

This also explains why three rounds of paragraph-level work moved nothing.
LOCAL-192 regenerated whole paragraphs when any rule fired: it rewrote the 5/5
material along with the 1/5 material, and the model had no way to know which
part was the problem.

**Conclusion: score, gate, and rewrite at the sentence group, not the
paragraph.** i-con stays as Michael defined it; the unit it applies to changes.

---

## 3. Two places his judgement contradicts the scoring I proposed

### 3a. ~~The truth gate would delete his favourite sentence~~ — LEAD misread this

`EVALUATION_RECOUNT.md` §3a proposed: any unsupported factual claim caps the
paragraph at 1.

Michael scored this **5/5 — Excellent**:

> "Villefranche-sur-Mer, known as the 'Free City on Sea'… The deep bay of
> Villefranche provides secure anchorage for ships, **with depths reaching 320
> feet**, a natural wonder in the Mediterranean."

`claim_check.py` on the same text, against the 33 corpus passages we hold for
the area:

```
SUPPORTED_PARAPHRASE | known as "the"
UNSUPPORTED          | 320 feet
unsupported_count = 1
```

**My rule scores it 1. Michael scores it 5.**

He is not endorsing invention — his own rewrites add *more* specifics ("tax
privileges granted in 1295 by Charles II of Anjou"). What he is saying is that
**specificity is the thing he wants**, and a number he cannot verify still
reads as vastly better than "ancient streets that exude a timeless charm."

That is exactly the danger: he cannot tell a sourced 320 from an invented one,
and neither can a listener. But capping at 1 is the wrong response, because it
punishes the shape of writing we are trying to get.

**LEAD was wrong to call this a contradiction.** Michael, 2026-08-04:

> *"Incorrect. I would have supported you 100% if I knew that the data was
> incorrect. You said the data was not found aka UNSUPPORTED in corpus
> passages."*

He then searched, found the bay documented at 95–150 m at its outer mouth
(320 ft ≈ 97.5 m), and concluded the figure is probably right. The
disagreement was never about whether the claim was sourced. It was about
**what to do when it isn't** — and his answer is: go and find a source.

**The rule he actually wants (D100):**

| verdict | meaning | action |
|---|---|---|
| `CONTRADICTED` | we are reasonably sure it is wrong | **hard block** |
| `UNSUPPORTED` | we cannot verify it | **publish**, disclosed, *after* trying an external source |
| `SUPPORTED_*` | backed | publish |

> *"We should not publish if we are reasonably sure that the data is incorrect.
> It is a different story if the data is unverifiable… having no information or
> very little information maybe worse than having unverifiable information."*

This is better than LEAD's proposal and implementable today. The hard block
lands on `CONTRADICTED`, which is now trustworthy — 0 of 188 corpus-wide with
no false alarms (D99). LEAD's version blocked on `UNSUPPORTED`, which
over-flags ~17% and would have deleted good writing.

**And the corpus is not the only source.** LOCAL-221 searches for a source
before accepting `UNSUPPORTED`, promoting to `SUPPORTED_EXTERNAL` with a
quoted sentence and a trust tier. Cost, measured: our 2-stop tour costs
$0.0398 (Polly $0.0296 + LLM $0.0102); Serper is $0.001/query, so per-claim
verification is ~75% on top, per-paragraph 15%, per-stop 5%. Michael's
instinct that verification is cheap relative to the tour holds; his "two orders
of magnitude" did not, and per-entity batching is the affordable shape.

### 3b. He has a rule we do not: generic → delete, not score low

Two sentences scored **0** with the same reason: *"can be placed in millions of
stops: nothing related to this one."*

> "As you continue your journey through this charming town, consider how these
> hidden paths have shaped the stories of this place…"

> "From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more
> ground than these stops alone."

Our lowest i-con is 1. He uses 0 and says **"should be removed."** That is not
a score, it is a verdict.

It is also mechanically detectable, which makes it the cheapest win available:
a sentence with no proper noun, no date, no number, and no referent unique to
this stop is generic by construction. **Rule R9 — delete, do not rewrite.**

---

## 4. Three more things his evaluation settles

**Directions are the best content we produce.** Group 1A — pure cycling
navigation, three imperatives — scored **5/5**. The style rules must never
touch navigation, and the existing exemption is right. Worth stating because
R1 now fires on open-class imperatives and it would be easy to break this.

**The prolog is conditional, not good.** He gave it 3/5 "*only if* what is said
here will be disclosed" later. It names Villa Eilenroc's soirées and the Rue
Obscure escape route; the stops must then deliver them. That is a
**promise-keeping check**: every entity the prolog names must appear, with
substance, in a stop body. Detectable.

**His rewrites add far more than they remove.** For Villa Eilenroc he supplies
Charles Garnier, 1867, Hugh-Hope Loudon, "Eilenroc" as "Cornelie" reversed, the
Beaumonts in 1927, the Fitzgeralds. None of that is in our corpus. **The
ceiling is still the corpus** — sentence surgery makes bad text honest, it does
not make it interesting.

---

## 5. The architecture

```
generate paragraph
   ↓
split into sentence groups        (his unit: 1–3 sentences on one idea)
   ↓
classify each group               NAVIGATION | CONTENT | CONNECTIVE
   ↓
per group:
   R9  generic?          → DELETE, no rewrite
   R1–R4, R7, R8 style?  → rewrite this group only, keep the rest verbatim
   unsourced claim?      → source it, or remove the claim, or drop the group
   ↓
reassemble
```

**What makes this different from LOCAL-192:** the rewrite request carries one
group and one named fault, and the surrounding text is untouched. LOCAL-192
handed back a whole paragraph and asked for a general improvement, which is why
R4 survived — the model had no idea which of nine sentences was the problem.

**Cost.** Roughly one small call per failing group instead of one per failing
paragraph. On this tour: 6 failing groups vs 4 failing paragraphs — more calls,
each much smaller. Measure it; do not assume.

---

## 6. Multiple variants and user preference

Michael's second point: once sentences are the unit, generating several
variants and selecting per user becomes natural.

This is already designed — `STORY_QUALITY_DESIGN.md` §2c/2d: every paragraph
carries a soft distribution over `details` / `historic` / `social`, and the
Beta-count preference model updates from swipes. Sentence groups make it
sharper: **3A (Monet, 1888) is `historic`; 5A (320-foot anchorage) is
`details`.** Those are different readers, and today they are welded into one
paragraph.

**Sequencing matters, though.** Variant selection multiplies generation cost by
N and only pays off once the *base* quality is acceptable — choosing between
three 2.0-rated variants is not a feature. Get the mean above the gate first.
The About-page personalisation is the right destination; it is not the next
step.

---

## 7. Answered by Michael, 2026-08-04

**§3a — two axes?** Volume-dependent: block unsourced sentences when we have
plenty of material, allow them when we do not. But *"in today's world we can
and should check trustworthy sources to verify that sentence's facts."* So the
answer is not a gate setting, it is LOCAL-221 — verify first, gate second.

**R9 — always delete?** *"Humans think they are being cheated or misled when
they hear sentences that have no information… and they think the teller is
stupid."* So yes, delete — **but the target is connectives carrying "both
factual and emotional content."** Deletion is the floor, not the goal. A
connective that names something true about the two stops it joins is worth
building; a generic one is worth nothing.

**Sentence groups — group or individual?** **Both, three times.**

> *"On the first pass we should look at the group, then on the second pass
> sentence by sentence, and on the 3rd pass as a group again."*

His reasoning nests: a tour works only if every stop is interesting; a stop
only if every paragraph is; a paragraph only if every sentence is — **but a
sentence judged alone destroys the paragraph as a unit of meaning.** Hence
group → sentence → group.

---

## 8. The Lena test — what all of this is for

> *"Lena said she would not use any museum tour because nowadays she can ask
> Google about any painting by pointing her phone camera at it and get precise
> factual information. I said that she can, but then this information will be
> out of context of her tour, her interests, and will be dry. I am only right
> if our tours will be full of the correct information, that fits Lena's
> interests and enhances the whole tour experience."*

Point-and-ask already beats us on isolated facts, for free. Three things make a
tour worth using instead:

| Lena's test | our work | state |
|---|---|---|
| **correct** | `claim_check` + external verification | built, improving |
| **fits her interests** | swipe/preference model, `STORY_QUALITY_DESIGN` §2c/2d | designed, not built |
| **enhances the whole tour** | cross-stop continuity, SQ-S6b "dominant story" | designed July, **never built** |

The third is the thinnest and the least substitutable — a camera cannot give
you continuity between stops. Michael's own evaluation scored both connective
sentences **0/5**. That is the gap.
