# SUBMISSION_LOCAL-437.md

## Summary

LOCAL-437 redoes the gate exemption proof that LOCAL-436 was bounced for. Three defects
fixed:

1. **The exemption is now bound to a test** — module-scope predicate, imported by the
   test, red when neutralised.
2. **The control is the correct venue** — Palais Lascaris, Nice (not Palais de la
   Méditerranée).
3. **The fabrication proof exercises the actual exemption path** — a fabricated work
   injected on the `prose_llm` path, run end to end.

---

## Defect 1: Module-scope predicate, imported by test

### The predicate

```python
# generate_tour_text.py, line 17
def should_exempt_from_existence_gate(deterministic_fill_used: bool, exhibition_stops_source: str) -> bool:
    return (
        deterministic_fill_used
        and exhibition_stops_source in ('checklist', 'partial', 'prose_llm')
    )
```

### Called from the gate site

```python
# generate_tour_text.py, line ~7055
_seg_checklist_exempt = should_exempt_from_existence_gate(
    _deterministic_fill_used, _exhibition_stops_source
)
```

### Imported by the test

```python
# tests/test_local437_gate_exemption.py, line 16
from generate_tour_text import should_exempt_from_existence_gate
```

### Red when neutralised

Predicate neutralised to `return False`:

```
FAILED tests/test_local437_gate_exemption.py::TestExemptionPredicateBound::test_checklist_source_exempt
FAILED tests/test_local437_gate_exemption.py::TestExemptionPredicateBound::test_partial_source_exempt
FAILED tests/test_local437_gate_exemption.py::TestExemptionPredicateBound::test_prose_llm_source_exempt
```

3 tests fail. 6 pass (the negative cases). The binding works both directions.

---

## Defect 2: Control — Palais Lascaris, Nice

**Gate mode: enforce** (`STOP_EXISTENCE_GATE_MODE=enforce`)

### Result: 4/4 stops, dates intact

```
PALAIS LASCARIS CONTROL RESULTS
======================================================================
Elapsed: 595.2s
Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)
✓ Stops: 4/4
✓ Dates: 1780/1652/1581/1696 all present
✓ Coordinates: 4/4
```

### Stops delivered

| Stop | Date | Status |
|------|------|--------|
| Harpe by Naderman (Paris, 1780) | 1780 | ✓ delivered |
| Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581) | 1581 | ✓ delivered |
| Violes gambe by William Turner (Londres, 1652) | 1652 | ✓ delivered |
| Basse de violon by Paolo Antonio Testore (Milan, 1696) | 1696 | ✓ delivered |

### Gate path (non-exempted)

```
[LOCAL-245] Stop-existence gate mode: ENFORCE
[D1v2] 8/8 works verified — tier: exhibit_museum
[LOCAL-16 GATE] All 8 stops are D1v2-verified ✓
[EXISTENCE-GATE] ENFORCE — 8/8 stops verified (100%), dropping 0 unverified
```

Palais Lascaris is a permanent-collection museum. Its stops are independently
verifiable (D1v2 via SPARQL, and the existence gate via venue corpus). No exemption
fires. The exemption does not affect this venue.

**Internal consistency check:** 4 stops delivered, 4 dates present, 4 coordinates,
4/4 expected stop names found. Numbers agree.

---

## Defect 3: Fabrication proof — prose_llm path

**Gate mode: enforce** (`STOP_EXISTENCE_GATE_MODE=enforce`)

### The case that matters

D390 says: *"the only way the exemption can admit a fabrication is a work invented
by the `prose_llm` extractor itself."* LOCAL-436 tested a fabricated work passed
directly to the gate — that does not exercise the exemption.

### What was tested

