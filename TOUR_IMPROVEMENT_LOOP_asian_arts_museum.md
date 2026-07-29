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

  **TEMPORARILY SUSPENDED 2026-07-29 ~13:0x, per Michael's explicit request** before
  he left for ~2 hours: "change the rules just for this time and continue running
  the cycle... this will teach me if having 3 rounds of no progress is futile
  enough in case if after 3 rounds of no progress there progress will come." Round
  3 (LOCAL-16) is currently in progress and would be the 3rd data point (0: 15.6,
  1: -9.4, 2: 15.6) — normally a plateau-stop candidate depending on round 3's
  result. Per his instruction, do NOT stop on plateau during this window — keep
  bouncing/redispatching through as many non-improving rounds as needed. Score>=75
  and the cost caps below remain ACTIVE and are still hard stops. Revert to the
  original 3-round rule (or get Michael's updated call) once he's back and checks
  in — do not treat this suspension as permanent.
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
| 1 (BOUNCED) | 2026-07-29 | **-9.4 / 100** | $0.0436 | n/a (negative) | Kiro claimed 3/4 fixed + honest 7/8 shortfall; LEAD independently regenerated twice (own run + re-read Kiro's own evidence file) and found the real delivered tour is functionally unchanged from round 0 — new fabrication pathways fully offset the fixed one. See findings below. | 318fa2e (not merged) |
| 2 (BOUNCED) | 2026-07-29 | **+15.6 / 100** | $0.0377 | $0.00242 | Duplicate-stop bug (Fix 1) and most attribution fabrications (Fix 4) genuinely fixed — but branched from pre-LOCAL-14 storied (LOCAL-14 was never merged), so UNIFIED-FILL's core "never fabricate" restriction didn't exist as a foundation. Fix 1 only added name-normalization to the OLD fill logic, which still adds GPT-invented "unverified fills." Two such fills this round: one soft-hedged ("La Joie de vivre"), one a full unhedged fabrication of both a named artist AND named artwork ("Mei-Ling Chen" / "Harmony in Bloom") for an exhibit D1v2 explicitly could not verify exists at this venue — the attribution guard (Fix 4) completely failed to fire or catch it. Net score: statistically identical to round 0. See findings below. | 697ad89 (not merged) |

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

## Round 1 verdict (BOUNCED, not merged)

Kiro's diff was real and all 13 suites (11 core + venue_identity + local12) did
genuinely pass — confirmed independently. Kiro's own live evidence (quoted in
CLICKUP_OFFLINE_QUEUE.md) was also real (not fabricated reporting) — the gap was
methodology: Kiro grepped selected log lines ("UNIFIED-FILL added 1 VERIFIED fill,
total now 7/8", "POST-R4-FILL SKIPPED") and treated that as proof of "7/8 stops,
honest shortfall, zero fabrication" without reading the full 8-stop rendered text
or tracing what happens after POST-R4-FILL. It doesn't hold up:

1. **UNIFIED-FILL still produces a duplicate stop.** Its dedup check compares
   `_cand_name.lower()` (the raw candidate name, e.g. "Voyage au pied du mont
   Fuji") against names already in `poi_list` — but the already-placed stop is
   keyed under its CANONICAL name ("Hokusai – Voyage au pied du mont Fuji"). The
   exact match fails, so the same real exhibit gets added a second time under its
   raw name. Reproduced in BOTH Kiro's run and LEAD's independent rerun (always
   lands as stop 7, always duplicates stop 1).
2. **A third, completely untouched fabrication pathway exists: "Part C"**
   (`generate_tour_text.py` ~line 2696-2812, `while len(poi_list) < total_stops`).
   This fires whenever R4/UNIFIED-FILL/POST-R4-FILL still leave a shortfall (which
   LOCAL-14's fix deliberately creates more often, since it refuses to fabricate
   there) — and asks GPT-3.5 directly for "specific, real, well-known" venue
   candidates with ZERO D1v2/Wikidata canonical-title verification. For museum
   tours it doesn't even run the address-match check (line 2771 explicitly skips
   it when `tour_category == 'museum' and _museum_venue_name`). This produced
   "Le souffle de la Chine - De Schongqing à Marseille" (Kiro's run) and
   "L'Afrique en visages" (LEAD's independent run) — two different but equally
   ungrounded, confidently-written invented exhibits. LOCAL-14 fixed 2 of 3
   fabrication pathways and missed this one entirely.
3. **Address/title corruption is NOT fixed, and got worse.** In LEAD's rerun the
   corruption moved from the address FIELD into the stop TITLE line itself, e.g.
   stop 3 rendered as `Located at the Asian Arts Museum on 405 Promenade, 'Stop
   4' features the striking piece titled "Fauteuil. des Anglais, 06200 Nice,
   France` — including a stray `'Stop 4'` meta-reference baked into the name.
   The post-hoc regex sanitization Kiro added doesn't reliably catch this.
4. **New fabrication vector found in Phase 5 description generation itself**:
   stop 5 ("Les paysages de l'âme", a D1v2-VERIFIED work) was confidently
   attributed to "contemporary artist Mei Ling" in LEAD's rerun — a specific,
   named, false attribution with no corpus support (the original tour correctly
   described this as anonymous, 13th century). D1v2 verification only confirms
   the WORK TITLE is real; nothing currently stops Phase 5 from inventing
   specific false claims (artist, era) about a verified work. "Mei Lin/Mei Ling"
   also happened to be the exact fictional name from round 0's UNIFIED-FILL bug —
   possibly GPT's own generic-plausible-name tendency, not a code artifact, but
   worth knowing it recurs.
5. Item 3 (stop 4 fact regression) is real but unreliable — Kiro's run showed
   good specific facts (schist, 2nd century, Greco-Indian), LEAD's independent
   rerun reverted to fully generic prose for the same stop. Corpus-availability-
   dependent, as Kiro itself flagged, not a solid fix yet.

**LEAD's independent score from LEAD's own regenerated text: -9.4/100** —
statistically unchanged from round 0's -9.4. Real, honest engineering effort
landed, but net measured trust-quality is flat: newly-exposed pathways (duplicate
stop, Part C, Phase-5 attribution fabrication) fully offset what got fixed.

Not merged. Container restored to clean approved `storied` (confirmed via
md5sum match). Round 2 should target, in priority order: (a) normalize names
before the UNIFIED-FILL dedup check, (b) gate or disable Part C for museum tours
the same way UNIFIED-FILL/POST-R4-FILL were fixed — accept honest shortfall
instead of ungrounded GPT invention, (c) a stricter reject-and-regenerate
approach for corrupted stop names instead of post-hoc regex salvage, (d) a
Phase-5 guard against inventing a named artist/attribution for a work whose
fact sheet doesn't support one.

## Round 2 verdict (BOUNCED, not merged)

Round 2 branched from `storied` at the round-2 dispatch commit — which does
**not** include round 1's code, since round 1 (LOCAL-14) was bounced and never
merged. This matters: the round-2 task described "the fill-from-verified loop
LOCAL-14 added" as an existing foundation to build a name-normalization fix on
top of, but that foundation was never actually in the codebase Kiro branched
from. Kiro patched the dedup check in the ORIGINAL (pre-round-1) UNIFIED-FILL
logic, which still explicitly adds GPT-invented "unverified fills" — the code
comment literally still reads "Every fill candidate is explicitly unverified"
and the log line still says "added N unverified fills." Round 2 fixed the
duplicate-name comparison bug (confirmed: no duplicate stop in either Kiro's or
LEAD's independent regeneration this round) and the attribution guard clearly
works for MOST stops (five separate stops correctly say "unknown artisan" /
"anonymous artist" instead of inventing a name) — genuine, real progress on two
of four items.

But the deeper problem — ANY fallback path that adds a stop without D1v2
canonical-title verification remains capable of full fabrication — was not
closed, just relocated again (round 0: nav-label scraping; round 1: Part C +
a duplicate; round 2: UNIFIED-FILL's own "unverified fill" mechanism, now with
the name-collision bug fixed but the fabrication risk itself untouched). LEAD's
independent regeneration reproduced the exact same 2-unverified-fills pattern
Kiro's own evidence showed, and reading the FULL text (not just log lines)
found:
- Stop 7 ("La Joie de vivre" — a D1v2-DROPPED, unverified candidate): presented
  as a full, richly-detailed stop with only a soft "the story goes" hedge — not
  strong enough to communicate that the exhibit's very existence is unconfirmed.
  Notably, "La Joie de vivre" is also the title of a real, famous, unrelated
  WESTERN artwork (Matisse/Picasso association) — a confusing coincidence, or
  GPT drawing on real-world art history and misplacing it at this venue.
- Stop 8 ("Le Printemps" — the other D1v2-DROPPED candidate): the attribution
  guard (Fix 4) completely failed here. GPT confidently invented BOTH a named
  artist ("the renowned artist Mei-Ling Chen") AND a named artwork title
  ("Harmony in Bloom") with zero hedging — the single most elaborate,
  confident fabrication seen across all 3 rounds so far, for an exhibit
  Wikidata couldn't verify exists at this museum at all. Whether the guard's
  gating condition failed to trigger, or GPT simply overrode the explicit
  prompt constraint and the post-generation regex safety net also failed to
  match the exact phrasing used, is worth root-causing in round 3.

**LEAD's independent score: +15.6/100 — statistically identical to round 0.**
Three data points now (round 0: 15.6, round 1: -9.4, round 2: 15.6) show the
same underlying pattern each time: fixing one fabrication-fallback pathway
just relocates the problem to a sibling pathway, because there is no single,
uniform enforcement point. Not merged. Container restored to clean approved
storied (md5sum confirmed).

**Round 3 should NOT be another itemized symptom-fix list.** Recommend a
structural fix instead: add ONE single choke-point check — after ALL
candidate-gathering/filling logic runs (UNIFIED-FILL, R4, POST-R4-FILL, Part C,
whatever else exists), for `tour_category == 'museum'`, filter `poi_list` down
to ONLY entries with a D1v2-VERIFIED canonical-title match before any Phase 5
description generation happens. No fill mechanism should be able to sneak an
unverified stop through — verification should be enforced once, centrally, not
maintained separately in every fallback path (which is exactly how this keeps
recurring). Also worth a root-cause pass on why Fix 4's attribution guard did
not fire/catch stop 8's fabrication specifically, since as written it should
have.
