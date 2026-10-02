# LEAD review — MFA "Unbound" tour (`/tmp/mfa373.txt`)
**2026-08-10, after LOCAL-373. Reviewer: Claude (LEAD). Verdict: NOT SHIPPABLE.**

---

## Correcting what I told you earlier today

In D291/D292 and in my tick summaries I said the tour was **"3 real works, all
grounded, no backfill."** That statement was true only about **titles**, and I
did not say so. `title_appears_in_page` is a check on the stop *heading*. Nothing
in the pipeline checks the *prose*.

Having now read the delivered text against the source page, the prose contains
fabricated attributions. The retrieval chain (D273→D292) is genuinely fixed. The
tour built on top of it is not deliverable.

---

## What the MFA page actually says

From `tests/fixtures/mfa_picasso_miro_dali_unbound.html`, verbatim:

> **Joan Miró**, *Le Lézard aux plumes d'or (The Lizard with Golden Feathers)*
> (detail), published by Louis Broder, printed by Mourlot Frères, Paris, **1971.
> Illustrated book** … Gift of Boris Fridman.

> …as **Dalí** did in his **1974 illustrations for Sigmund Freud's** *Moses and
> Monotheism*; others partnered with writers…, as in **Juan Gris** and French
> poet **Pierre Reverdy's** *Au Soleil du Plafond* (1955). Rarely on view, …
> these **livres d'artiste** invite visitors into a world of…

The exhibition is about **artists' books**. That is what "Unbound" means here.

---

## What the tour says

| Stop | Tour claims | Page says | Verdict |
|---|---|---|---|
| 1. Le Lézard aux plumes d'or | "**Rousseau's** jungle setting"; a painting with "brushstrokes", a "golden-feathered lizard amidst a lush jungle landscape" | **Joan Miró**, 1971 **illustrated book** | **Fabricated attribution.** "Rousseau" appears **0 times** on the page |
| 2. Moses and Monotheism | "portrays **Moses as a central figure**, radiating authority"; "**monochromatic** color palette" | **Dalí's illustrations for Freud's book**, 1974 | Dalí and Freud **never named**. Visual claims unsourced |
| 3. Au Soleil du Plafond | "**Le Corbusier's ceiling mural**"; "Stand directly beneath… **Look up**" | **Juan Gris** with poet **Pierre Reverdy**, 1955 | **Fabricated attribution.** "Corbusier" appears **0 times**. It is a book, not a ceiling |

I grepped the fixture for each name. `Rousseau` → 0 hits. `Corbusier` → 0 hits.
`Miró` → 7. `Gris` → 1. `Reverdy` → 1.

---

## The three failures, in order of severity

### 1. Two of three stops name the wrong artist — and neither name is on the page
This is not a retrieval miss. It is the model writing from parametric memory
about a *title* it was handed. "Le Lézard aux plumes d'or" sounds like a Douanier
Rousseau jungle; "Au Soleil du Plafond" sounds architectural, so Le Corbusier.
Both are plausible-sounding inventions of exactly the kind D275 forbids for
*works*, arriving instead through *attributions*.

**The grounding gate has a hole in the shape of everything that is not a title.**

### 2. Every work is a book; the tour describes paintings and a ceiling
Stop 3 instructs the visitor to stand beneath a mural and look up. In the gallery
they will be standing in front of a vitrine containing a 1955 book. This is the
one error a visitor cannot rationalise — it fails at the moment they follow the
instruction.

The exhibition's own subject — the livre d'artiste, the bound-versus-unbound
question in the title — **appears nowhere in the tour.** This is precisely the
material D289 said to fill thin exhibitions with, and Thread A/B in LOCAL-369
were built to supply. On this run they contributed nothing.

### 3. The prose is thin where it is not wrong
Even setting fabrication aside: "This masterpiece challenges the boundaries
between reality and imagination." "This masterpiece transcends mere decoration."
"evoking wonder and admiration." These are the class-1 empty sentences LOCAL-375
just measured at 61% of flagged hits. The closing line is broken grammar of the
D288 class:

> "That's 3 stops — Au Soleil du Plafond, blurring art and architecture with a
> mural and Le Lézard aux plumes d'or challenges reality and imagination as a
> masterpiece."

Stop 2 also has no Orientation while stops 1 and 3 do, and coordinates appear
only on stop 1.

---

## What this means for the picture we had

**The retrieval chain works and that result stands.** Seven defects
(D273/274/275/284/287/291/292) took us from "returns Ancient Nubia" to "returns
the three works actually in this show." That was real and it is not undone here.

**The defect has moved one layer down**, from *which objects* to *what we say
about them*. It was invisible while the pipeline was returning the wrong objects
entirely — you cannot see that stop prose is unsourced when there is no stop.

**The credit line was right there and unused.** The page gave us artist, date,
publisher, printer, medium and donor for stop 1, in one string the extractor
already parsed (LOCAL-369 built provenance handling for exactly this). The tour
used none of it and invented a different artist instead.

---

## My recommendation

**Do not field-test this tour.** Not a close call — a visitor told to look up at
a Le Corbusier ceiling that is a Juan Gris book in a case will conclude the
product does not know what it is talking about, and they will be right.

**Three tasks, in this order.** I have not dispatched them — you are at 95% of
the weekly ceiling and I would rather you set the sequence:

1. **Ground the prose, not just the title.** Every named person, date, medium and
   place in stop prose must appear in the page text that stop was built from, or
   be dropped. The check exists for titles; extend it to entities. This is the
   one that makes the tour honest.
2. **Feed the credit line into the stop.** Artist, date, medium, publisher, donor
   are already extracted. A stop that says "Joan Miró, 1971, illustrated book with
   lithographs, published by Louis Broder, gift of Boris Fridman" is both true and
   more interesting than what we shipped.
3. **Give the exhibition its own subject.** "Unbound" is about livres d'artiste
   and the tour never says so. D289's ruling — supplement with story, never with
   invented works — is exactly this, and the story here is sitting in the page's
   own opening paragraph.

**On the LOCAL-375 finding, sharpened by this tour:** I recommended narrowing the
empty-sentence heuristic before enforcing. This tour is evidence for that
sequencing — its worst sentences are fabrications that are *grammatically rich*
and would sail past an empty-sentence gate, while its harmless visual
descriptions are what the gate would catch. Enforcement on this metric was never
going to prevent this failure. Fabrication needs the grounding fix, not a
threshold.

---

## Standing items, unchanged

- **Boston Globe credential (D223)** — still needs rotating if real. 4 days open.
- **Threshold for `empty_sentence_count`** — yours to set once the narrowing lands.
