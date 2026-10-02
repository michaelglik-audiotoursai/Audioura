# Judgement — Restaurant tour in Monaco, the stories land (D550)

**2026-08-29.** Tour: `TOUR_MONACO_RESTAURANT_20260829_v3.md`.
**Le Louis XV – Alain Ducasse · Le Grill · Café de Paris Monte-Carlo.** 995 words.

---

## The blocker is cleared

Michael's release condition: *"The major thing to fix is to add stories about people; without them
we can not go to release and mobile testing."*

| stop | hours | booking | price | cuisine | the story |
|---|---|---|---|---|---|
| Le Louis XV | ✅ | ✅ | ✅ | ✅ | Ducasse summoned in May 1987 to transform the dining room |
| Le Grill | ✅ | ✅ | ✅ | ✅ | **31 May 1959** — inaugurated by Rainier III and Grace, with **Aristotle Onassis and Tina Livanos** |
| Café de Paris | ✅ | ✅ | ✅ | ✅ | **Crêpe Suzette, 1896**, from a dessert accident involving the Prince of Wales · **Diaghilev's Ballets Russes**, Nijinsky and Karsavina |

**All four practical facts on all three stops. A named person and a date in all three. Story gate
2 of 3**, the best on any path in this project's history.

All three lore calls came back `via gemini` — 7, 8 and 4 facts.

## The answer to "why??", in full

Michael asked the same question four times before it was properly answered. Four causes, discovered
in this order, each hiding the next:

**1. We were asking Gemini about a museum object.** `_gemini_facts()` hardcoded the museum prompt
and the `Object:` / `Museum:` framing for every stop.

**2. Retrieved episodes were offered as context, never required.** They entered as search snippets
where the ranker can score them `usable=0`; the prompt called them "reference material".

**3. Gemini had never once run inside the container.** `story_leads.py` opened `.env`
unconditionally at module import; `.env` is in `.dockerignore`, so the import raised
`FileNotFoundError` and every caller's `try/except` swallowed it. **Every host test I ran passed
against a code path that did not exist in production.**

**4. And the one Michael found himself: I never asked his question.** I sent an instruction block
ending in `Return ONLY JSON`. Measured, same model, same restaurant, same day:

> **My prompt:** *"Chef Dominique Lory crafts a refined menu… Ducasse began at Pavillon Landais in
> 1972."*
>
> **His phrasing:** *"The sliding roof retracts in under three minutes. When it debuted on 31 May
> 1959, Prince Rainier III and Princess Grace cut the ribbon… Aristotle Onassis, majority
> shareholder of the SBM and often at odds with Rainier over control of Monaco, pushed to build the
> most extravagant rooftop in the Mediterranean to woo Maria Callas."*

**The engineering was suppressing the material.** A wall of rules plus a JSON schema makes the
model cautious and list-shaped. A short natural question with an honesty caveat lets it tell what
it knows. I had assumed more instruction meant better output; the measurement says the opposite,
and that assumption cost several iterations.

The fix keeps his accuracy caveat intact: ask in his words, take the prose, and structure it in a
second pass that is **forbidden to add anything the prose does not contain** — hedges like
*"reportedly"* and *"legend has it"* are preserved rather than promoted to fact.

## Remaining, none blocking

1. **Story gate 2 of 3** — Le Grill has the 1959 inauguration but the prose does not build it into
   a three-sentence arc with a consequence.
2. **`closure_scan` is the weakest component in the system** — three false positives this week
   (La Salière on a snippet about Naples, Florida; Café de Paris once) against zero true positives
   the corpus lookup had not already caught. **Demote it to advisory.** It did not misfire here.
3. **Replenished stops arrive thinner** than originally-selected ones — they get practicals and
   lore but not the corpus and fact-sheet material.

## Recommendation

**Ready for the mobile test.**

Set the app's server IP to **`192.168.0.136`**, and request a location you have not generated —
`tour_cache` is keyed on (location, type, stop count) and will answer from cache rather than
exercising the pipeline.

## For Subscribed

**Eleven failures this week, one shape: correct code running nowhere that mattered.** Museum-gated
blocks, a data file that never entered the image, a city compared by equality, an import that never
applied, an edit that deleted a function, a module that died on import in the container — and a
prompt so over-specified it suppressed the answer.

**Every one was hidden by a `try/except` that turned a hard failure into a silent downgrade, and
every one was found by reading tour output rather than by a green suite.** Two practices carry
forward: **run it in the container it ships to and show the log line where the code fired**, and
**when a human gets a better answer than the system, compare the two prompts before assuming the
system needs more logic.**
