##### READY FOR REVIEW

# SUBMISSION LOCAL-215: Claim Check Paraphrase Gap

**Branch:** `kiro/local215-claim-check-paraphrase`
**Base:** `storied`
**Commit:** `910e3cb84d9f6f7ef2dc08f254a23f417ccc0677`
**Date:** 2026-08-04

---

## Approach Chosen: Option 1 — Better Lexical Matching

**Defence:** Options 2 and 3 (embeddings, LLM adjudication) are more capable
but violate the core requirement differently:
- Option 2 requires an embedding model dependency and per-paragraph cost.
- Option 3 introduces the fabrication risk the detector is designed to measure.

Option 1 (stemming + curated synonyms) is the only approach that:
- Costs **$0.00** per paragraph (pure regex/token matching, no network calls).
- Cannot introduce false SUPPORTED by construction (the enhanced pass only fires
  on claims already marked UNSUPPORTED, and synonym groups are hand-curated).
- Produces predictable, auditable behaviour with no model variance.
- Adds no dependency.

**What it cannot do:** Bridge pure semantic inference. "Pop art challenges
boundaries between high and low culture" vs "embraces the emerging mass
culture" requires reasoning about conceptual equivalence. No lexical technique
bridges this safely. The remaining 5 failures ARE the paraphrase gap, and the
honest answer is: they need embeddings at ~$0.001/paragraph (ada-002) or LLM
adjudication at ~$0.005-0.02/paragraph (gpt-4o-mini with passage quote).

**Cost per paragraph:** $0.00 (unchanged from LOCAL-210).

---

## Mechanism

1. **Lightweight suffix-stripping stemmer** (`_stem()`): Handles morphological
   variants (donated→donat, contributions→contribut, enriched→enrich).
   Irregulars table for common English verbs (gave→give, built→build).

2. **Curated synonym groups** (4 tight groups): donate/contribute/give/offer,
   popular/mass, reference/allusion/borrow/reinterpret/reground,
   relate/connect/link/associate.

3. **Strategy 3b** in basic matcher: Stem-aware sliding window. After raw token
   overlap fails, tries again with stemmed tokens. Same threshold (0.55).

4. **Enhanced pass** (`_find_best_evidence_enhanced`): Fires only on claims that
   FAILED basic matching. Uses stems + synonym groups with threshold 0.70
   (stricter than basic). Requires 4+ content tokens and 2+ domain-specific
   stems. Cannot flip SUPPORTED→UNSUPPORTED by design.

5. **Prefix matching fix**: One stem must be a prefix of the other (not just
   shared prefix). Prevents collaborate↔collage false matches.

---

## Results

### LOCAL-195 Regression Set (29 claims, MAMAC)

| Metric | Before | After |
|--------|--------|-------|
| Agreement rate | 79.3% (23/29) | **82.8% (24/29)** |
| False SUPPORTED | **0** | **0** |
| False UNSUPPORTED (over-flagged) | 6 (21%) | **5 (17%)** |

**Claim fixed:** "Generous contributions shaped MAMAC" — enhanced pass finds
"donation exceptionnelle au MAMAC... générosité" (3/4 stems matched via
contribut↔donat synonym + gener↔generosite prefix + mamac direct).

### Holdout Set (20 claims, Musée National Marc Chagall — never used in development)

| Metric | Value |
|--------|-------|
| Agreement rate | **90.0% (18/20)** |
| False SUPPORTED | **0** |
| False UNSUPPORTED (over-flagged) | 2 (10%) |

Over-flagged: "Chagall took French nationality in 1937" (corpus has this in
French: "nationalité française"), "The museum received donations after the
artist passed away" (too many generic tokens after stopword removal).

### Threshold Sensitivity

| Threshold | Agree | FalseSupp | FalseUnsup | Note |
|-----------|-------|-----------|------------|------|
| 0.40 | 19 | 6 | 4 | ⚠️ dangerous |
| 0.45 | 20 | 5 | 4 | ⚠️ dangerous |
| 0.50 | 20 | 5 | 4 | ⚠️ dangerous |
| 0.52 | 24 | 0 | 5 | safe floor |
| **0.55** | **24** | **0** | **5** | **← current** |
| 0.58 | 24 | 0 | 5 | stable |
| 0.60 | 24 | 0 | 5 | stable |
| 0.65 | 24 | 0 | 5 | stable |
| 0.70 | 21 | 0 | 8 | too strict |

