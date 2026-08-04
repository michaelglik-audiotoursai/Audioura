# Anchor Gate Design

## Recommendation

**Do not enforce a hard gate yet. Deploy as log-only (shadow mode) on the
next five generated tours, gating only `UNLINKED_ENTITY` paragraphs once
per-stop corpus coverage reaches ≥ 60% of stops on a tour.** At 13.2%
ANCHORED overall, hard enforcement would strip 87% of content — exactly the
"very little substance" Michael warned against. The detector is working
correctly; the corpus is still catching up. The right sequencing is:
(1) build corpus coverage via the paid-search pipeline already proven at
$0.006–$0.025 per venue, (2) shadow-log every generation to track the
metric rising, (3) flip the gate to enforcing once a tour's corpus makes the
test fair. This keeps the bias toward more substantiated content, not less.

---

## 1. Where in the pipeline

The gate runs **inside the existing content-QA stage**, after text generation
is complete and before audio synthesis begins. Specifically:

```
generate_tour_text_service (port 5000)
        ↓ paragraphs per stop
tour_generation_service (port 5001) — content-QA lives here
        ↓  ← ANCHOR GATE runs here, after rubric scoring
        ↓     (new step within the same service, not a new container)
tour_orchestrator_service (port 5002) — proceeds to TTS
```

**Why here, not earlier:** The gate needs final paragraph text and the
per-stop corpus to both be available. Generation must finish before
substantiation can be tested. Placing it after the existing rubric means the
rubric still catches style/length/tone issues; the anchor gate catches
stop-specificity issues. They are orthogonal checks.

**Why not a separate service:** This is a deterministic classifier (no LLM
call, $0.00 per invocation). It shares the same database connection the QA
stage already holds. Adding a network hop for a <100ms in-process check
would add latency and failure modes for no benefit.

---

## 2. Behaviour per classification class

| Class | Definition | Gate action |
|-------|-----------|-------------|
| `ANCHORED` | Paragraph contains ≥1 corpus-backed anchor tying it to this stop | **Pass.** No action. |
| `NO_ANCHOR` | Generic prose with no entity or anchor at all | **Log + retain (shadow mode).** When enforcing: attempt corpus search → retain if anchored after search → remove only as last resort. |
| `UNLINKED_ENTITY` | Names a person/work/event but does not substantiate the link to this stop | **Log + retain (shadow mode).** When enforcing: targeted search for entity–stop relationship → if found, re-classify as ANCHORED → if unfindable after search budget, remove. |
| `NAVIGATION` | Wayfinding/transition paragraph ("Continue along the promenade…") | **Exempt. Never scored, never removed.** These are functional content, not descriptive claims. The detector already excludes them from the scored denominator (D51 confirmation, LOCAL-175). |

### Enforcement priority when the gate activates

`UNLINKED_ENTITY` is gated **first and more aggressively** than `NO_ANCHOR`:

- `UNLINKED_ENTITY` makes a specific *claim* (names Fitzgerald, references a
  painting) without backing it. This is the failure mode Michael explicitly
  identified. It is more clearly wrong and more clearly fixable (search for
  the named entity).
- `NO_ANCHOR` is generic but not necessarily false. "Enjoy the Mediterranean
  breeze" is vapid but not misleading. Removing it thins the tour without
  fixing an error.

---

## 3. Search budget per tour

### Observed costs

| Venue type | Fetch cost | Sources found |
|-----------|-----------|---------------|
| Palais Lascaris (indoor, specific works) | $0.006 | 6 passages |
| French Riviera biking (15 outdoor stops) | $0.025 | 15 sources |
| Per-venue average | ~$0.002–$0.004 | — |

### Proposed cap

**$0.10 per tour generation**, allocated as:

- Up to $0.05 for initial corpus-building (fetching stop_corpus for stops
  that lack it — the LOCAL-178/179 pattern).
