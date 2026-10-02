# Judgement — Monaco restaurant tour v3, and the answer to "is there a mechanism to learn?"

**2026-08-27**, build `02c3520`. Tour: `TOUR_MONACO_RESTAURANT_20260827_v3.md`.
**3 requested, 2 delivered** — and the missing one is the point.

---

## What you found

**La Marée Monaco closed on 30 September 2020, and I shipped it as stop 3.** The closure check I
had built that morning ran on it and cleared it. You found it by searching the name yourself.

## Why it failed — a logic error, not a tuning problem

The same restaurant returns **opposite verdicts depending on the spelling searched**:

| query | verdict | evidence the model was shown |
|---|---|---|
| `La Maree` | closed_permanently ✅ | *"La Marée Monaco. Permanently closed. 1615 votes."* |
| `La Marée` | open ❌ | *"open 7 days a week in Monaco"* |

Closure notices and stale listings **coexist**. Aggregators keep plausible hours alive for years
after a business dies — in this very run the extractor reported
`hours=19:12-00:22, price_band=Average price 79 EUR` for a restaurant that has been shut for six
years.

I had the check weigh evidence-of-closure against evidence-of-operation. **That makes the verdict a
coin toss decided by whichever snippets SERP returns that second.**

**The costs are not symmetric.** Skipping an open restaurant costs a listener one stop. Sending
them to a locked door is the entire harm. Closure is now **decisive**: probed across accented and
unaccented spellings, matched deterministically against a marker list rather than judged by a
model, and it **overrides** a confident "open" complete with hours.

Verified live, all four spellings agree, and the drop fired in the tour:

```
[D538] ⚠️  DROPPED 'La Maree' — reported permanently closed
[D536] ⚠️  LISTENER ASKED FOR 3 STOP(S), DELIVERING 2
```

**The over-correction is guarded too**, because it is the obvious next failure: *"closed on
Mondays"* and *"the kitchen closed at 22:30"* must not delete a restaurant. Tested.

## The mechanism you asked for

**`tests/known_closed_venues.json`** — replayed by `tests/test_d539_closure_regression.py` on every
change.

Every entry is a venue that **shipped in a tour** and turned out not to be visitable. Each carries
the tour it shipped in, who found it, **why it was missed**, and the ground truth. Entries are
never deleted; a venue that reopens becomes `expect: open` and keeps its history, because the case
still exercises the machinery.

Two entries today:

1. **La Marée** — `closed`, with the spelling-dependence diagnosis in full.
2. **Joël Robuchon Monte-Carlo** — **`verify`, not `closed`.** I suspect it but have not confirmed
   it. The corpus distinguishes what we know from what we suspect, so a suspicion cannot harden
   into a fact by being written down.

**Why this is the right shape.** Every guard built in the last two days was written from a single
real failure — the Guernica fabrication, the Gautier birth year, the 1946 repetition, the
Hippodrome waypoint. They hold because reality supplied the case. This file makes that pattern
explicit instead of accidental: **a defect a human caught can never quietly return.**

## The honest limitations

1. **The tour is 2 stops, not 3.** Dropping a closed restaurant leaves a hole and nothing refills
   it. The shortfall is announced, which is correct behaviour, but replenishment for restaurant
   tours does not exist. **Post-release** — it touches selection, and that is not a release-eve
   change.
2. **The closure check is restaurant-only.** A closed museum, a demolished landmark or a shut
   viewpoint on a walking tour would still ship. `LOCAL-365` covers exhibitions; nothing covers the
   rest.
3. **Detection depends on someone having published the closure in an indexable form.** A quietly
   shuttered venue with no coverage will pass. This raises the floor; it does not guarantee.
4. **`story_units` 0/2** — unchanged, and still the ceiling on every path.
5. **The stop list varies run to run** (Phase 3A is unseeded), so I cannot promise La Marée would
   have been proposed again. What I can say is that **when it is proposed, it is now removed.**

## Recommendation

**Ship this.** Then stop on Storied.

The remaining items — story units, the five museum-gated checks, closure beyond restaurants,
replenishment, offline Q&A — are all real and all post-release. **Subscribed is a better use of
your time than another increment here**, and everything above is recorded in `DECISIONS.md`
(D531–D539) so it can be picked up from disk by a session that was not here.