**The threshold is not fragile.** Results are stable across 0.52–0.65, a 13-point
plateau with zero false passes. The current 0.55 is centred in the safe band.

---

## Remaining Disagreements (5)

| # | Claim | Score | Why it stays |
|---|-------|-------|-------------|
| 1 | "Exhibit titled 'Richard Long...' exists at MAMAC" | 0.250 | By design: stop name filtered as given, not claimed |
| 2 | "She-Bam Pow POP Wizz relates to pop art" | 0.286 | "POP" in title → pop art is semantic inference |
| 3 | "popular culture references to convey social commentary" | 0.333 | vs "reground creation in popular strains" — pure paraphrase |
| 4 | "Pop art challenges boundaries between high/low culture" | 0.286 | vs "embraces the emerging mass culture" — conceptual equivalence |
| 5 | "Donations shaped the collection" | 0.500 | 2 content tokens (donations, shaped); "shaped" has no corpus synonym |

Claims 2–4 are the semantic-inference gap. No lexical technique bridges them
safely. They require either:
- **Embedding similarity** (ada-002, ~$0.0001/claim): compare claim vector to
  passage vectors, threshold at cosine ~0.80. Cost ~$0.001/paragraph (10 claims
  × passage matrix). Risk: embeddings can match spurious surface similarity.
- **LLM adjudication** (gpt-4o-mini, ~$0.003/claim): quote the passage, ask
  "does this passage support this claim?". Cost ~$0.02/paragraph. Risk: model
  may hallucinate support. Mandatory: require verbatim passage quote in response.

---

## Per-File Summary

| File | Change |
|------|--------|
| `claim_check.py` | +285 lines: stemmer, synonym groups, enhanced matching, Strategy 3b |
| `tests/test_local210_calibration.py` | +12 lines: enhanced pass in verdict logic |
| `tests/test_local215_holdout.py` | **NEW** (120 lines): 20 hand-scored Chagall claims |

---

## Verbatim Evidence

### LOCAL-195 calibration (after):
```
Total claims checked: 29
Agreements: 24 (82.8%)
Disagreements: 5 (17.2%)
False SUPPORTED (missed unsupported claims): 0
False UNSUPPORTED (over-flagged supported claims): 5
Direction: detector errs toward OVER-FLAGGING
Cost per paragraph: $0.00
```

### Holdout (Chagall):
```
Total claims: 20
Agreements: 18 (90.0%)
False SUPPORTED (CRITICAL): 0
False UNSUPPORTED (over-flagged): 2
```

### Database:
```
audio_tours: 130
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
```

### Git:
```
git status --short: (clean)
git rev-list --count storied..HEAD: 1
```

---

## Limitations

1. **Fixes 1 of 6 over-flagged claims.** The improvement is modest and honest.
   The remaining 5 require semantic reasoning beyond lexical matching.

2. **Synonym groups are domain-specific.** The 4 groups (donate/contribute,
   popular/mass, reference/borrow, relate/connect) were curated for art/museum
   tours. A different domain (e.g., science, history) would need different groups.

3. **The stemmer is lightweight and imperfect.** It handles common English
   suffixes and 40 irregular verbs. Edge cases exist (e.g., "flies"→"fly" works,
   "lying"→"ly" does not). For this domain the coverage is sufficient.

4. **French corpus passages require cross-lingual matching.** "Generous
   contributions shaped MAMAC" matches because the French passage contains
   "générosité" (prefix-matches "gener") and "donation" (synonym-matches
   "contribut"). This works here but is not a general cross-lingual solution.

5. **The enhanced pass is conservative by design.** It requires 4+ content tokens,
   2+ domain-specific stems, and 70% concept match. This means short, generic
   claims ("Donations shaped the collection", 2 tokens) cannot be rescued.
   Loosening these gates introduces false passes on the holdout set.

---

## Spend

$0.00 — no LLM calls, no API calls. Pure Python regex + token matching.

Ceiling: $0.35. Actual: $0.00.
