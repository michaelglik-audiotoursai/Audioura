# Tour Improvement Loop — Asian Arts Museum, Nice, France

Closed-loop quality improvement for one venue, using the scoring rubric agreed with
Michael 2026-07-29. Purpose: give Kiro's fix work a real, repeatable numeric target
instead of one-off bug reports, and give Michael a concrete price-per-quality-point
signal for subscription-tier decisions.

## Rubric (summary — full derivation in chat history / round12-review-state.md memory)

- N = requested stop count, share = 100/N points per stop-slot.
- FABRICATED or MISSING stop-slot (fake nav-label stop, invented artist/artwork with
  no real referent, or a slot never filled at all): **−1.0 × share**.
- THIN/NO-STORY (real referent, generic/boilerplate, no verifiable specific facts):
  **+0.5 × share**.
- ADEQUATE (real referent, some specifics, some generic filler): **+0.75 × share**.
- RICH (real referent, specific, verifiable, distinctive): **+1.0 × share**.
- Structural-defect surcharge (independent axis — template leaks, corrupted fields,
  voice breaks): **−0.25 × share**, capped at **−0.5 × share** per stop.
- Cross-stop correlation bonus (only if genuinely earned — actual callbacks between
  stops, not a templated "you've seen X, Y, Z" wrap-up): **+50%** of affected stops'
  value, can push total >100.
- Venue-identity bonus (genuinely specific venue-level facts — architect, founding
  story — surfaced in the intro when per-stop facts are scarce): up to **+10%** of
  tour total.

## Loop mechanics (agreed with Michael 2026-07-29)

1. LEAD (Claude) evaluates the current tour, identifies concrete defects, dispatches
   a fix task to Mac Mini Kiro.
2. Kiro fixes, live-verifies (must DELETE the exact `tour_cache` row first — same
   cache trap as LOCAL-8/LOCAL-13 — then show CACHE MISS/CACHE STORE), runs the full
   11-suite regression, AND live spot-checks a **second, different venue** to guard
   against overfitting to this one museum. Reports evidence, does NOT self-score.
3. LEAD independently re-scores from the real regenerated text (never trusts Kiro's
   own score) and updates the round table below.
4. Repeat while score < 75.

**Stop conditions:**
- **Plateau:** if the score has not improved by at least **+3 points** vs. 3 rounds
  ago, stop and report to Michael — this overrides continuing even if score is still
  < 75 (noise-tolerant: small round-to-round jitter from LLM stochasticity doesn't
  count as "no improvement" by itself, but 3 rounds flat does).
- **Cost:** stop for Michael's explicit approval before any further round if
  cost-per-tour exceeds **3× the original ($0.0353 × 3 = $0.1059)** OR the absolute
  ceiling of **$0.50/tour** — whichever triggers first (in practice the 3× relative
  trigger binds first).
- Michael may check the current index value at any time; no need to wait for a round
  to finish.

## Round history

| Round | Date | Score | Cost | $/point | Verdict | Commit |
|---|---|---|---|---|---|---|
| 0 (baseline, LOCAL-9→12 fixes applied) | 2026-07-29 | **+15.6 / 100** | $0.0353 | $0.00226 | 2 fabricated stops (UNIFIED-FILL inventing fictional fill), 1 real regression (stop 4 lost hard facts), 2 structural defects (`[Venue Name]` leak, corrupted address field), 1 voice-break | 7e61c13 |
| 1 (in progress) | 2026-07-29 | — | — | — | dispatched as LOCAL-14 | — |

## Round 1 scope (LOCAL-14, dispatched 2026-07-29)

1. **UNIFIED-FILL fabrication (highest priority):** when D1v2 correctly drops a
   candidate as unverifiable, UNIFIED-FILL must never invent a fictional
   replacement (e.g. "Mei Lin," "Untitled Sculpture by Unknown Artist") to hit the
   requested stop count. Either fall back to another genuinely still-available
   D1v2-verified candidate not yet used, or accept fewer real stops than requested
   — never synthesize a name/work that doesn't exist.
2. **Structural defects:**
   - `[Venue Name]` template placeholder left unsubstituted in stop 1's intro.
   - Stop 3 (Fauteuil)'s address field has narrative text leaked into it, corrupting
     the address.
   - The repetition-rewrite logic produced a first-person voice break ("One time, I
     asked the museum staff...") in stop 7 — guide voice must stay third-person.
3. **Stop 4 regression:** "La geste de Bouddha" had specific facts in the original
   tour (II-III century, Pakistan, schiste stone, acquired 2001) that vanished in
   the regeneration, replaced with generic mood prose. Investigate why (fact-sheet
   generation, D1v2 match confidence, RAG fetch) and restore.
4. **Stretch, non-blocking:** venue-identity facts (architect, founding, etc.) still
   don't surface in the intro despite LOCAL-11's hook resolving the venue correctly.

Acceptance: fresh regeneration (cache row deleted first), all 11 suites green, a
live spot-check on a second venue showing no regression, and an honest report of
which of the 4 items above landed vs. didn't — no self-scoring.
