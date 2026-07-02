# Storied v2.2.0 — Content QA Results

Generated: 2026-07-01 | STORIED_MODE=true | Container: development-tour-generator-1

---

## Results Summary

| Tour Type | Location | Stops | QA Score | Cost | Time | Status |
|-----------|----------|-------|----------|------|------|--------|
| Museum | Musée National Marc Chagall, Nice | 10 | 7/8 | $0.031 | 73s | ✅ PASS |
| Walking | Beacon Hill, Boston | 8 | 7/8 | $0.022 | ~45s | ✅ PASS |
| Restaurant | North End, Boston | 8 | 7/8 | $0.022 | ~47s | ✅ PASS |
| Specialized | Harry Potter locations, London | 8 | N/A | N/A | N/A | ⚠️ GENERATION FAILED |

---

## Detailed Scores

### Museum (Chagall, 10 stops) — 7/8
- ✅ No cross-stop repetition (>0.85)
- ✅ Distinct opening sentences
- ✅ No compass bearings
- ✅ Introduction block present
- ✅ Final stop has substantial content
- ✅ Word count per stop 200-500
- ✅ Total length reasonable
- ❌ Forbidden phrases (69 matches — "vibrant colors" leaks through despite ban)

### Walking (Beacon Hill, 8 stops) — 7/8
- ✅ No cross-stop repetition (>0.85)
- ✅ Distinct opening sentences
- ✅ No compass bearings
- ✅ Introduction block present
- ✅ Final stop has substantial content
- ✅ Word count per stop 200-500
- ✅ Total length reasonable
- ❌ Forbidden phrases (12 matches — "a testament to" recurs)

### Restaurant (North End, 8 stops) — 7/8
- ✅ No cross-stop repetition (>0.85)
- ✅ Distinct opening sentences
- ✅ No compass bearings
- ✅ Introduction block present
- ✅ Final stop has substantial content
- ✅ Word count per stop 200-500
- ✅ Total length reasonable
- ❌ Forbidden phrases (14 matches — "intricate details", "a testament to")

### Specialized (Harry Potter, London) — GENERATION FAILED
- ⚠️ PHASE 3C address filter rejected ALL stops — "Harry Potter filming locations, London" doesn't match individual London addresses (e.g. "Gracechurch St, EC3V 1LT")
- Root cause: PHASE 3C city-name matching too strict for themed tours where the location string is a concept, not a geography
- **This is a Beta-era limitation, not a Storied regression** — the same address filter runs in STORIED_MODE=false

---

## Observations

1. **Forbidden phrase check** is the only consistent failure across all 3 passing tours. GPT sometimes generates banned phrases despite the DO NOT USE instruction. The de-repetition rewriter catches cross-stop copies but not per-stop first occurrences.

2. **Cost is well within budget**: $0.02–$0.03/tour vs the $0.15 ceiling. The spine ($0.02) + fact sheets add ~$0.01, keeping total well under target.

3. **Harry Potter failure** is not a Storied defect — it's a PHASE 3C address-matching limitation for themed/fictional-location tours. This exists in Beta too. Fix would require skipping PHASE 3C for `specialized` category or relaxing the address validator for themed tours.

---

## Verdict

**3 of 4 tour categories score ≥ 7/8** on content_qa_runner.py. The 4th (specialized/book) fails at generation, not at QA — a pre-existing address filter limitation unrelated to Storied features. For Aug 1 release, the 3 passing categories cover the primary use cases. The specialized tour issue is documented as a known limitation.
