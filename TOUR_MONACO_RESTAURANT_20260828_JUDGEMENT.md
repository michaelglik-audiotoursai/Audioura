# Judgement — Restaurant tour in Monaco, build `f7f1284`

**2026-08-28.** Tour: `TOUR_MONACO_RESTAURANT_20260828.md`. **3 requested, 2 delivered.**

---

## Verdict: accept the tour; distrust most of the machinery that produced it

**Le Louis XV – Alain Ducasse à l'Hôtel de Paris · La Montgolfière.**

| | |
|---|---|
| Delivered / requested | **2 / 3** — announced, not silent |
| Known-bad venues present | **none** — verified in the delivered text, not the log |
| Story gate | **2 of 2 PASS** — the best ratio of the week, on any path |
| Practicals in the narration | ✅ price, booking, hours, closed days |
| Words | 776 (371 / 405) |

Both stops pass the story gate — Le Louis XV and La Montgolfière each carry a named person, real
actions and an arc. For comparison: 0/5 on the biking tour, 1/3 on the museum tour at its best.

The listener is told what they need: *"The Gourmet Menu is priced at 360 EUR"*, *"a reservation is
essential"*, *"Open from 12:00 to 13:30 and again from 19:30 to 21:00, closed on Wednesdays and
Sundays."*

---

## What this cost, and what it actually proved

You found **two dead restaurants in tours I handed you** — La Marée (closed 2020) and Le Vistamar
(replaced by Pavyllon in 2022). Fixing that took **seven attempts**, and I want the record straight
about which of them worked.

**Le Vistamar shipped three separate times after I told you it was handled:**

1. The rebrand check didn't exist yet — it only knew the word "closed".
2. The Gemini check was probabilistic and returned "operating" that run.
3. The corpus lookup was correct but compared cities by **equality**, and production passes
   `"Restaurant tour in Monaco"`, not `"Monaco"`. Every entry was skipped.

**And two of my fixes did more damage than the defect:**

- The rebrand markers **dropped all three restaurants and crashed the run**
  (`max_workers must be greater than 0`), acting on *"Built by Louis XIII back in 1623, the estate
  is now home to…"*.
- `closure_scan` **deleted an open Monaco restaurant** on a Florida snippet: *"The Bevy in Old
  Naples permanently closed… a new concept, La Salière Naples, will open in its place."*

## What is actually reliable, ranked honestly

1. **The known-closed corpus.** Deterministic, zero cost, and the only part that has never been
   wrong. It is what removed La Marée in this run.
2. **The practicals acquisition** (SERP → OpenAI). Solid, and the finding that mattered was
   mundane: searching the compound name `"Le Louis XV - Alain Ducasse à l'Hôtel de Paris"` returned
   **3 snippets**; the house name alone returned **33**.
3. **The Gemini operating check.** Probabilistic. Right most times, and it let Le Vistamar through
   twice. Useful, not trustworthy alone.
4. **Keyword marker paths.** Structurally unsound — both of them bound a marker to the wrong
   subject. The rebrand path is removed; the closure path now requires the city in the snippet and
   should still be regarded as the weakest link.

**The honest summary is narrower than "we validate stops now": a human-curated list protects
listeners, and everything automated around it is an assist.**

## Defects remaining in this tour

1. **`LOCAL-36` fires a false alarm.** It prints
   `⚠️ NO PRACTICAL CLAIMS FOUND TO VERIFY — and this is a RESTAURANT tour` **while the tour
   contains price, booking and hours.** The D538 warning I added is correct in principle; the gate
   it wraps looks for claims against the venue's own page, and these came from search. **The
   acquisition and verification halves do not share a source**, so the warning cannot see the facts
   that are there. It is now crying wolf — worse than the silence it replaced.
2. **A garbled sentence:** *"The Gourmet Menu is priced at 360 EUR, while menu is 240 EUR."* A menu
   name was dropped mid-sentence.
3. **2 stops, not 3.** Dropping is subtractive; nothing refills. The shortfall is announced, which
   is right, but a restaurant tour that loses a third of itself to a correct drop still
   under-delivers. **Replenishment is the highest-value next item on this path.**
4. **`La Montgolfière` lost an attributed quote** — `DROPPED attributed quote 'Chef Henri' — no
   primary source`. The guard worked; the stop is thinner for it.

## Recommendation

**Ship it.** Then, in order, post-release: replenishment after a drop; make `LOCAL-36` and the
acquisition share a source so the warning stops crying wolf; then `story_units`, which this tour
happens to pass but which remains 0–1 of N everywhere else.

**And one process change I would make about myself.** Seven wiring failures today — five
museum-gated checks, a data file that never entered the image, and a city comparison that never
matched — all had the same shape: **the code was right and it ran nowhere that mattered.** Every
one was caught by reading tour output, never by a green suite. Before calling any future guard
done, the check is not "do the tests pass" but **"show the line in a real run where it fired."**
