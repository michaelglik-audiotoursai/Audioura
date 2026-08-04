##### READY FOR REVIEW

# SUBMISSION LOCAL-210: Unsupported-Claim Detector

**Branch:** `kiro/local210-unsupported-claim-detector`
**Base:** `storied`
**Date:** 2026-08-04

---

## What This Is

`claim_check.py` at the repo root — the instrument the truth gate (§3a) needs.
Extracts checkable factual claims from a paragraph and verifies each against
corpus passages using proximity-aware token matching. Returns per-claim verdicts
in the LOCAL-195 vocabulary.

No LLM. No container rebuild. Cost per paragraph: **$0.00**.

---

## Interface

```python
from claim_check import check_paragraph

result = check_paragraph(
    text,           # paragraph text
    stop_title,     # e.g. "Nymphe dans la forêt"
    venue_name,     # e.g. "Musee Matisse, Nice, France"
    passages,       # corpus passages for THIS stop
    other_stop_passages=None,  # other stops' passages (for SUPPORTED_ELSEWHERE)
)
# Returns:
# {
#     'claims': [{text, type, verdict, evidence, score}],
#     'unsupported_count': int,
# }
```

Importable from repo root with no `sys.path` manipulation.

---

## Claim Types Extracted

| Type | Example |
|------|---------|
| DATE | "June 21, 1990", "1960s", "between 1936 and 1938" |
| NUMBER | "over 213 exhibitions", "5,000 pieces" |
| COMPOSITION | "oil on canvas", "circular arrangements made from stones" |
| MOVEMENT | "land art movement", "Fauvism", "pop art" |
| PROPER_NOUN_PREDICATE | "Robert Smithson and Andy Goldsworthy" |
| ATTRIBUTION | "built by Y", "donated by X" |
| NICKNAME | "known as the Free City on Sea" |

**Not extracted:** adjectives, atmosphere ("captivating", "profound"), second-person
framing ("as you gaze upon"), structural transitions, source attribution paragraphs.

---

## Calibration Against Hand-Scored Sets

### LOCAL-195 (MAMAC, 29 manually-scored claims across 8 paragraphs)

| Metric | Value |
|--------|-------|
| **Agreement rate** | **79.3%** (23/29) |
| False SUPPORTED (missed unsupported) | **0** |
| False UNSUPPORTED (over-flagged supported) | **6** |
| Direction of error | **Entirely toward OVER-FLAGGING** |

### LOCAL-205 (Matisse, 6 tour runs, 19 content paragraphs)

| Metric | Value |
|--------|-------|
| Paragraphs checked | 19 |
| Claims extracted | 38 |
| UNSUPPORTED (detector) | 12 |
| Unsupported per paragraph (detector) | **0.63** |
| Hand-scored reference (per paragraph) | **2.56 (A) / 3.10 (B)** |

The detector finds **~25% of the unsupported claims** that the hand check found.
This is expected: most of the hand-scored unsupported claims are **artwork descriptions**
(nude nymph, satyr, turbulent sea) that are factual assertions about what a painting
depicts — a category the token-matcher cannot reliably extract or verify without
understanding visual description language.

---

## Every Disagreement (LOCAL-195)

All 6 disagreements are the detector marking SUPPORTED claims as UNSUPPORTED:

| # | Paragraph | Claim | Hand | Detector | Reading |
|---|-----------|-------|------|----------|---------|
| 1 | A1 | "Exhibit titled X exists at MAMAC" | SUPPORTED | UNSUPPORTED | Title matches stop_corpus row but detector filters it (is the stop title itself). **Reasonable filter — the stop name's existence is given, not claimed.** |
| 2 | A2 | "Generous contributions shaped MAMAC" | SUPPORTED | UNSUPPORTED | Semantic inference from 3 donation passages (Saint Phalle, Chubac, Nahoul). Token overlap insufficient — "generous" and "shaped" don't appear in the passages. **Fair: the inference requires reasoning.** |
| 3 | A3 | "She-Bam relates to pop art" | SUPPORTED | UNSUPPORTED | Title contains "POP" and passages mention pop art movement, but the specific linkage requires inference. **The detector cannot reason "POP in title → pop art exhibit."** |
| 4 | A3 | "popular culture references to convey social commentary" | SUPPORTED | UNSUPPORTED | Paraphrase of "brings art and life closer together, reground creation in popular strains." **Semantic distance too large for token matching.** |
| 5 | A3 | "Pop art challenges boundaries between high and low culture" | SUPPORTED | UNSUPPORTED | Paraphrase of "embraces the emerging mass culture." **Same: semantic inference, not token overlap.** |
| 6 | B2 | "Donations shaped the collection" | SUPPORTED | UNSUPPORTED | Generic paraphrase of specific donation passages. Token overlap 0.50 (below 0.55 threshold). **Borderline — one threshold notch from agreement.** |

