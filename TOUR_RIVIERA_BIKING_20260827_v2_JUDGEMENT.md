# Judgement — French Riviera biking tour v2, 5 stops, build `87c091f` (D536)

**2026-08-27.** Tour: `TOUR_RIVIERA_BIKING_20260827_v2.md`.
Requested: 5 stops. **Delivered: 5.**

---

## Verdict: acceptable, and a different tour from the one you rejected

| | before (`18fcd07`) | now (`87c091f`) |
|---|---|---|
| Stops delivered / requested | **2 / 5** | **5 / 5** |
| Stops with independent evidence | 3 of 5, gate ignored | **5 of 5 (100%)** |
| Your requested Hippodrome | **absent** | **present, stop 4** |
| Stops that were plausibly invented | 4 of 5 | **0** |
| Words | ~684 | **1,395** |
| Cost / time | $0.1244 · 3m37s | $0.2021 · 4m02s |

**The route:** Cap d'Ail → Monaco → Èze Village → **Hippodrome de la Côte d'Azur** →
Saint-Jean-Cap-Ferrat. 81 km, within the 120 km cycling limit. These are real Riviera
destinations, all verified, and the tour reads as a coastal ride rather than a tour of
racecourses that mostly do not exist.

## Your confirmation question, answered with evidence

**Mostly yes, and I found the one place where it was not true.** I checked the previous biking
run's log rather than assuming. These already ran on a biking tour:

```
[D534] No cross-stop repetition in the drafts            ← semantic + fact repetition
[D533] No cross-stop fact repetition detected
[D533] Person-year role guard: no mismatches             ← the birth-year fabrication guard
[D534] 2 thin enough for another story (floor=300w)      ← the size trigger
```

**The exception was mine.** The two rules I wrote yesterday from your review — *acknowledge a stop
the listener already visited* and *don't claim importance without saying what changed* — I put
inside `if tour_category == 'museum':`. They could never reach a walking, biking or dining tour.
Lifted out; both prompt branches carry them now.

The only thing still museum-only is D532's exhibition scope veto and its disclosure, and that is
correct — it is about a museum's published checklist, which has no meaning for a bike ride.

## What the five fixes actually did

**1. Intent sees your original sentence.** Previously `[BLOCKER1]` stripped "tour", `[LOCAL-46]`
stripped "Biking", and `tour_type='biking'` was suppressed — then the *stripped* string was used to
ask what the tour is about. It answered `poi_type: "horse racing tracks"`. Now:

```
poi_type: "Biking tour with a stop at Hippodrome de la Cote d'Azur"
```

**That single change is responsible for most of the improvement.** The strippers still do their
real job — area resolution — on their own copy.

**2. The waypoint is no longer the boundary.** `PHASE 5.6` previously removed three stops for being
"outside 'Hippodrome de la Cote d'Azur'". Every removal was correct; a racecourse is not inside
another racecourse. The check was right and the scope was wrong.

**3. And then it went missing — caught before you saw it.** Refusing the waypoint as a scope
produced the opposite failure: the next run delivered five real destinations and **not** the
Hippodrome. The word appeared twice, both times in the echoed title. Two causes: the existing
user-explicit protection requires the plural `"stops at"` and you wrote `"a stop at"`, so it never
fired; and it only *protects* a stop already present. `named_waypoints()` now does three jobs —
refuse as scope, **insert if missing**, protect from the address and distance gates.

**4. The shortfall notice fires on every path.** `[D536] Listener asked for 5 stop(s), delivering
5 — request met`. Previously the only stop-count line was `LOCAL-394`'s
`OK (2 selected == 2 delivered)` on a tour that had lost 60% of its stops.

**5. GEO-CHECK reports the real mode and limit** — `within cycling distance … limit 120 km`
instead of `within walking distance` on a bike tour.

---

## Defects that remain

**1. Banned phrases survive outside stop descriptions.** Three FORBIDDEN_PHRASES entries shipped:

> "…**stands as a testament** to this region's rich history…" (stop 1 orientation)
> "Enjoy the **breathtaking views** of the Mediterranean…" (a Directions line)
> "the lighthouse **stands as a timeless beacon** for sailors" (closing recap)

`LOCAL-192` retried 13 paragraphs and fixed 10 — **it runs on stop descriptions only.**
Orientations, Directions and the closing recap are unfiltered. This is the same shape as the
museum-only prompt rules: a good check wired to one part of the artifact.

**2. The route order is inefficient.** Cap d'Ail → Monaco → Èze → **Cagnes-sur-Mer** →
Saint-Jean-Cap-Ferrat sends you ~30 km west to the Hippodrome and then back east. Max leg 39.23 km
of an 81 km total. The GEO-CHECK validates total distance and outliers, not sequence. For a
cycling tour the ordering is a real usability matter, not cosmetic.

**3. "Starting from Nice" is not honoured.** You asked to start from Nice; stop 1 is Cap d'Ail.
Nice appears only in the Directions ("Head southeast on Promenade des Anglais"). An origin named in
the request should either be stop 1 or be explicitly framed as the departure point.

**4. Stop 1's orientation previews stop 2's content** — the Monaco population statistic is
delivered before the listener has left Cap d'Ail. You asked to keep previews, so this is not a
request to remove it; but a preview should name what is coming, not spend its facts.

**5. Èze Village is 217 words**, under the 300 floor. The thin trigger fired on all five stops;
four improved, one kept its original.

## Recommendation

**Accept the tour.** It answers the request, every stop is real and verified, and the stop you
named is in it.

Next, in order: run the phrase filter over orientations, directions and the recap (defect 1);
honour a stated origin (defect 3); then route ordering (defect 2), which is the one that costs a
cyclist actual kilometres.

**One process note.** Three times today a fix opened the opposite failure — the repetition guard
that broke coherence, the fallback flag that produced a false disclosure, and the waypoint rescued
from being a boundary and then left out of the tour. **All three were caught by running the thing
and reading the output. The test suites were green every time.**
