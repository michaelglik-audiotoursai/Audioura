# Judgement — Restaurant tour in Monaco, 3 of 3 (D545)

**2026-08-28.** Tour: `TOUR_MONACO_RESTAURANT_20260828_v3.md`.
**Le Louis XV – Alain Ducasse · Café de Paris Monte-Carlo · Le Grill.** 833 words.

---

## Michael's three demands, answered

| his ask | result |
|---|---|
| **3 stops, not 2** | ✅ **3 delivered.** `Listener asked for 3 stop(s), delivering 3 — request met` |
| **People, not just facts** | ⚠️ **2 of 3 stops.** Stop 3 has a chef and a festival, no episode |
| **No dead restaurants** | ✅ **three were proposed, all three refused** |

**On the "terrible bug" — he was right and my recommendation to ship was wrong.** Dropping a dead
restaurant is correct; delivering 2 of 3 because of it is not, and the shortfall notice does not
discharge it. Monaco has hundreds of restaurants. Replenishment now proposes more, vets each
through **the same corpus and closure checks** that removed the original, and appends until the
count is met.

**It refused a dead venue mid-replenishment**, which is the part that matters:

```
[D545]   ADDED 'Café de Paris Monte-Carlo'
[D545]   rejected 'La Marée' — recorded in known_closed_venues.json
[D545]   ADDED 'Le Grill'
```

Three dead restaurants were proposed across this run — Robuchon, Vistamar, La Marée — and none
reached the listener.

## The people stories — his Gemini answer as the specification

**Stop 1, Le Louis XV:**
> *"Le Louis XV is the flagship restaurant of the renowned chef Alain Ducasse, who opened its doors
> in May 1987. At just 33 years old, Ducasse accomplished this feat, responding to a challenge…"*

**Stop 2, Café de Paris — the best stop in the tour:**
> *"Founded in January 1868 by François Blanc, who also established the Hôtel de Paris…"*
> *"In 1896, it became famous for hosting the Prince of Wales, the future Edward VII…"*
> *"On 21 July 1988, Prince Rainier, ruler of Monaco from 1949 to 2005, inaugurated the newest
> iteration of the café…"*
> …and the crêpe Suzette was invented there.

Named people, dates, consequences. That is the register he asked for, and it did not exist in any
restaurant tour before today.

**Stop 3, Le Grill — this is the honest shortfall.** Its three retrieved facts were: the eighth
floor of a hotel that opened in 1864, Chef Dominique Lory's approach to seasonal ingredients, and a
festival appearance. **A location, a person and an event — but no episode.** Nobody does anything
with a consequence. The story gate agrees: `story_units=0`.

Worse, the detail that made Le Grill worth proposing — **its retractable roof, cited in the
proposal itself** — appears **nowhere in the tour** (`retractable: 0 occurrences`). The
replenishment step knew why the stop was interesting and that reason did not survive into the
narration.

## What it took to get here, recorded plainly

Michael found **three dead restaurants** in tours I handed him. The last one, Joël Robuchon, I had
recorded as a *suspicion* — `expect: "verify"` — and never settled. It shipped again. Confirmed
today: the brand partnership ended in 2020, and in June 2023 the room reopened as **Les
Ambassadeurs by Christophe Cussac**. Promoted to `closed`, and the corpus rule amended: **a
`verify` entry is a task, not a resting state.**

**And the run before this delivered 1 stop because of my own carelessness:**

```
[D538] Restaurant practicals error (non-fatal): name 'propose_replacements' is not defined
```

I edited an import with a `str.replace()` and did not assert it matched. It no-op'd silently, the
exception aborted the whole block, and neither replenishment nor the lore fetch ran. **Eighth
wiring failure of the day, and the only one that was plain sloppiness.** The `non-fatal`
try/except turned a hard failure into a log line nobody would look for.

**One run was also lost to intermittent DNS on this Mac** — `api.openai.com` failing to resolve for
Python and curl while `nslookup` succeeded and other hosts were fine. Environmental, not code;
recorded so it is not mistaken for a defect later.

## Defects remaining

1. **Le Grill has no story** — 1 of 3 stops passes the story gate. The lore call returned facts, not
   episodes, for this venue. **The `why` from the replenishment proposal should be carried into the
   stop's material** — it is the one place the system already knew what made the place interesting.
2. **`story_units` 1/3** — the standing ceiling on every path, unchanged.
3. **Café de Paris is 205 words**, under the 300 floor, despite being the richest stop.
4. **The `crêpe Suzette` detail leaks across stops** — it appears in all three, including the recap.

## Recommendation

**Ship this one.** It answers the request: three stops, three refused dead venues, practicals
spoken, and two stops carrying real people-and-date stories.

**Next, in order:** carry the replenishment `why` into the stop material (small, and it fixes Le
Grill directly); then `story_units`; then the five museum-gated checks.

**And the standard, restated because today proved it eight times:** before calling a guard done,
not *"do the tests pass"* but **"show the line in a real run where it fired."** Every failure today
was correct code running nowhere that mattered.
