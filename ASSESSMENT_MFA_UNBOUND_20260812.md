# LEAD Assessment — "Picasso, Miró, Dalí: Unbound" tour of 2026-08-12 11:29

**Tour file:** `TOUR_MFA_UNBOUND_20260812.txt` · 3 stops · 5769 chars · generated on
`storied @ e231bc4` (post-LOCAL-438), STORIED_MODE, existence gate LOG_ONLY, cache off.
**Generation wall-clock: ~12 min, of which ~7–9 min was 50 timed-out external lookups
(D395 — fix dispatched as LOCAL-441).**

---

## What is genuinely good

1. **Sourcing is the venue's own words.** All three works extracted from the MFA's
   exhibition page via the archive path (`snapshot 20260812064828, age 0 days`) —
   Cloudflare never let us in the front door and it no longer matters (D381/D382).
2. **The right three works, correct order, correct coordinates, within word budget**
   (326/223/289 words vs 450 budget).
3. **No fabrications survived.** Every claim in the delivered text passed verification
   against fetched sources. The Desnos-style confabulation (D373) did not recur.
4. **Stop 1 is close to standard:** 3 story sentences — Broder's commissioning, the
   Mourlot Frères printing, Miró's 1971 creation. It passes the current gate.

## What is not good enough — measured, not felt

| Stop | story sentences | verdict |
|---|---|---|
| Le Lézard aux plumes d'or | 3 | ✓ PASS |
| Moses and Monotheism | 1 | ✗ FAIL |
| Au Soleil du Plafond | 0 | ✗ FAIL |

1. **Stop 3 carries zero stories.** It names Tériade and Reverdy but wraps them in
   atmosphere ("a testament to...", "invites contemplation") — the exact
   admiration-prose failure D393 diagnosed. A listener learns *that* the work exists,
   not *what happened*.
2. **Boris Fridman vanished this run.** Present in the 04:00 and 08:16 runs, absent
   now — run-to-run variance (D385), not a regression. The donor story is the human
   thread of stop 1 and its survival should not be a coin flip.
3. **Nothing like Michael's 1967-destroyed-edition story appears.** The pipeline still
   *describes from snippets* rather than *asking for a story*. The most compelling true
   narrative about this work — the scrapped first edition, the paper chemistry, the
   1971 redemption — is invisible to a snippet-miner because no single snippet contains
   it. It requires a story-seeking query (Michael's step 2).
4. **12-minute generation** against a ≤2-minute requirement (D395).

## Scoring stop 1's best content under the new scheme (D393/D394, additive 5/4/3)

*"Louis Broder commissioned the work... printed by Mourlot Frères... Miró created it
in 1971"* — trust 5 (venue page), emotion 1 (no arc, no stakes), novelty 1 → **7/12**.
Michael's 1967-disaster story, corroborated: trust ~4, emotion 4, novelty 3 → **11/12**.
The gap between what we deliver and what the material supports is ~4 points of pure
storytelling — and it is a *generation* gap, not an evaluation gap.

## Improvement plan (all dispatched or queued, in order)

1. **LOCAL-439 (queued):** gate judges story-units (≥1 verified unit of ≥3 sentences),
   gpt-4o-mini classification replaces the verb list, additive 5/4/3 interest scoring.
   Fixes the ruler.
2. **LOCAL-441 (queued, concurrent):** external lookups go parallel under a 20s batch
   budget — removes the 7–9 min of sleeping; first step toward ≤2 min.
3. **LOCAL-440 (next):** story-first generation — Michael's 4-step pipeline: connect
   fact→stop→exhibition, ASK for the story, score candidates, verify hard, size-adapt,
   pack (LOCAL-438's selector, already merged). This is what puts a 1967-class story
   into stop 1 and *any* story into stop 3.
4. **After 440:** per-stop parallel narration (the rest of the ≤2 min target), then
   re-measure variance (the D386 harness) — the release question becomes "how often
   does every stop carry a verified story?" with real numbers.

## Bottom line

The plumbing chain is done: right works, right source, nothing invented, budget
respected. The tour is *trustworthy and thin*. Every remaining gap is one problem
wearing three costumes — **we describe instead of narrate** — and the architecture to
fix it (your walkthrough, formalized in D392–D394) is specced and next in the queue.