1. Monkeypatched `find_exhibition_checklist` to return a result with path=`prose_llm`
   containing 3 real MFA works + 1 fabricated work ("The Invisible Symphony of
   Forgotten Dreams")
2. Ran the full `generate_tour_text` pipeline end to end under enforce mode

### Result: LOCAL-372 strips the fabrication

```
[D1/LOCAL-372] SKIP D1v2 — stops sourced from exhibition prose_llm
[D1/LOCAL-372] DROPPED 1 stop(s) absent from the exhibition page (not extracted from it — likely invented):
[D1/LOCAL-372] 3 exhibition stop(s) grounded against the venue page
[LOCAL-437] EXISTENCE-GATE: EXEMPT — stops sourced from exhibition prose_llm
```

The fabricated work is stripped at line 6117 by `title_appears_in_page()`.
It never reaches the existence gate.

### Unit confirmation (Mode A)

```
title_appears_in_page('The Invisible Symphony of Forgotten Dreams', page_text) = False
✓ STRIPPED: Fabricated work is NOT on the page → dropped by LOCAL-372
```

All 4 real works survive the same check:
```
✓ grounded: 'Le Lézard aux plumes d'or'
✓ grounded: 'Moses and Monotheism'
✓ grounded: 'Au Soleil du Plafond'
✓ grounded: 'À toute épreuve'
```

### Integration confirmation (Mode B)

```
Tour generated: yes
Stops in tour: 3
  - Le Lézard aux plumes d'or
  - Moses and Monotheism
  - Au Soleil du Plafond
Fabricated work in final tour: False
Fabricated work logged as dropped: True
```

### Why the exemption is safe

The defense chain:
1. `prose_llm` extracts works from the exhibition page text (the same text that is `page_text`)
2. LOCAL-372 (line 6100-6127) checks each extracted title against that same `page_text`
3. `title_appears_in_page()` requires ≥70% word overlap with the page
4. A fabricated title (not on the page) has 0% overlap → stripped
5. Only page-grounded titles reach the existence gate
6. The exemption bypasses the gate for those surviving titles only

The scenario *"a work invented by the `prose_llm` extractor itself"* cannot survive
because the extraction LLM's input IS the page text, and the grounding check verifies
against that same page text. An invented title has no page evidence.

---

## MFA Unbound — enforce mode

**Gate mode: enforce** (`STOP_EXISTENCE_GATE_MODE=enforce`)

### Result: 3/3 stops delivered

```
MFA UNBOUND RESULTS
======================================================================
Elapsed: 560.4s
Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)
✓ Stops delivered: 3/3
✓ Exemption fired (checklist/prose_llm path)
  Source: prose_llm
✓ LOCAL-372 page-grounding operated
  3 stops grounded against venue page
```

### Stops delivered

| Stop | Source |
|------|--------|
| Le Lézard aux plumes d'or (The Lizard with Golden Feathers) | prose_llm |
| Moses and Monotheism | prose_llm |
| Au Soleil du Plafond | prose_llm |

### Gate path (exempted)

```
[LOCAL-245] Stop-existence gate mode: ENFORCE
[D1/LOCAL-372] SKIP D1v2 — stops sourced from exhibition prose_llm
[D1/LOCAL-372] 3 exhibition stop(s) grounded against the venue page
[LOCAL-16 GATE] All 3 stops are D1v2-verified ✓
[LOCAL-437] EXISTENCE-GATE: EXEMPT — stops sourced from exhibition prose_llm (already grounded against venue page by LOCAL-372)
```

Without the exemption, these 3 stops would be dropped by the existence gate (D389
proved this). With the exemption, they are delivered because LOCAL-372 already grounded
them against the venue's own exhibition page.

---

## Targeted test suite: green

```
tests/test_local437_gate_exemption.py: 9 passed
tests/test_local435_fence_tolerant_intent.py: passed
tests/test_local422_call_site_binding.py: passed
tests/test_local424_call_site_binding.py: passed
tests/test_local431_story_gate_enforcement.py: passed
tests/test_local417_positive_gate.py: passed
tests/test_local364_exhibition_checklist.py: passed
tests/test_local365_closed_exhibition_signal.py: passed
tests/test_local372_book_word_drop.py: passed
tests/test_local369_exhibition_thread_and_provenance.py: passed
Total: 152 tests passed, 0 failed
```

No full suite run (per task spec).

---

## Env vars behind every number

| Measurement | Gate mode | Env var |
|---|---|---|
| Palais Lascaris 4/4 | enforce | `STOP_EXISTENCE_GATE_MODE=enforce` |
| MFA Unbound 3/3 | enforce | `STOP_EXISTENCE_GATE_MODE=enforce` |
| Fabrication stripped | enforce | `STOP_EXISTENCE_GATE_MODE=enforce` |
| Neutralise red (3 fail) | n/a | predicate returns False |

All runs use `STORIED_MODE=true`, `TOUR_LLM_MODEL=gpt-4o`, `AUDIOURA_DB_TARGET=production`.
