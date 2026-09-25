# Round 9 — LEAD's own read, written BEFORE the critiques returned

Written 2026-09-23 20:2x, after reading both round-9 files in full and before
`CRITIQUE_ROUND9_FACTS.md` (LOCAL-534) or `CRITIQUE_ROUND9_COHERENCE.md`
(LOCAL-535) existed. The point of writing it first is that a critique cannot then
be graded against nothing: Michael's rule is that critiques are claims, not facts,
and two have already been wrong. This is the baseline they get compared to.

**Both tours score `defects: {}` — CLEAN — in `ROUND9_SUMMARY.json`.**
Everything below is in a tour the instrument called clean.

Every finding is **READ** (the words are in the file) or **VERIFIED** (I ran the
code and can show the output).

---

## 1. The headline: LOCAL-527 cannot see round 9's fabrications — VERIFIED

LOCAL-527 was merged at 19:21 specifically to gate fabricated builder/founder
attribution. Round 9 generated at 20:10. The same two fabrications are present and
the gate returns nothing:

```
$ python3 -c "... tq._find_fabricated_attributions(tour)"
CHURCH_1 fabricated_attribution frames: []
LOGAN_1  fabricated_attribution frames: []
```

It is not broken. It fires perfectly on the round-7/8 sentences it was written
against:

```
"The airport was constructed in 1887-1889 by Gustave Eiffel."
   -> [('unverified', 'constructed', '1887', 'Gustave Eiffel')]
"Founded in 1868 by St. Mary Help of Christians."
   -> [('dedication', 'Founded', '1868', 'Mary Help of Christians')]
```

**The fabrication did not stop. It changed grammatical shape.** The gate requires
`<built|constructed|founded|established|erected> in <YEAR> by <NAME>`. Round 9 says:

- LOGAN_1 orientation: *"**Gustave Eiffel's iconic Control Tower** mark the endpoints"*
  — possessive. No verb, no year, no "by". Invisible to the pattern.
- CHURCH_1 orientation: *"**Designed by Jean Bazaine**, the stained-glass windows
  depicting the sacraments"* — `designed` is deliberately excluded from the verb
  list so real art attributions survive, and there is no year.

Both confirmed by running the function on those exact strings: `[]`.

**This is the lesson, and it is bigger than one gate.** Every fix of this class so
far matches a surface form. The generator is not constrained to the surface form.
A gate written against last round's sentence is a gate the next round walks around.

## 2. Gustave Eiffel is refuted three stops later by the tour itself — READ

No outside knowledge is needed for this one, which makes it the highest-confidence
finding in the batch:

- Stop 1 orientation: *"Gustave Eiffel's iconic Control Tower"*
- Stop 3 body: *"Designed by the Boston architectural firms **Kubitz & Papi, Inc.
  and Desmond & Lord, Inc.**, this tower is a marvel of brutalist architecture"*

The tour states two different designers for the same structure, 4,000 characters
apart, and nothing compares them. The second is correct; Eiffel died in 1923.

## 3. A Sydney cathedral is announced as an endpoint of an airport tour — READ

LOGAN_1 stop-1 orientation, verbatim:

> *"The tour spans from the bustling Terminal A Main Concourse to the efficient
> Terminal A Baggage Claim, all within the same building. **St. Mary's Cathedral,
> dedicated by pioneer priest Fr John Therry**, and Gustave Eiffel's iconic Control
> Tower mark the endpoints."*

Two sentences that contradict each other about what the endpoints are, and the
named endpoint is a building in Sydney, Australia — Fr John Therry is the priest
associated with St Mary's Cathedral there. Nothing in this tour is in Australia.

## 4. CHURCH_1 announces stained glass, then stop 2 says there is none — READ

- Orientation: *"Designed by Jean Bazaine, **the stained-glass windows depicting the
  sacraments shimmer** with spiritual significance."*
- Stop 2 is **titled** "Stained Glass Windows".
- Stop 2 body: *"**In the absence of stained glass**, we find the church's story told
  through different means… While the absence of stained glass might seem like a gap…"*

A stop exists, is named after a thing, and its own text says the thing is not there.
The stop-existence gate did not stop this, and the scorer called it clean.

## 5. The dangling-referent class (LOCAL-530) survives — READ

LOCAL-530 merged 19:21, round 9 at 20:10.

- CHURCH_1 stop 2: *"**This event**, deeply etched into the church's modern history,
  demonstrates that while the church may not hold stained glass windows…"* — no
  event has been mentioned. The referent does not exist anywhere in the stop.
- LOGAN_1 stop 3: *"**Trippe, the founder and later Pan American World Airways**,
  helped connect Boston to New York"* — the given name is gone (Juan Trippe) and
  "the founder" has lost its object. The sentence does not parse.

## 6. The epilogs describe tours that were not given — READ

- LOGAN_1 closes: *"That's 4 stops — Terminal A Main Concourse … and Control Tower …
  **This tour covered Control Tower and Terminal A Baggage Claim.**"* Four stops were
  delivered; the closing names two of them, twice, and omits the Jetbridge entirely.
- CHURCH_1 closes: *"That's 4 stops — **Mary Immaculate of Lourdes** showcases
  collaborative stained glass art and the nave at Boston Globe's Spotlight
  investigation site was crucial in 2002. This tour covered Altar and Narthex."*
  Mary Immaculate of Lourdes is a **different church** — the tour's own stop 2 says
  so explicitly ("A short distance away in Newton Upper Falls… another story…
  **due to frequent confusion**"). The epilog then adopts the confusion it warned about.

## 7. `named_people` is still wrong — READ

`ROUND9_SUMMARY.json` records `"named_people": 1` for LOGAN_1. The file names:
Fr John Therry, Gustave Eiffel, Edward Lawrence Logan, Trippe, Kubitz, Papi,
Desmond, Lord. That is at minimum four people and four surnames of firms.

D585 was "fixed after three wrong attempts". It is still undercounting by roughly
the same factor the round-7 critique found. **If this number is driving any triage,
it is pointing at the wrong files** — which is exactly what the round-7 critique
concluded, before the fix.

## 8. One unverifiable claim worth naming — INFERRED

CHURCH_1 stop 1 has Mother Teresa visiting in June 1995 and approaching *"a young
parishioner who had been paralyzed. With her gentle touch and whispered prayers,
she brought an air of hope"*. The 1995 visit appeared in round 7 as well. The
healing-scene framing is new, is exactly the kind of detail no source will support,
and `CHURCH_1_evidence.json` marks all four stops `"UNVERIFIED" / "not in discovered
landmarks"` — it carries no factual sourcing at all.

---

## What this says about where the work is

Items 5, 6 and 7 are deterministic and fixable the usual way. Items 1–4 are the
same single problem the handoff already named, and round 9 is evidence that the
per-defect gate strategy has reached its limit: **LOCAL-527 was written, merged,
and the very next generation produced the same falsehood in a form the gate cannot
match.** Writing LOCAL-536 against the possessive form invites round 10 to use an
appositive.

The one structural finding that does not depend on knowing anything about the world
is item 2 and item 4: **the tour contradicts itself inside its own text.** A check
that compares a tour's claims against its own other claims needs no corpus, no
grounded call, and no knowledge — and would have caught the Eiffel attribution, the
stained-glass void, and both epilogs. That is the cheapest real gate available and
it is not built.
