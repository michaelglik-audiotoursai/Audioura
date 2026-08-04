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

### 3a. The truth gate would delete his favourite sentence

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

**Revised proposal:** an unsupported claim does not cap the score. It **blocks
publication of that sentence until it is either sourced or removed** — a
separate axis from quality. A sentence can be excellent *and* unpublishable.
Conflating the two produced a rule that argues against our best output.

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

## 7. What I need from Michael

1. **Does the split at §3a match your intent?** Quality score and
   publishability as two separate axes — a sentence can be excellent and still
   blocked for being unsourced.
2. **R9 (generic → delete):** is deletion always right, or are there
   connectives you want kept for flow even when they say nothing?
3. **Sentence groups:** you grouped 1–3 sentences by idea rather than scoring
   each one. Should the system group the same way, or score every sentence
   individually?
