# Judgement — French Riviera biking v3, and an honest report on the story work

**2026-08-27**, build `043748f`. Tour: `TOUR_RIVIERA_BIKING_20260827_v3.md`.

---

## The headline: I took the risk you flagged, and you were right to flag it

You asked me to judge whether adding stories would improve the tour or damage what we had. **I
judged it safe, and two of the three things I did were wrong.** Both are reverted. The tour above
is good — better than v2 on route — but **the story improvement you actually asked for did not
land**, and I am not going to present run-to-run noise as a result.

## What this tour is

| | v2 (you accepted) | **v3 (this one)** |
|---|---|---|
| Stops delivered / requested | 5 / 5 | **5 / 5** |
| Existence-verified | 5 / 5 | **5 / 5** |
| Your Hippodrome | present | **present (stop 5)** |
| Route total | 81 km | **39 km** |
| Longest leg | 39 km | **24.7 km** |
| Words | 1,395 | 1,387 |
| Story-gate passes | *not measured* | **0 / 5** |

**Route:** Villa Ephrussi → Cap d'Ail Beach → Monaco Grand Prix Circuit → Saint-Paul-de-Vence →
Hippodrome. That is a genuinely better ride than v2 — half the distance, no 39 km leg, and
Saint-Paul-de-Vence and the Monaco circuit are strong stops.

## The story work: what happened, measured

**First, a correction.** I told you the story bias caused a bad stop selection. **It did not.** The
gesture rule edits the *description* prompt, the place-focused retrieval runs *after* selection,
and the story-gate change is informational. None touch selection. The Phase 3A call is **unseeded**
— three runs of the identical string gave three completely different stop sets before any of this
existed. I asserted causation I could not support.

**Second, the results, across four runs on the same request:**

| run | story-gate passes | note |
|---|---|---|
| before D537 | *never measured* | the gate was museum-only |
| D537 run 1 | 1 / 5 | |
| D537 run 2 | 2 / 5 | |
| **this run** | **0 / 5** | |

**That spread is noise, not improvement.** I cannot claim the story work raised story quality; the
honest reading is that it did not measurably move it. What it *did* do:

- **The story gate now runs on every tour type.** Before today a biking tour's stories were never
  measured at all — which is exactly why your "needs a story or two" had no number behind it. That
  is a real gain and it is why I can tell you 0/5 instead of guessing.
- **Concrete dates rose** — 1907, 1912, 1929, 1938, 1960, 1964, 1987, 1996 appear in this tour.
- **The place-focused retrieval works in isolation** — asked about Saint-Jean-Cap-Ferrat it returned
  Duke Emmanuel Philibert's 1561 fort at Saint-Hospice, Cocteau, and the Hippodrome's 1928 founding.
  The material is reachable; the narration is not reliably using it.

## The two mistakes, both reverted

**1. I told the system a bicycle is an unusual vehicle.** Seeing an earlier run route you onto
Île Sainte-Marguerite — a ferry-only island — and then instruct you to *"pedal off from Île
Sainte-Marguerite … towards Cannes"*, I added `bike` to the reachability check, reasoning it was
advisory so it "could only flag an impossible stop, never delete a good one."

**That reasoning was wrong.** Advisory means it keeps stops when the CALL FAILS — not when the call
answers confidently and wrongly. The next run excluded as unreachable by bicycle:

```
Hippodrome de la Cote d'Azur   ← the one place you asked for by name
Fort Carré                     ← on the Antibes seafront
Promenade du Paillon           ← a park in central Nice
```

…and **kept the island.** The check is tuned for "can a dogsled get here", where the answer is
nearly always no. Reverted.

**2. Kept from that failure, because it is correct:** a stop **you named** is now immune to the
reachability check. It had overridden D536's insertion and deleted your Hippodrome. That guard is
right for animal tours too.

## Defects that remain in this tour

1. **Three banned phrases shipped** — *"deep connection to"*, *"transcends time"*,
   *"breathtaking view"*. This is the known gap I reported yesterday and did not fix:
   **`LOCAL-192` runs on stop descriptions only**, so orientations, Directions lines and the closing
   recap are unfiltered. It is a one-place fix and it is the cheapest remaining win.
2. **One gesture survived** — *"rich history"*. The D537 rule reduced these but does not eliminate
   them.
3. **Cap d'Ail Beach is 147 words**, well under the 300 floor — the thinnest stop in any tour today.
4. **"Starting from Nice" is still not honoured** — the tour opens at Villa Ephrussi.

## Recommendation

**Either tour is shippable. If you want one sentence: ship this v3** — same content quality, half
the cycling distance, your Hippodrome present, nothing requiring a boat.

**On D537: keep it, but do not count on it.** It is gated away from the museum path, so the Palais
tour cannot regress from it, and the story gate it enabled is how we will measure any future
attempt. But it did not deliver the stories you asked for, and the real fix — getting retrieved
episodes into the narration rather than merely fetching them — is post-release work.

**Process note, and it is the fourth instance today.** Every fix I made opened its own opposite
failure: the repetition guard broke coherence; the fallback flag produced a false disclosure; the
waypoint was rescued from being a boundary and then dropped from the tour; and the reachability
check deleted three reachable stops while keeping an island. **All four were caught by running the
thing and reading the output. The test suites were green every time.**