- Up to $0.05 for entity-specific searches triggered by the gate (the
  Fitzgerald pattern — search for a named entity's relationship to the stop).

At observed rates ($0.002–$0.004/venue), this funds 25–50 entity searches —
far more than a typical 10–15 stop tour would need.

### What happens when the budget is hit mid-tour

**Retain unresolved paragraphs and log them.** Rationale:

- Michael's directive: "If we start simply remove everything we will end up
  with very little substance." The budget cap is a cost control, not a
  quality signal. Hitting it means we ran out of search allowance, not that
  the content is bad.
- A paragraph that *might* be substantiable (we just couldn't afford to
  check) is better than a gap in the tour. The user hears a slightly generic
  sentence; without it they hear silence or an abrupt jump.
- The log ensures these paragraphs surface in the next audit cycle and can
  be resolved when corpus is built out.

**Alternative considered and rejected:** Remove unresolved paragraphs after
budget exhaustion. This produces unpredictable tour lengths depending on
which stops happen to be processed last (when budget is lowest). Two
identical tours generated a day apart could differ if search ordering
changes. This violates the determinism principle the detector was built on.

---

## 4. Removal floor

### Proposed rule

**Never remove below 3 paragraphs per stop, AND never remove more than 40%
of a stop's paragraphs in a single generation.**

Whichever limit is hit first protects the stop.

### Reasoning

- Tours currently average 4–6 paragraphs per stop. Removing below 3 leaves
  a stop with an introduction and one or two facts — barely enough to fill
  30 seconds of audio. Below that, the stop feels like a placeholder.
- The 40% cap prevents a stop with 10 paragraphs from losing 7 of them even
  though 3 remain. Losing 4/10 is aggressive enough; losing more signals a
  corpus gap, not a content problem.
- When the floor is hit, the gate **logs which paragraphs it would have
  removed** but retains them. This creates a queue for corpus enrichment:
  these stops need better sources, not fewer paragraphs.

### Edge case: all paragraphs fail

If every scoreable paragraph on a stop is `NO_ANCHOR` or `UNLINKED_ENTITY`:

1. The gate retains all paragraphs (floor rule).
2. It logs the stop as `CORPUS_GAP` — meaning the stop has no per-stop
   corpus data at all, making the anchor test structurally unfair.
3. This stop is queued for priority corpus-building on the next enrichment
   pass.

This is not a defect in the gate; it is the gate correctly identifying that
the corpus hasn't reached this stop yet.

---

## 5. Whether to gate at all yet

### Current state of the world

- **13.2% ANCHORED overall** (87% would be rejected under hard enforcement)
- **Corpus coverage is sparse:** 14/58 stops (24.1%) have stop_corpus data
- **Where corpus exists, the metric is strong:** MAMAC 88%, Chagall 70%,
  Palais Lascaris 23.5%, Riviera 32.3%
- **Where corpus is absent, the metric is zero** — and this is the
  detector working correctly, not a detector bug

### Recommendation: shadow mode (log-only) with a defined activation trigger

**Phase 1 — Shadow mode (now):**
- Run the detector on every generated tour
- Log per-paragraph classifications to the database
- Report ANCHORED % per tour and per stop in generation logs
- No content is removed or modified
- Duration: until the activation trigger fires

**Phase 2 — Selective enforcement (trigger: ≥ 60% of stops on a tour have
stop_corpus data):**
- Gate `UNLINKED_ENTITY` paragraphs only
- Apply the search-before-remove pipeline (corpus → paid search → remove)
- Respect the removal floor (3 paragraphs / 40% cap)
- `NO_ANCHOR` paragraphs remain log-only
- Duration: until overall ANCHORED reaches ≥ 50% on gated tours

**Phase 3 — Full enforcement (trigger: ANCHORED ≥ 50% on tours where Phase 2
is active):**
- Gate both `UNLINKED_ENTITY` and `NO_ANCHOR`
- Full search-before-remove pipeline for both classes
- Removal floor still applies

### What would change my mind

I would skip shadow mode and enforce immediately if **any** of these were true:

1. **Corpus coverage reaches 60%+ of stops** across the active tour set
   before this design is implemented — meaning the test is already fair for
   most content.
2. **Michael directs immediate enforcement** after reviewing the shadow logs,
   accepting that tours will be shorter until corpus catches up.
3. **A user-facing quality incident** traces to an unanchored paragraph
   (e.g., a factually wrong Fitzgerald claim reaches a listener). At that
   point, the cost of false retention exceeds the cost of thin tours.

Conversely, I would **delay** Phase 2 beyond the 60% trigger if:
- The search pipeline proves unreliable (> 20% of searches return no usable
  source for entities that clearly exist)
- Tour length drops below minimum acceptable threshold (< 2 minutes audio
  per stop) on early enforced tours

---

## 6. What the gate will and will not catch

### Will catch

- **Name-dropping without substance:** "Fitzgerald was inspired here" with no
  explanation of what he wrote or how it connects to the stop.
- **Interchangeable filler:** "Experience the enduring power of nature" —
  prose that passes the substitution test (swap the place name, still true).
- **Corpus gaps:** Stops where we have no substantiating data at all, flagged
  for enrichment rather than left silently generic.

### Will NOT catch

- **Anchored but dull:** A paragraph can cite a correct date, name a real
  painting, and still be boring. The gate tests substantiation, not prose
  quality. "The painting was completed in 1967" is ANCHORED and tedious.
- **Anchored but repetitive:** If three paragraphs on the same stop all
  anchor to the same corpus fact, the gate passes all three. Redundancy
  detection is a separate concern.
- **Factual errors within anchored content:** If the corpus itself contains
  an error (unlikely for Tier 1 sources, possible for Tier 3), the gate
  will anchor to the wrong fact and pass it. The gate trusts the corpus.
- **Tone, pacing, narrative flow:** These are style concerns handled by the
  existing rubric, not by the anchor gate. A tour can be 100% ANCHORED and
  still feel like a Wikipedia recitation.
- **"Generic but true":** "The Mediterranean Sea is to your right" is generic
  and true and useful wayfinding. The NAVIGATION class exempts obvious cases,
  but borderline atmospheric sentences ("The sun warms the ancient stones")
  may be flagged as NO_ANCHOR despite adding value. The removal floor
  protects against over-pruning these.

### The 100% ANCHORED ≠ good tour warning

A tour where every paragraph is ANCHORED means every paragraph is
substantiated by the corpus. It does NOT mean:
- The tour is engaging
- The tour has good narrative arc
- The paragraphs flow into each other
- The tour is the right length
- The listener will enjoy it

The anchor gate is one quality dimension. It answers: "Is this paragraph
saying something specific and verifiable about *this* stop?" That is a
necessary condition for a good tour, not a sufficient one.

---

## 7. Implementation sequence (when this design is approved)

This section is informational — no work begins until Michael accepts or
modifies the recommendation above.

1. Add `anchor_gate_log` table (tour_id, stop_id, paragraph_index, class,
   action_taken, search_cost, timestamp)
2. Integrate detector call into content-QA stage (shadow mode: log only)
3. Add per-tour ANCHORED % to generation output metadata
4. Build corpus-coverage check (% of stops with stop_corpus data)
5. Implement activation trigger logic (Phase 1 → Phase 2 transition)
6. Implement search-before-remove pipeline within the gate
7. Add removal floor enforcement
8. Implement Phase 2 → Phase 3 transition logic

Estimated: 3–4 tasks after approval, no new containers, no generation
changes until Phase 2 activates organically.
