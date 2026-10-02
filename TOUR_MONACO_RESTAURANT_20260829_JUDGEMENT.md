# Judgement — Restaurant tour in Monaco, 3 of 3 (D546/D547)

**2026-08-29.** Tour: `TOUR_MONACO_RESTAURANT_20260829.md`.
**Le Louis XV – Alain Ducasse · Le Grill · Elsa.** 680 words.

---

## Michael's four facts — the ask

> *"days and hours, is reservation required, the price of an average entrée or how much one should
> expect to pay for lunch and dinner (any one is enough) and type of food"*

| stop | hours | booking | price | cuisine |
|---|---|---|---|---|
| Le Louis XV | ✅ | ❌ | ✅ | ✅ |
| Le Grill | ✅ | ❌ | ✅ | ✅ |
| **Elsa** | ✅ | ✅ | ✅ | ✅ |

**One stop of three has all four.** Two omit the booking requirement — and for Le Louis XV that is
the one a listener most needs, since the acquired data says *"reservation required; walk-ins are
not realistic and tables can book out weeks or months"*. **The data was fetched and the narration
dropped it.**

The prompt now says all four are mandatory when present, which is why Elsa carries them. It is not
yet reliable across all stops, and I am not going to claim otherwise on a 1-of-3 result.

**Elsa is the proof the design works when it lands:**

> *"Elsa opens its doors from Tuesday to Saturday, from 19:15 to 21:30. Reservations are essential,
> and the tasting menu is priced around 138 EUR, offering a taste of its organic Mediterranean
> delights."*
> …Marcel Ravin, who hosted a Four-Hands Dinner with Domenico D'Antonio and Christopher Coutanceau.

Hours, booking, price, cuisine, and a named-people story, in prose, in one stop.

## What is fixed and verified

**No dead venue anywhere, including the opening.** The previous tour's prolog advertised
*"La Marée's Russian-inspired concept"* — a restaurant closed since 2020 that the system had
correctly dropped from the stops. The corpus check now runs **before the spine is written**, so
the tour cannot describe a venue it will not visit. Robuchon and Le Vistamar were both removed
pre-spine this run.

**Four dead-or-rejected venues kept out, and the count still met** — Robuchon, Le Vistamar,
La Marée, plus one more, with Le Grill and Elsa replacing them.

## The three defects, in the order I would fix them

**1. `closure_scan` rejected Café de Paris Monte-Carlo as permanently closed. It is open.**
Michael's own Gemini answer has it open daily 8:00–1:00. **That is the third false positive from
this path** — La Salière (a Florida snippet), and now this. The corpus lookup and the Gemini check
have never produced one; the keyword scan has produced three. **It should be demoted to advisory
or removed.** Nothing in this session has been more consistently wrong.

**2. Two stops are thin — Le Grill 144 words, Elsa 119.** Both are replenishment additions, and
they arrive without the corpus and fact-sheet material an originally-selected stop gets. They carry
practicals and lore and little else. Total tour 680 words against 1,060 in the previous version.

**3. Elsa opens mid-thought:** *"Position yourself to best view this location. **This achievement**
was realized under the culinary mastery of Marcel Ravin…"* — a placeholder orientation followed by
a dangling demonstrative. Replenished stops skip the orientation generation the original stops get.

## What this cost, recorded honestly

Reaching this took **nine wiring failures across two days**, of which two were mine in this last
stretch alone:

- A `str.replace()` that matched nothing, so `propose_replacements` was never imported — the whole
  vetting block was skipped and the tour shipped with **no** protections while reporting success.
- An edit that sliced **to the end of the file** and deleted `propose_replacements` outright — the
  next run shipped **Le Vistamar and La Marée together**, both already in the corpus.

Both were unguarded string edits. The third attempt asserted its anchor appeared exactly once,
found two, and **wrote nothing** — the guard working. That assertion is the practice going forward.

**And the `try/except ImportError` around the vetting block is dangerous.** Twice it turned a total
failure into a log line and let an unvetted tour ship as if fine. For a restaurant tour, a missing
`restaurant_practicals` should fail the generation, not degrade silently.

## Recommendation

**Do not treat this as ready for mobile testing yet.** It is close, and the remaining items are
small, but one of them actively rejects real restaurants.

Before the phone test, in order:
1. **Demote `closure_scan`** — three false positives, zero true positives the corpus did not
   already catch.
2. **Give replenished stops the same orientation and material** as originally-selected ones —
   fixes both the thin stops and Elsa's dangling opener.
3. **Make the booking requirement as mandatory as the price** — the model is dropping it.

After that, the phone test: **server IP `192.168.0.136`**, and use a location you have not
generated, or the cache will answer instead of the pipeline.