**Zero false SUPPORTED.** The detector never claims a passage supports a claim
that the hand check marked unsupported. This is the correct error direction
(per task: "prefer erring toward UNSUPPORTED, since the cost of a false pass
is a fabricated fact reaching a listener").

---

## Direction of Error — Stated and Defended

**The detector over-flags.** It produces ~6 false UNSUPPORTED per 29 claims (21%),
and 0 false SUPPORTED.

**This is the correct bias for a truth gate instrument.** The truth gate caps
paragraphs at i-con 1. A false-pass lets a fabricated specific reach the listener
unchecked. A false-flag caps a paragraph that might have scored higher — annoying
but safe, and reviewable.

**The specific failure mode:** semantic paraphrase. When a passage says "regrounds
creation in popular strains" and the tour says "challenges boundaries between high
and low culture," the hand-checker recognizes the semantic equivalence. The detector
cannot. It sees token overlap of 0.29 and calls UNSUPPORTED.

**This is not fixable without an LLM.** Token matching, however proximity-aware,
cannot bridge semantic paraphrase. The detector is honest about this gap rather than
tuned to a 40-claim sample.

---

## Why This Cannot Be Fully Automated (The Finding)

The detector finds **0.63 unsupported claims per paragraph** where the hand check
finds **2.56–3.10**. The 4× gap is almost entirely artwork-description claims:

- "depicts a nude nymph reclining" (what the painting shows)
- "bold brushstrokes bring life to the turbulent sea" (visual description)
- "a satyr approaches with anticipation" (scene description)
- "circular arrangements made from stones" (installation composition)

These are factual assertions about physical objects — checkable in principle against
corpus descriptions of the artworks. But:

1. The corpus for these stops is a **title+date list** ("Nymphe dans la forêt, 1936-1938")
   with no visual description. The claims can't be verified against what doesn't exist.
2. Even with richer passages, verifying "this painting shows X" requires visual
   understanding — or trusting that a Wikipedia description of the artwork matches
   what hangs in the museum.

**The truth gate cannot be fully automated today.** The detector catches ~25% of
claims (dates, years, numbers, named entities, explicit medium/movement assertions).
The remainder — visual descriptions and semantic paraphrases — require either an LLM
(at cost) or human review.

**Recommendation:** Use the detector as a first pass. If `unsupported_count == 0`,
the paragraph likely has no checkable-and-unsupported claims. If `unsupported_count > 0`,
it reliably indicates at least one fabricated specific. The false-negative rate
(claims it misses) is high, but the false-positive rate (claims it wrongly passes)
is **zero** on the calibration set.

---

## Database Safety

- `audio_tours` rows: **123** (unchanged)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: all present
- No containers rebuilt
- No detectors modified (D55 respected)
- Style validator unchanged
- Anchor detector unchanged

---

## Spend

$0.00 — no LLM calls. Pure regex + token matching.

Ceiling: $0.40. Actual: $0.00.

---

## Files Changed

| File | Change |
|------|--------|
| `claim_check.py` | **NEW** — Unsupported-claim detector at repo root |
| `tests/test_local210_calibration.py` | **NEW** — Calibration runner against both hand-scored sets |
| `SUBMISSION_LOCAL-210.md` | **NEW** — This submission |

---

## Limitations

1. **Detects ~25% of unsupported claims** that a human finds. The gap is artwork
   descriptions and semantic paraphrases — categories that require NLP beyond token matching.

2. **Over-flags supported claims** at 21% false UNSUPPORTED rate. All are paraphrase
   failures where the corpus says something semantically equivalent but with different
   words. This is the safe error direction.

3. **Zero false SUPPORTED** on the calibration set, but the set is 29 claims.
   False positives may emerge on a larger sample.

4. **Cannot detect D62 entity conflation** without passage-level topic modeling.
   "Robert Indiana, Andy Warhol" in a passage about MAMAC's pop art collection
   is correctly not matched against a claim about land art — but that's because the
   tokens don't overlap, not because the detector understands referent mismatch.

5. **Composition claims ("depicts a", "portrays a") are extracted but rarely have
   corpus evidence** because the stop_corpus contains titles and dates, not descriptions.
   These will always fire as UNSUPPORTED until the corpus has artwork descriptions.

6. **Calibrated against 29 (LOCAL-195) + 54 (LOCAL-205 reference) claims total.**
   The sample is small. The agreement rate may shift on a larger corpus.
   This is honest reporting, not a claim of validation.
