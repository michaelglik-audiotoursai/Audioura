# What is a story? — the encyclopedic answer, and what it decides for us

**Started 2026-08-19 by Michael: "Let's look at the definition of the story to decide
what 'story' is. Let's start with an encyclopedia."**

Written because the generator is currently aiming at two of Michael's own definitions
that disagree (D485), and six rounds of prompt work have gone into a question that is
really a definitional one.

---

## 1. The five definitions worth having

### Forster / Britannica — story vs plot is CAUSALITY

Britannica takes plot as *"the structure of interrelated actions, consciously selected
and arranged by the author"*, and cites E. M. Forster's distinction: a story is a
*"narrative of events arranged in their time-sequence"*; a plot arranges the same events
by cause and effect.

> *"The king died, and then the queen died"* — story.
> *"The king died, and then the queen died of grief"* — plot.

**The whole difference is one causal word.** Nothing else changed.

### Prince — the MINIMAL STORY, and it is a retrieval spec

Gerald Prince (1973): a minimal story is **three conjoined events — the first and third
stative, the second active, and the third the inverse of the first.**

> *Korea was poor.* → *Korea invested in education.* → *Korea is rich.*

This is the most useful definition we have found because it is **mechanically
checkable**: state A, an action by an agent, state not-A.

### Wikipedia — the necessary elements

A narrative is *"any account of a series of related events or experiences."* The basic
elements held to be necessary and sufficient: **character** (individuals whose choices
propel events), **conflict** (tension driving thought and action), plot (events connected
by cause and effect), setting, narrative mode, theme. Narratives operate through cause
and effect, where *"characters' actions or other events produce reactions that allow the
story to progress."*

### Labov — what counts as a story when it is SPOKEN ALOUD

Labov (1972) studied narratives told out loud, which is exactly our medium. Six parts:
**abstract, orientation, complicating action, evaluation, resolution, coda.** Not all
are required — but the one he treats as indispensable is **evaluation**: the means by
which the narrator indicates *the point*, the reason it was worth telling.

> *"Pointless stories are met (in English) with the withering rejoinder, 'So what?'
> Every good narrator is continually warding off this question; when his narrative is
> over, it should be unthinkable for a bystander to say, 'So what?'"*

The desired response is not "how interesting" but **"He did?"** — reportability.

### Hühn / Schmid — EVENTFULNESS: when a change is worth telling

Narratology distinguishes **Event I** (any represented change of state) from **Event II**
(a change that is actually tellable). Event II requires five things:

1. **Relevance** — significance in the represented world
2. **Unpredictability** — deviation from what is expected
3. **Effect** — consequences of the change *for the character*
4. **Irreversibility** — persistence, irrevocability
5. **Non-iterativity** — singularity; it happened once, not routinely

Note that eventfulness is explicitly **interpretive and context-dependent** — a
hermeneutic category, not an objective one. That is a warning about any detector we
build: it will be a judgement, and it will need calibration, not a proof.

---

## 2. What this decides about Michael's two definitions

They are **not two rival definitions of one thing.** They answer different questions, and
no encyclopedia treats them as alternatives.

| Michael's formulation | What it actually is |
|---|---|
| **The scanner bar** — three consecutive sentences about ONE person, with an action and something at stake | **A story.** It is Prince's minimal story (agent + action + change) plus Labov's evaluation (the stakes = the "so what"). |
| **Step 3** — *"connecting a fact with the stop, with the exhibition, with the museum, with the city, with the country"* | **Not a story. It is RELEVANCE.** A chain of associations has no agent, no change of state, and no causality. On Forster's test it does not even reach *story*, let alone *plot* — it is a set of facts arranged by topic, not by time or cause. |

A sentence each about the publisher, the printer and the donor satisfies step 3
completely, and it is what Labov's bystander answers "so what?" to. The detector was
right to call it a list of credits.

**Neither is wrong — they are both needed, at different points.** Step 3's chain is what
makes a story *belong in this room*; without it we tell a good story about something the
visitor is not looking at. The scanner bar is what makes it *a story at all*. Relevance
without narrativity is a catalogue entry. Narrativity without relevance is a podcast.

**Proposed ruling: the scanner bar defines "story"; step 3 defines "which story to
tell."** They are sequential filters, not competitors — and the current failure is not
that we chose wrong, but that we have been asking the retrieval layer for relevance and
then asking the prompt for narrativity, which it cannot manufacture without inventing.

---

## 3. What it changes in the code — the part that is not philosophy

### Prince gives retrieval a query shape it does not currently have

Every retrieval query we issue is **topical** — it asks for material *about* an object.
Prince's structure says the unit we need is a **change of state with an agent**. Those
are different searches, and the second one has lexical signatures the first does not use:
*refused, destroyed, banned, seized, fled, lost, bought back, hid, forged, contested,
returned, only survived, was never, until*.

The claim in the 2026-08-19 evaluation — *"there are no stakes in the retrieved material
for any stop"* — needs restating precisely: **we never asked for them.**

### The unglossed-reference gate destroys minimal stories by construction

Stop 1 of `TOUR_MFA_RELEASE_20260819_0115.txt` had all three of Prince's events:

> Fridman collected this work → he gave it to the MFA → it is public.

The gate degraded *Boris Fridman* out of his own sentence, leaving *"The generous gift of
this work to the museum further enriches the collection."* That deletes **the agent of
the middle, active event** — the only one of the three that cannot be stated without a
person. State, action, state becomes state, state, state, which is Prince's definition of
**not a story**.

The gate was right that he was unexplained. Deleting him was the wrong repair; glossing
him was the right one. This is a concrete, testable defect, and it is the same shape as
the passive-voice problem in the same evaluation (*"was posthumously realized"*, *"was
instrumental in bringing"*) — **the actor is being removed from the active event.**

### Hühn gives the detector five criteria instead of one

The current detector asks one question — is something at stake? Hühn's five (relevance,
unpredictability, effect on the character, irreversibility, non-iterativity) are each
separately checkable and would say *why* a stop failed rather than only *that* it did.
Non-iterativity alone would reject most of what we currently retrieve: *"the press
published many editions"* is iterative and therefore not an event.

---

## Sources

- [Britannica — Plot](https://www.britannica.com/art/plot)
- [Wikipedia — Narrative](https://en.wikipedia.org/wiki/Narrative)
- [Wikipedia — Plot (narrative)](https://en.wikipedia.org/wiki/Plot_(narrative))
- [The Living Handbook of Narratology — Event and Eventfulness](https://www-archiv.fdm.uni-hamburg.de/lhn/node/39.html) (Prince's minimal story; Hühn/Schmid's five criteria)
- [Labov — A Structural Analysis of Narrative](https://cle.ens-lyon.fr/anglais/fichiers/william-labov-a-structural-analysis-of-narrative-mode-de-compatibilite-769-_1366115192183-pdf)
- [Gerald Prince — *Narratology: The Form and Functioning of Narrative*](https://books.google.com/books/about/Narratology.html?id=tnzKglLMBrgC)
