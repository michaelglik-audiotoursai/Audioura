# Tour Quality Rubric (TQR) — v1, 2026-07-04

Scored independently by KIRO and LEAD every improvement cycle, on the full generated tour text, read end-to-end **as a visitor would experience it**. Used by the Continuous Improvement Loop (see AGENT_SYNC.md).

## Part A — Binary gates (any FAIL = cycle continues, no scoring needed)

| # | Gate | How verified |
|---|------|--------------|
| A1 | Zero fabricated entities: every named work/room/exhibit is verified in this venue's collection by ≥1 grounded source (RAG / Wikipedia / museum site) | Cross-check each stop title + in-text named entities against the retrieved evidence set |
| A2 | Zero wrong-venue works (famous work by the right artist located elsewhere — e.g. "Jerusalem Windows" in Nice) | Same evidence check: source must tie the work to THIS venue |
| A3 | Contained/Distributed correctness: museum tour → ≤2 unique addresses, no other named venues as stops | `content_qa_runner.py` exit 0 (factual checks) |
| A4 | No unverified location claims: room/hall named only if grounded; otherwise "ask museum staff" | Read directions per stop |
| A5 | Beta parity: `STORIED_MODE=false` output unchanged | Regression check |
| A6 | Entity identity: every stop is a single, canonical, disjoint work verified BY TITLE — never by topic-word overlap with book/cycle/theme names; no stop is a superset or member of another stop (added 2026-07-05 after Michael's "Biblical Message" catch) | Check evidence entries resolve to canonical work titles; check stop list for set/member overlap |

## Part B — Quality dimensions (score 1–5; exit needs BOTH assessors ≥4 on ALL)

| Dim | 5 looks like | 2 looks like |
|-----|--------------|--------------|
| B1 Grounded richness | Each stop has specific, verifiable facts (dates, materials, provenance, documented anecdotes) beyond what a plaque would say | Generic filler ("masterpiece", "timeless", "invites you to reflect") padding thin content |
| B2 Narrative arc | Prolog frames a journey; stops build on each other (spine roles evident); epilog pays off the arc with a real recap | Stops are interchangeable standalone blurbs; arc words present but no actual build |
| B3 Per-stop story | Each work gets a STORY, found-first: documented origin, intention, turning points, people (e.g. the Biblical Message was meant for a Vence chapel, following Matisse and Picasso, and became France's first living-artist museum), with claims tracing to retrieved snippets. **Stories may be invented ONLY where none can be found** — and inventions must be interpretive/thematic, clearly not presented as documented fact | Description of what the work depicts, restated three ways; or an invented arc used where a documented story WAS findable (added after Michael's 2026-07-05 story-mining insight; fallback rule per Michael 2026-07-05) |
| B4 Practical usability | Visitor always knows what to do next: where the work is, or explicitly "ask staff"; realistic pacing; word counts 200–500 | Fabricated or missing wayfinding; stops too thin/bloated |
| B5 Voice & variety | Distinct openings, story-type variety, no repeated sentences/phrases across stops, no forbidden phrases | Template smell: same rhythm every stop |

## Delivery rules (added 2026-07-05, Michael's exit review — checkable per tour)

1. **Credits:** found stories are credited — inline for quotes, plus a short spoken "Sources" line in the epilog. Paraphrase always; never copy source prose.
2. **Structure:** no standalone "Introduction:" section — prolog lives inside Stop 1's opening (epilog already lives inside the last stop). Output is strictly stop-structured for the app/TTS.
3. **Orientation = substance or silence:** an orientation exists only if it gives a specific position FOR A REASON or names a concrete visual element to find. Generic positioning + unanchored adjectives ("fully immerse", "intricate details", "symbolic richness") are defects.
4. **Honor requested stop count:** verified stops < requested triggers bounded candidate replenishment (re-prompt excluding tried names) BEFORE delivering fewer; fewer-than-requested ships only with `stop_count_warning` after exhaustion.

## Exit criterion ("really good tour")

All Part A gates PASS **and** both assessors score ≥4 on all B dimensions **for 2 consecutive generations** (stability, not luck — temperature variance is real). Then, and only then, hand to Michael for human judgment.

## Assessment artifact (required each cycle)

Each assessor appends to the cycle's ClickUp task:
1. Part A table with proof line per gate
2. Part B scores + the single worst sentence/passage quoted for each dim scored <4
3. Defect list, each tagged `[GEN]` (prompt/pipeline fix) or `[QA]` (checker gap — if a human can see the defect but the QA didn't, the QA gains a check)
4. Verdict: `CONTINUE (defects listed)` or `EXIT-READY`

Rule: any defect Michael later finds that neither assessor listed → add a rubric line or QA check so it can't recur. The rubric is a living document.
