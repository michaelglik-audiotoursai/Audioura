# My judgement on "exhibition blue green and silva in MFA Boston, MA"

Companion to **`TOUR_MFA_BLUEGREEN_20260824_1606.md`**. One generation, no selection.

---

## 1. The finding, first

**There is no MFA Boston exhibition called "blue green and silva".** The system did not say so.
It produced a confident, fluent, 5,827-character tour of an exhibition that does not exist, built
from three unrelated works it chose itself, and told the listener things about them that are
false.

This is the most serious result of the day, and it is worth more than the Unbound tour. **A tour
that is wrong is worse than no tour**, because a listener standing in Gallery 332 has no way to
know. Everything I fixed today was about polish; this is about whether the product should have
spoken at all.

### What actually happened, from the log

1. **The venue resolved to the wrong museum, in the wrong city.**
   `[venue_resolver] Resolved: 'Museum of Fine Arts, Boston' → Q1565911 (Museum of Fine Arts,
   Houston)`, `URL: http://www.mfah.org/`. The request said Boston. The resolver returned Houston
   and the run continued.
2. **Nothing matched the exhibition.** `[LOCAL-212] Coverage selection: 0 COVERED, fallback
   needed: 1×VENUE_ONLY, 2×EMPTY`. The system knew it had no coverage for any candidate and
   proceeded anyway, choosing `The Great Good Man`, `That Red One` and `Autorretrato con espejo`
   — three works with nothing in common.
3. **`Knowledge validation passed`.** Twice. Whatever that gate is checking, it is not checking
   whether the requested subject exists.

---

## 2. What the tour tells a listener, and why each part is wrong

**The opening states the fiction as fact:**

> In Gallery 332, the exhibition "blue green and silva" at the MFA Boston invites you to explore
> the intricacies of identity through artistic expression.

**Then it misattributes its own first stop, in the same paragraph as the correct attribution.**
The heading says *The Great Good Man* **by Marsden Hartley**; the orientation says it is *"by
**Cyrus Edwin Dallin**"*. Both are in the tour. One of them is wrong.

**It describes two of three works as things they are not:**

> "That Red One" showcasing **Dutch Golden Age painting** — it is a 1944 Arthur Dove abstract.
> "Autorretrato con espejo" delving into **ancient Egyptian artifacts** — it is a Siqueiros
> self-portrait of 1937.

**Stop 3 hands a Siqueiros painting to George Gershwin.** Read the pronoun chain:

> David Alfaro Siqueiros completed this self-portrait in 1937. The composer George Gershwin… had
> left New York in 1936 and never returned… **His work, "Autorretrato con Espejo," exemplifies his
> ability to integrate political fervor into self-expression.**

By the third sentence "his" resolves to Gershwin. **And the closing recap propagates it** —
*"Autorretrato con espejo, painted after George Gershwin's departure from New York in 1936"* —
so the error is the last thing the listener hears.

**Donors are reduced to first names and presented as people:** *"Jessie, a notable benefactor"*,
*"John, a generous donor"*, *"James' donation"*. These are credit-line fragments, not names.

**Stop 2 leaks stop 3's artist into an invented relationship:** *"Siqueiros, who authored
illustrated texts, represents the kind of intellectual partnership…"* — in a stop about Arthur
Dove. This is the cross-stop contamination class, in a form my check (a) does not detect.

**And the *Unbound* thesis leaks into a tour that has nothing to do with books:** *"an exhibition
emphasising collaborative ventures in transforming the book as an art form"* — attached to a
self-portrait.

---

## 3. The one component that behaved honestly

**The story loop refused to publish on 2 of 3 stops**, and it refused for the right reason:

| stop | candidates examined | outcome |
|---|---|---|
| The Great Good Man | 35, 26, 5, 34 | **no story** — nothing reached the floor of 50 |
| That Red One | 34, 34, 34, 30 | **no story** |
| Autorretrato con espejo | 21, 48, 55, **65** | story at 65 |

When the subject is real, the loop finds material scoring 63–83 (the Unbound tour, same day, same
code). When the subject is fabricated, it finds 5, 21, 26, 30, 34, 34, 34, 35 — and declines.
**Your index floor is a working detector of "there is nothing here", and it is currently the only
part of the pipeline that noticed.**

The third stop also shows the D523 fix earning its keep in the hardest case: 21, 48, 55, 65 —
accept-first would have taken 55.

**Every defect check came back clean** — no bracketed citations, no repeated clause, no spoken
label, no missing space, no Treat Page. The tour is polished. It is polished nonsense, which is
precisely why polish was never the thing to measure.

---

## 4. What I think should happen, and it is a decision for you

The pipeline has no answer to "I do not know this." I would give it one, in this order:

1. **Fail the venue resolution loudly.** Boston resolving to Houston is a bug with a wrong answer,
   not a near-miss. A resolved venue whose city contradicts the request should abort the run.
2. **Make `0 COVERED` a stop condition, not a fallback.** `[LOCAL-212]` already knows it has no
   coverage for any candidate. Today it fills the gap with whatever the museum happens to own.
   The honest outcome is to return nothing and tell the app why.
3. **Reuse the index floor you already own.** The loop scored this subject 5–35 across eight
   candidates while scoring the real one 63–83. **A tour whose stops all score below 50 is a tour
   about nothing**, and that signal is already computed, already free, and currently only used
   per-story.

I have not implemented any of these, because refusing to generate a tour is a product decision
about what a paying user sees, and it is yours. The change is small; the consequence is that some
requests come back empty.

---

## 5. Two smaller things this tour surfaced

- **`"This particular piece is located within as part of an exhibition…"`** — another preposition
  whose object was stripped, in a shape my new check (i) does not match (it looks for a
  participle before the preposition; this has "located within as"). The class is real and my
  detector is still fitted to the one example I had.
- **`"the 20th-largest art museum in the world"`** — true, and it belongs to a museum that is not
  the one this tour resolved to.

---

## 6. Summary against the Unbound tour, same code, same hour

| | Unbound (real) | blue green and silva (not real) |
|---|---|---|
| stops with a gated story | 3 of 3 | **1 of 3** |
| candidate indices | 63–83 | **5–65, six of twelve below 35** |
| stop index mean | 73.0 | 57.0 |
| rubric base score | 75.0 | **75.0** |
| defect checks | 2 found | **0 found** |

**The rubric gives both tours 75.0 and the defect checker prefers the fictional one.** Neither
instrument can tell that one of these tours is about a real exhibition and the other is not. The
story loop's candidate indices can — that is the number to build the guard on.
