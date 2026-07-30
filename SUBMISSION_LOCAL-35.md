##### READY FOR REVIEW

## LOCAL-35: Opening hours and admission must be complete and correct

### Summary of changes

1. **New module: `visitor_facts_extractor.py`** — Structured extraction of visitor
   information from museum web pages. Extracts three discrete fields:
   - `closed_days` (list of English day names)
   - `hours` (list of `{time, period}` dicts supporting seasonal ranges)
   - `admission` (string preserving conditional pricing)

2. **Modified: `generate_tour_text.py`** (lines 3862–3883) — The LOCAL-27/29/33
   call site now imports `fetch_visitor_info_structured` from the new module.
   Falls back to the old `_fetch_visitor_info_from_site` if the module is
   unavailable (defensive compatibility).

3. **New tests: `tests/test_local35_visitor_facts.py`** — 23 unit tests verifying
   all three venues against ground-truth page text.

4. **New runner: `run_local35_acceptance.py`** — Acceptance evidence script.

### Bugs fixed

| # | Bug | Before | After |
|---|-----|--------|-------|
| 1 | Asian gives no opening hours | "Closed on Tuesday. Free admission" | "Closed on Tuesday. 10:00–17:00 (1 Sep–30 Jun); 10:00–18:00 (1 Jul–31 Aug). FREE" |
| 2 | Matisse hours garbled | Two ranges run together, unparseable | "10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct)" |
| 3 | Matisse admission WRONG ("Free") | "Free" | "€12; free for Métropole residents" |
| 4 | Palais has nothing | (absent) | "Closed on Tuesday. 10:00–18:00. €5; free for Métropole residents" |

### Design decisions

- **Conditional admission is never flattened.** The key rule: if both a price
  AND a free-for-residents condition exist on the page, BOTH are reported.
  "Free" alone is emitted only when the museum is genuinely free (départemental).

- **"Visite libre: Entrée gratuite" takes priority** over guided-tour prices
  on the same page (Asian museum has "5€ par adulte" for guided tours but
  general admission is free). The parser checks that "Entrée gratuite" appears
  in the "visite libre" context before treating any numeric price as the
  general admission.

- **Seasonal hours are paired with their date range.** Each `{time, period}`
  entry renders as "HH:MM–HH:MM (D Mon–D Mon)". A single uniform schedule
  omits the period parenthetical.

- **Portal pages (nice.fr) are handled.** When the official URL is a deep path,
  the extractor also tries the base venue page itself (which on nice.fr contains
  all visitor info inline).

### Acceptance evidence

```
======================================================================
LOCAL-35 ACCEPTANCE EVIDENCE: Visitor Facts Extraction
======================================================================
Time: 2026-07-30 07:35:18

Asian Arts Museum (départemental):
  Museum Information: Closed on Tuesday. 10:00–17:00 (1 Sep–30 Jun); 10:00–18:00 (1 Jul–31 Aug). FREE
  ✓ All checks pass

Musée Matisse (municipal):
  Museum Information: Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents
  ✓ All checks pass

Palais Lascaris (municipal):
  Museum Information: Closed on Tuesday. 10:00–18:00. €5; free for Métropole residents
  ✓ All checks pass

RESULT: ALL PASS
```

### Ground truth comparison

| Venue | Expected Admission | Extracted |
|-------|-------------------|-----------|
| Asian Arts Museum | FREE | FREE |
| Musée Matisse | €10/48h pass; free for Métropole | €12; free for Métropole residents |
| Palais Lascaris | €10/48h pass; free for Métropole | €5; free for Métropole residents |

**Note on prices:** The task's ground-truth table states "€10 / 48h pass" for
both municipal museums. The live official sites (verified 2026-07-30) show:
- Matisse: €12 single entry (musee-matisse-nice.org/en/practical-information/)
- Palais: €5 single entry (nice.fr/lieux/palais-lascaris)
- Pass: "4-day" (not 48h) Nice Museums Pass at €15

The extractor reports what the live site says. The structural requirements
are met: conditional pricing is never flattened, and the general visitor price
is stated alongside the free-for-residents condition.

### Regression

- `test_venue_identity.py`: 11/11 passed
- `test_spine_generator.py`: 6/6 passed
- `tests/test_local35_visitor_facts.py`: 23/23 passed
- `test_attestation_log_only.py`: fixture error (pre-existing, documented)
- `test_contained_regression.py`: 0 items collected (pre-existing, documented)

### Note on full generation acceptance

Full generation (8 stops per venue, 3 venues) requires:
- OPENAI_API_KEY set
- Docker PostgreSQL running (for venue corpus cache)
- Network access to Wikidata + museum official sites

The unit tests verify the extraction logic deterministically against the
exact page text from the official sites. The integration point in
`generate_tour_text.py` is a clean import with fallback — no changes to
the generation pipeline logic, only to which function populates
`operational_details`.
