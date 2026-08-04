##### READY FOR REVIEW

# LOCAL-39: Visitor Facts Rebase — LOCAL-35 composed with LOCAL-36

## What was done

Rebased LOCAL-35 (structured visitor facts extraction) onto current `storied`
(which contains LOCAL-36 practical facts QA gate and LOCAL-37 three-class stories).

The two mechanisms are **composed**, not choosing between them:
- **LOCAL-35's `visitor_facts_extractor.py`** provides the structured extraction
  (closed_days, seasonal hours, conditional admission with source_url).
- **LOCAL-36's `practical_facts_gate.py`** verifies every claim against raw source
  text — unsourced claims are DROPPED.
- **LOCAL-39 wires them together**: `fetch_visitor_info_with_provenance()` does a
  single fetch that serves both extraction AND provenance needs.

## Gate enhancements (required for composition)

1. Added `except` as a closure indicator → handles "open daily except Tuesdays"
2. Refined admission verification: unconditional "Free" is only rejected when the
   source contains a **general entry price** (tarif normal/plein/unique, Musée X – €N),
   not workshop/guided-tour prices

## Merge strategy (field-level best-of)

When multiple pages are fetched (FR + EN), the extractor **merges** the best fields
from each: takes seasonal hours from whichever page has more, takes admission from
whichever has a specific price, takes closed_days from whichever detected them.
This handles the real-world case where the FR page has 2 seasonal hour ranges but
the EN page has the "Musée Matisse – 12€" line.

---

## Evidence: Simulated acceptance (all three venues, page text from official sites)

```
LOCAL-39 ACCEPTANCE: Visitor Facts (LOCAL-35) + Provenance Gate (LOCAL-36)
Time: 2026-07-30 08:12:47
Pipeline: visitor_facts_extractor → practical_facts_gate

Asian Arts Museum (départemental):
  Museum Information: Closed on Tuesday. 10:00–17:00 (1 Sep–30 Jun); 10:00–18:00 (1 Jul–31 Aug). FREE
  Gate: 2/2 VERIFIED, 0 dropped ✓

Musée Matisse (municipal):
  Museum Information: Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents
  Gate: 3/3 VERIFIED, 0 dropped ✓

Palais Lascaris (municipal):
  Museum Information: Closed on Tuesday. 10:00–18:00. €5; free for Métropole residents
  Gate: 3/3 VERIFIED, 0 dropped ✓

INJECTION TEST: Matisse with fabricated 'Free admission':
  Gate: DROPPED — not supported by source ✓

ALL PASS
```

## Evidence: Live extraction from musee-matisse-nice.org

```
[LOCAL-35] Visitor info page found (fr): http://musee-matisse-nice.org/informations-pratiques
[LOCAL-35] Visitor info page found (en): http://musee-matisse-nice.org/practical-information
[LOCAL-35] Extracted from FR page: closed=[], hours=2, admission='Free for Métropole residents'
[LOCAL-35] Extracted from EN page: closed=['Tuesday'], hours=1, admission='€12; free for Métropole residents'
[LOCAL-35] MERGED: hours from FR (2 seasonal), admission from EN (has €12), closed from EN
[LOCAL-35] Final: Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents

[LOCAL-36] Practical Facts Gate:
  Claims found: 3
  Verified: 3
  Dropped: 0
  AUDIT: closed_day | Closed on Tuesday | http://musee-matisse-nice.org/practical-information | VERIFIED
  AUDIT: admission | €12 | http://musee-matisse-nice.org/practical-information | VERIFIED
  AUDIT: admission | free for Métropole residents | http://musee-matisse-nice.org/practical-information | VERIFIED
```

## Evidence: Live generation run (Matisse — 8 stops, correct info)

```
VENUE: Matisse Museum
  Stops delivered: 8/8
    1. Nu bleu IV
    2. Nymphe dans la forêt
    3. Tempête à Nice
    4. Pierre Matisse, un marchand d'art à New York
    5. Odalisque au coffret rouge
    6. Lectrice à la table jaune
    7. Nature morte aux grenades
    8. Papeete-Tahiti
  Museum Information: Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents
  Gate: PASSED (3 verified)
  ✓ All checks pass
```

## Evidence: Matisse does NOT say "Free" unconditionally

The pipeline **never** outputs just "Free" for Matisse:
- Extraction: `admission='€12; free for Métropole residents'` (always with price)
- Gate: fabricated "Free admission" → DROPPED by provenance gate
- Live run confirms: "€12; free for Métropole residents"

## Evidence: Unit tests (49 passing)

```
tests/test_local35_visitor_facts.py — 23 passed
tests/test_local36_practical_facts_qa.py — 26 passed
Total: 49 passed in 0.09s
```

## Blocking: API quota exhausted

The OpenAI API key ([REDACTED — live OpenAI key, removed 2026-08-04; see D79]...) has hit `insufficient_quota` (429).
This prevents the full 3-venue × 3-run acceptance evidence for Asian Arts and
Palais Lascaris. The code is ready; the constraint is billing, not correctness.

**What has been verified end-to-end (live):**
- Matisse: 8/8 stops, correct Museum Information, gate passed

**What has been verified via simulated page text (official site content):**
- Asian Arts: closed Tuesday, 10:00–17:00 (1 Sep–30 Jun) / 10:00–18:00 (1 Jul–31 Aug), FREE
- Palais Lascaris: closed Tuesday, 10:00–18:00, €5, free for Métropole residents
- All three venues: gate verifies all claims, drops fabricated ones

**Pending (needs API quota):**
- Full 3-venue × 3-run live generation with stability check
- Asian 8/8 documented works base ≥81.25 verification
- Palais ≥6 stops verification

## Files changed

| File | Change |
|------|--------|
| `visitor_facts_extractor.py` | NEW — structured extraction from LOCAL-35 + merge strategy + `fetch_visitor_info_with_provenance()` |
| `generate_tour_text.py` | Replaced visitor info section: uses LOCAL-35 extractor with provenance, falls back to old method |
| `practical_facts_gate.py` | Enhanced: 'except' closure indicator, refined "Free" vs priced admission logic |
| `tests/test_local35_visitor_facts.py` | NEW — 23 unit tests for extraction |
| `run_local35_acceptance.py` | NEW — extraction-only acceptance runner |
| `run_local39_acceptance.py` | NEW — simulated pipeline acceptance (extraction + gate) |
| `run_local39_live_acceptance.py` | NEW — live generation acceptance runner |
