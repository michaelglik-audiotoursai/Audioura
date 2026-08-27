# Judgement — Restaurant tour in Monaco, 3 stops, build `043748f`

**2026-08-27.** Tour: `TOUR_MONACO_RESTAURANT_20260827.md`. Requested 3, delivered 3.
The last tour before mobile testing and the GCloud migration.

---

## Verdict: the best-written of the three paths, and the one with the most dangerous gap

**Le Louis XV – Alain Ducasse à l'Hôtel de Paris · Joël Robuchon Monte-Carlo · Cipriani Monte
Carlo.** All three are real Monaco establishments, all existence-verified, and the prose is the
strongest of anything generated today. Stop 1 is a genuine story:

> "Opened in May 1987, this restaurant was born from a challenge set by Prince Rainier III… three
> Michelin stars within four years…"

Named person, date, action, consequence. **The story gate passes it** — 1 of 3, the best ratio of
any non-museum tour today, against 0/5 on the biking tour.

| | |
|---|---|
| Delivered / requested | **3 / 3** |
| Existence-verified | **3 / 3 (100%)** |
| Story-gate passes | **1 / 3** |
| Cross-stop repetition | none |
| Banned phrases | **none** — the first tour today with zero |
| Words | 1,089 (466 / 253 / 370) |
| Cost / time | $0.1614 · 3m 03s |

---

## The two defects, and both are specific to restaurants

### 1. Zero practical facts, in the one category where they are the point

```
[LOCAL-36] PRACTICAL FACTS GATE: PASSED (0 verified)
```

**The gate passed because it verified nothing, not because everything checked out.** The tour
contains no opening hours, no prices, no booking requirement, no dress code, no closed days.

For a museum tour that is a nice-to-have. **For a restaurant tour it is the point.** A listener
standing outside Le Louis XV wants to know whether it is open tonight, whether they need to have
booked three weeks ago, and roughly what dinner costs. This tour tells them about Prince Rainier's
1987 challenge and nothing they can act on.

Note the shape: **a gate that reports PASSED on zero evidence.** That is the same failure family as
`LOCAL-394` reporting "Stop count invariant: OK" on a tour that had lost 60% of its stops, and as
the role guard that crashed and printed a non-fatal error while the tour completed normally. A
check that cannot distinguish "verified fine" from "verified nothing" is not a check.

### 2. One of the three restaurants may be closed — and nothing looks for that

**Joël Robuchon Monte-Carlo.** Joël Robuchon died in 2018, and the Hôtel Métropole's restaurant of
that name has, to my knowledge, since closed and been replaced. **I have not verified this and I am
not asserting it as fact** — but a tour that sends a listener to a restaurant that no longer exists
is worse than a tour that omits it, and nothing in the pipeline is looking.

The existence gate verified it at 100%, correctly: it checks whether an entity is *known*, not
whether it is *currently operating*. Those are different questions, and for restaurants only the
second one matters.

**We already have the machinery for exactly this.** `LOCAL-365` refuses to tour a closed exhibition
— *"refusing to tour a dismounted show"* — with a typed clean-fail. **A restaurant is a closed
exhibition that serves dinner.** The concept transfers; the wiring does not exist.

---

## What today's cross-path work did for this tour

Confirmed running, from the log rather than assumption:

- `[Bug2Fix/D536] intent sees the ORIGINAL request` — the D536 fix
- `[D536] Listener asked for 3 stop(s), delivering 3 — request met` — the shortfall check
- `[LOCAL-439] story gate` — running on a restaurant tour for the first time
- Cross-stop repetition and the person-year role guard: both clean

**Zero banned phrases** — the only tour today with none, which is notable given the phrase filter's
known coverage gap (descriptions only). Restaurant prose seems less prone to the "breathtaking
view" register than coastal prose.

---

## Recommendation, and the handoff before mobile + GCloud

**Accept the tour with a caveat**: it reads well and is factually strong on history, but do not rely
on it operationally until the two defects above are closed.

**The three things I would do first after the release**, in order:

1. **Restaurant closure check** — port `LOCAL-365`'s logic from exhibitions. Highest risk of the
   three: it sends a real person to a real door.
2. **Make `LOCAL-36` report "0 verified" as a WARNING, not a PASS.** One-line honesty fix, and it
   stops the same false reassurance appearing in every restaurant tour.
3. **Run the phrase filter over orientations, Directions and the closing recap** —
   `LOCAL-192` covers stop descriptions only. Reported three times now, still open, still cheap.

**And the standing one:** `story_units` is the real quality ceiling on every path — 1/3 here, 0/5
on biking, 1/3 on the museum tour at its best. The retrieval finds real episodes; the narration
does not reliably turn them into stories. That is the next substantial piece of work, and it is
now measurable on all three paths, which it was not this morning.

**For the mobile test:** set the app's server IP to **`192.168.0.136`**, and request a location you
have not generated before — `tour_cache` is keyed on (location, type, stop count) and will hand you
a cached tour instantly and free, which tests the cache rather than the pipeline.
