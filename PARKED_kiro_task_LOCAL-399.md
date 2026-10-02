# LOCAL-399 (PARKED — unpark when LOCAL-398 merges) — Storytelling is not an exhibition feature

**Park reason:** same prose path as 397/398.

---

## Michael's ruling, 2026-08-11 (going to sleep)

> "I expect to see this tour with stories and **actually most of other tours with
> stories also, as the story-telling ability is needed for any tour**."

397 and 398 build storytelling inside the exhibition path. That is where the
failure was found, but it is not where the capability belongs. **A walking tour, a
restaurant tour and a general museum tour all need stories**, and none of them has
an exhibition page or a curator's premise.

## What must generalise

The mechanism built in 397/398 is venue-agnostic and must be reachable from every
tour type:

| Step | Exhibition case | Must also work for |
|---|---|---|
| identify people/entities per stop | credit line: artist, publisher, printer, donor | a building's architect and patron; a dish's chef; a street's namesake; an instrument's maker |
| search for stories about them | `work_story_searcher.search_stories_for_stop()` | same call, different subjects |
| attach to the right stop (D315) | work-attribution | same rule: a beat belongs to the stop whose subject it concerns |
| relevance test (D325) | work / maker / exhibition premise | work / maker / **venue purpose** / the place itself |
| correction not deletion (D327) | same | same |
| earn the adjective (D324) | same | same |

**The framing cases from D302 already give the hook:** `exhibition`,
`venue_purpose`, `none`. Story attachment should key off whichever applies:
- `exhibition` → the curatorial premise (done in 397)
- `venue_purpose` → why the institution exists. **Palais Lascaris already detects
  "bequeathed to the city of Nice in the testament of 26 May 1901"** — that bequest
  is a story nobody has told yet, and the tour currently never mentions it.
- `none` → the objects and their people, no institutional narrative invented

## The task

- Make the story pipeline run for **every** `tour_category`, not only museum
  exhibitions. Where a category has no obvious "maker", use whatever named people
  the grounded corpus supplies for that stop.
- **Palais Lascaris is the first proof**, because it is already the control venue
  and already detects a bequest it never speaks about. Its instrument makers —
  Naderman, Antonio de Torres, Testore, Schnitzer — are named in the stop titles
  and are exactly the kind of subject `search_stories_for_stop` exists to research.
- Then one non-museum tour. Pick a walking tour with a real venue and show a story
  reaching a stop.

## Do NOT

- Do not invent a purpose for a venue that has none (D302 case 3, `framing=none`) —
  a general museum with no stated mission gets object stories, not an institutional
  narrative.
- Do not regress the exhibition path. Everything 397 and 398 deliver must hold.
- Do not let story budget explode: report SERP query count and cost per tour type.
  If a category is disproportionately expensive, say so rather than silently
  spending.

## Acceptance — live, per D284, case-insensitive in python (D299), delivered text only (D312)

Three live generations, full text pasted for each:

1. **`Palais Lascaris, Nice, France`, 4** — ≥1 verified story per stop naming a
   person and something they did that is not visible; the **1901 bequest** told as
   a story; 4/4 real instruments; dates 1780/1884/1696/1581 intact;
   `framing=venue_purpose`; **live base score reported** (variance band is
   68.8–93.8 per D326 — report the number, do not chase it)
2. **`Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8** — everything
   397/398 delivered still holds, unchanged
3. **One walking tour** of your choice with a real venue, 3–4 stops — ≥1 verified
   story per stop

Plus for all three: zero unearned evaluative adjectives (D324); every story beat
passing the D325 relevance tests; corrections logged per D327; SERP query count and
cost per tour.

Env: `DISABLE_TOUR_CACHE=1`,
`DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
`STORIED_MODE=true`, plus `SERP_API_KEY`/`SERP_PROVIDER`.

## Tests

Expected red-on-revert count stated; revert breaks the **logic, not the symbol**
(D296). Required: a test that the story path is reached for a non-museum
`tour_category`. Per D307, at least one test on the real generation path.

## PROCESS
- Branch `kiro/local399-stories-everywhere` off `storied`.
- Write `SUBMISSION_LOCAL-399.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
