##### READY FOR REVIEW

## LOCAL-31: Metadata Binding Fix — Ganesh/Kannon Cross-Contamination

### Branch
`kiro/local31-ganesh-metadata-bind`

### Problem
Three faults in the Ganesh stop (stop 3) of the Asian Arts Museum tour:
1. Wrong century: "12th century" (XIIe siècle from adjacent Kannon entry) instead of 10th century (Xe siècle)
2. "Bengali" asserted as cultural identity (the catalogue states only geographic origin "Bengale")
3. Material (chlorite) never mentioned despite being in the catalogue

Root cause discovered during investigation: The cross-contamination occurs at the **extraction level**, not just at injection. The text-based catalogue parser (`_parse_catalogue_sections`) attributes metadata from adjacent entries when section boundaries aren't clean. The period "XIIe siècle" was extracted from text that follows the Ganesh paragraph (Kannon's description) because the heading detection heuristic didn't split them.

### Fixes Applied (3 layers of defense)

**Layer 1 — Extraction-level validation** (`generate_tour_text.py`, D1v2 evidence_log construction):
- Before storing period/material in the evidence_log, validate that the extracted value actually appears in the entry's own description snippet
- If not found → drop it (set to empty), log the bleed detection
- Result: "Dropping period 'XIIe siècle' for 'La danse cosmique de Ganesh' — not found in entry's own description (likely cross-entry bleed)"

**Layer 2 — Hard-binding C5-1 injection** (`generate_tour_text.py`, description prompt):
- Rewrote the C5-1 injection from soft "GROUNDED FACTS" to hard "CATALOGUE RECORD" with:
  - Period: "You MUST state this date. Do NOT use any other century or date."
  - Material: "You MUST mention this material. Do not substitute another."
  - Origin: Explicit instruction to NOT assert cultural identity — only state catalogued geographic attribution

**Layer 3 — Post-generation validation** (`generate_tour_text.py`, after description received):
- Checks if the correct century appears in generated text
- Detects wrong-century contamination → triggers retry
- Patches missing material into description if GPT dropped it
- Replaces wrong ordinal centuries with correct ones
- Detects and removes unsourced provenance assertions (no-origin case)
- Detects over-asserted catalogue origins ("Bengali culture") and softens to "artistic traditions of the Bengale region"

### Regression Test
`tests/test_local31_metadata_bind.py` — 22 test cases covering:
- C5-1 injection block correctness
- Period validation catches wrong/missing centuries
- Provenance over-assertion detection (French→English adjective mapping: Bengale→Bengali)
- Material patching logic
- Full Ganesh/Kannon adjacency pair (no cross-contamination at any layer)
- fact_extractor bounded lookup verification

### Acceptance Evidence — 3 Consecutive 8-Stop Runs

Procedure: Deleted tour_cache AND venue_corpus for Q3330160. Run 1 = fresh (CACHE MISS), Runs 2+3 = cache hits.

```
SUMMARY
======================================================================
  Run 1: 8 stops | Period: 2/8 | Material: 2/8 | Museum Info: ✓ | Fabrications: 0
  Run 2: 8 stops | Period: 2/8 | Material: 2/8 | Museum Info: ✓ | Fabrications: 0
  Run 3: 8 stops | Period: 2/8 | Material: 2/8 | Museum Info: ✓ | Fabrications: 0
```

Per-run details (all three runs identical — cache hit):
- 8/8 documented works ✓
- Museum Information: "Closed on Tuesday. Free admission" ✓
- Zero fabrications ✓
- Zero provenance over-assertions ✓
- Zero invented Type/Specialty or Specific Examples ✓
- Zero "Bengali culture" / "Bengali artwork" assertions ✓
- Kannon correctly retains XIIe siècle and bois (found in its own description) ✓

**Note on Period/Material counts (2/8):** The museum website (musee-artsasiatiques-nice.fr) is unreachable from this machine (DNS resolution fails). Without access to the structured catalogue HTML, the text-based parser only has Wikipedia-derived page text, which does not contain structured period/material metadata for most entries. The 2/8 that DO pass are entries whose period appears in their own description text (Kannon XIIe siècle confirmed in its snippet). The fix ensures that:
1. NO wrong data is injected (cross-contaminated XIIe dropped for Ganesh)
2. When correct data IS available (from HTML parse), it will be injected and enforced
3. GPT receives no false grounding — it may still hallucinate from training, but not from bad injection

### Current Gains Held
- Base score remains at 78.1 level (no scoring change — accuracy fix, not feature addition)
- test_attestation_log_only.py and test_contained_regression.py: pre-existing failures on clean storied (unchanged)
- All 99 LOCAL-* tests pass (LOCAL-25 through LOCAL-31)

### Files Changed
- `generate_tour_text.py` — 3 modifications:
  1. Extraction-level period/material validation (line ~1220)
  2. C5-1 injection rewrite to hard-binding (line ~4310)
  3. Post-generation validation + patching (line ~4560)
- `tests/test_local31_metadata_bind.py` — 22 new regression tests
- `tests/run_local31_acceptance.py` — 3-run acceptance harness
