# Track C — the story-selection factory (listener preference feedback loop)

**Written 2026-08-11 by Storied_Tours at Michael's instruction. Not yet dispatched.**

---

## Michael's instruction

> "search returns 23 results — I love it: the more, the merrier. We can not fit all
> 23 of course and neither we want to, but **once we get a feedback loop of the
> listener preferences deducted from the previous 'likes' and 'dislikes' we will
> custom select which stories to choose for which listener.** I suggest you start
> putting the factory for that now."

## Why this is the right shape, and why now

The pipeline currently fetches ~85 snippets per tour and injects 5 per stop chosen
by a fixed ranking. **That fixed ranking is a placeholder for a personalised one.**
Every piece needed for personalisation is a piece we now have:

- retrieval returns far more candidates than we use (85 → 15) — the surplus is the
  raw material for choice
- snippets are already scored and ranked (LOCAL-411)
- stops are already classified — CLAUDE.md records `stop_metrics.class_details`,
  `class_historic`, `class_social` as **live with 315 classified rows**
- `STORY_QUALITY_DESIGN.md` §2c/2d already specify the swipe/personalisation
  feature; SQ4b is the deferred ClickUp task `wdvrdawdje`

So this is not new architecture. It is connecting an existing classifier to an
existing ranker via a feedback signal we do not yet capture.

## The factory, in the order it should be built

**1. Capture the signal (do this first — it is the only irreversible-ish part).**
Nothing personalises without data, and data only accumulates with time. Add
like/dislike capture per *stop* (not per tour — the unit of preference is the
story, not the outing), stored with the stop's existing class vector.
Even before any selection logic exists, **start collecting.** A month of signal is
worth more than a clever cold-start rule.

**2. Classify each candidate snippet, not just each stop.** The three existing
classes (`details` / `historic` / `social`) are the natural axes: an auction
catalogue entry is `details`, "Picasso met Mourlot in 1945" is `social`, "published
1971 in an edition of 50" is `historic`. Score every retrieved snippet on the same
axes the stops already use, so preference and candidate live in the same space.

**3. Build the listener vector.** Per listener, a running weight over the three
classes, updated from likes/dislikes. Start with something simple and legible —
a count or exponential moving average. Resist a learned model until there is enough
signal to justify one.

**4. Personalise the rank, keep the floor.** The selection becomes: score by story
quality (LOCAL-411's ranking) **× listener affinity**. Two constraints that must not
be negotiable:
   - **Grounding is never traded for preference.** A story the listener would love
     but the corpus does not support is still forbidden.
   - **Keep a diversity floor.** If a listener's vector says "details only", still
     include one `social` story per tour — otherwise the loop collapses to a
     monoculture and preferences can never be revised.

**5. Only then, measure.** A/B the personalised ranker against the fixed one on
completion rate and like rate. Until step 1 has run for weeks, there is nothing to
measure.

## What NOT to build yet

- No per-listener model training. Three-class weights are enough to start and will
  reveal whether the signal is even informative.
- No cross-listener collaborative filtering. That needs a user base.
- Do not let personalisation reach into *which stops* are chosen — only which
  *stories* are told about them. The stops are determined by the venue and the
  grounding; personalising them would change what the tour *is*.

## Dependency note

This is downstream of the current story work. Personalised selection is pointless
while **zero** search-sourced stories reach the prose (the open LOCAL-412 problem).
**Build step 1 now** — signal capture is independent and time-sensitive. Hold steps
2–5 until a story actually lands in a delivered tour.

## Where it should run

Signal capture touches the mobile app and the DB, which is **Track B's** territory
(`TRACK_B_STORIED_VS_BETA.md`, session `GCloud_Storied`). Steps 2–4 are ranking
logic in `work_story_searcher.py` / `generate_tour_text.py`, which is
**Storied_Tours**. Split accordingly; the two meet at the schema.
