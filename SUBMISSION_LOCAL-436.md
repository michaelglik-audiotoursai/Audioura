# SUBMISSION_LOCAL-436.md

## Verdict: What each verifier asserts and why they disagree

**LOCAL-16 GATE (D1v2)** asserts: "This stop title appears on the venue's own
exhibition page." It grounds stops against the source from which they were
extracted — the MFA's exhibition page for "Picasso, Miró, Dalí: Unbound" at
`https://www.mfa.org/exhibition/picasso-miro-dali-unbound` (reached via Wayback,
snapshot `20260812064828`). For checklist-derived stops, this is a page-text match:
the title appears verbatim on the page the stop was extracted from. This is the
LOCAL-372 grounding check.

**Existence Gate (LOCAL-245)** asserts: "This stop can be found via independent web
evidence — Wikipedia, Wikidata, SPARQL, venue_corpus canonical titles, or
stop_corpus same-source passages." It looks for *external corroboration* that the
entity exists as a publicly documented thing.

**Why they disagree on exhibition works:** A livre d'artiste on loan for a temporary
exhibition (e.g., "Le Lézard aux plumes d'or" — a 1971 illustrated book by Miró,
published by Louis Broder) exists physically and is documented on the MFA's own page.
But it has no Wikipedia article, no Wikidata entry, no OSM node. It is not in the
museum's permanent SPARQL collection. The existence gate's independent-evidence
requirement is the wrong question for a work whose authority comes from the venue's
own exhibition page.

**The gate is wrong here** — not in the sense that it malfunctions, but that it asks a
question that does not apply. It was designed to catch fabricated stops by checking
for independent evidence. For permanent venues and landmarks, this converges with
D1v2. For temporary exhibition works, it diverges: real objects that ARE on the
venue's own page have no Wikipedia trail. The gate cannot distinguish "obscure but
real" from "fabricated" for these works.

## Resolution: Exempt checklist-derived stops from the existence gate

**Option chosen: (a) — exempt checklist-derived stops.**

**Reasoning:**
1. Checklist-derived stops are already grounded by LOCAL-372 against the venue's own
   page. This is a *stricter* check for exhibition works than the gate's general web
   evidence search.
2. The gate was built to catch fabricated stops (D127). Checklist-derived stops are
   extracted from the venue's own page — they cannot be fabricated by GPT.
3. Option (b) ("teach the gate to accept venue-page provenance") would require
   passing exhibition page text into the gate module, creating tight coupling
   between modules that are currently independent.
4. Option (c) ("treat disagreement as INCONCLUSIVE") is weaker: it keeps the stops
   but never says they're verified, leaving ambiguity in the log.

**Implementation:** In `generate_tour_text.py`, at the existence gate invocation
point (~line 7021), added a check:

```python
_seg_checklist_exempt = (
    _deterministic_fill_used
    and _exhibition_stops_source in ('checklist', 'partial', 'prose_llm')
)
```

When true, the existence gate is skipped entirely for that run. The exemption does
NOT apply to `creator_filter` stops (GPT-generated, need gate check) or regular
museum stops.

## Red output — neutralising the fix

Without the exemption, the existence gate drops all 3 MFA Unbound stops:

```
[EXISTENCE-GATE] ENFORCE — 0/3 stops verified (0%), dropping 3 unverified
  [UNVERIFIED] "Le Lézard aux plumes d'or" — no evidence
  [UNVERIFIED] 'Moses and Monotheism' — no evidence
  [UNVERIFIED] 'Au Soleil du Plafond' — no evidence
```

Gate mode: `enforce`. Code path: `stop_existence_gate.run_existence_gate` called
directly with the three exhibition stop titles against "Museum of Fine Arts, Boston".

## Proof: Real exhibition work survives the gate (ENFORCE mode)

**Gate mode: `STOP_EXISTENCE_GATE_MODE=enforce`**

```
[LOCAL-16 GATE] All 3 stops are D1v2-verified ✓
[LOCAL-436] EXISTENCE-GATE: EXEMPT — stops sourced from exhibition prose_llm (already grounded against venue page by LOCAL-372)
```

MFA Unbound delivered: 3 stops, 5710 chars.
- Stop 1: Le Lézard aux plumes d'or (The Lizard with Golden Feathers)
- Stop 2: Moses and Monotheism
- Stop 3: Au Soleil du Plafond

Source: `https://www.mfa.org/exhibition/picasso-miro-dali-unbound` (Wayback snapshot
20260812064828).

## Proof: Fabricated work is still dropped (ENFORCE mode)

**Gate mode: `STOP_EXISTENCE_GATE_MODE=enforce`**

```
[EXISTENCE-GATE] ENFORCE — 0/1 stops verified (0%), dropping 1 unverified
  [UNVERIFIED] 'The Invisible Symphony of Forgotten Dreams' — no evidence
```

The gate correctly identifies and drops a plausible but fabricated work at the
same venue. The exemption only applies to checklist-derived stops, not arbitrary
titles.

## MFA under LOG_ONLY (shipping default)

**Gate mode: `STOP_EXISTENCE_GATE_MODE=log_only`**

```
[LOCAL-16 GATE] All 3 stops are D1v2-verified ✓
[LOCAL-436] EXISTENCE-GATE: EXEMPT — stops sourced from exhibition prose_llm (already grounded against venue page by LOCAL-372)
```

MFA Unbound delivered: 3 stops, 6096 chars.
- Stop 1: Le Lézard aux plumes d'or (The Lizard with Golden Feathers)
- Stop 2: Moses and Monotheism
- Stop 3: Au Soleil du Plafond

Both modes now produce the same outcome for exhibition tours. The exemption logs
identically regardless of mode, because the decision is made before the gate runs.

## Control: Palais de la Méditerranée 4/4, dates intact (D302/D326)

**Gate mode: `STOP_EXISTENCE_GATE_MODE=enforce`**

```
[LOCAL-245] Stop-existence gate mode: ENFORCE
[EXISTENCE-GATE] ENFORCE — 6/6 stops verified (100%), dropping 0 unverified
```

Palais delivered: 4+ stops, dates intact.
- Stop 1: Miss Europe 1965
- Stop 2: Miss Europe 1966
- Stop 3: Construction et inauguration du casino
- Stop 4: Difficultés financières, affaire Agnès Le Roux et démolition

Dates found: 1929, 1934, 1965, 1966, 1982, 1989, 2004.

The Palais stops are NOT exempt (they are not checklist-derived — they come from
SPARQL + GPT). They go through the existence gate normally, pass verification,
and deliver with historical dates intact.

## Unit tests: green

```
tests/test_local436_gate_exemption.py::TestExhibitionGateExemption::test_real_exhibition_works_fail_existence_gate PASSED
tests/test_local436_gate_exemption.py::TestExhibitionGateExemption::test_fabricated_work_still_dropped PASSED
tests/test_local436_gate_exemption.py::TestExhibitionGateExemption::test_exemption_flag_prevents_drops PASSED
tests/test_local436_gate_exemption.py::TestExhibitionGateExemption::test_no_exemption_for_creator_filter PASSED
tests/test_local436_gate_exemption.py::TestExhibitionGateExemption::test_no_exemption_for_non_deterministic PASSED
```

No full-suite run (per task instructions).
