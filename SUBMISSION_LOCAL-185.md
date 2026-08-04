##### READY FOR REVIEW

## LOCAL-185: Narrow navigation exemption

**Commit:** `b912e09` on branch `kiro/local185-narrow-navigation-exemption`
**Files changed:** `tests/stop_anchor_detector_v2.py` (25 insertions, 12 deletions)

---

## Problem

`is_navigation_paragraph()` classified any paragraph with 2+ navigation
pattern matches as NAVIGATION regardless of length. Tour 152, Stop 2
(Musée Picasso) — a 1,445-character block of prose containing hallucinated
facts, wrong dates, and sensory fabrication — matched "Step into" (pattern 1)
and "Just ahead" (pattern 5), was classified NAVIGATION, and therefore
**excluded from anchor scoring entirely**.

## Fix

Two changes to `is_navigation_paragraph()`:

1. **Length+density guard on the 2+ patterns rule:**
   - ≤300 chars and 2+ pattern matches → NAVIGATION (unchanged behavior)
   - \>300 chars → must pass the >50% nav-sentence density gate (existing
     check at function bottom) regardless of pattern count

2. **Compass directions added to pattern 0:**
   Added `north|south|east|west|northwards?|southwards?|eastwards?|westwards?`
   so "Head south on Promenade de la Croisette" is correctly detected.

## Threshold justification

Measured length distribution of all NAVIGATION paragraphs across 7 baseline
tours + tour 152 (8 tours total):

| Length | Tour | Stop | Nav density | Genuine? |
|--------|------|------|-------------|----------|
| 102 | 14 | The Bathers | 100% | ✓ |
| 108 | 14 | The Sleeping Gypsy | 100% | ✓ |
| 130 | 1 | The Triumph of David | 100% | ✓ |
| 175 | 14 | The Flight into Egypt | 100% | ✓ |
| 333 | 12 | Promenade des Anglais | 75% | ✓ |
| **594** | **29** | **Musée Matisse** | **33%** | **✗ FALSE POSITIVE** |
| **1445** | **152** | **Musée Picasso** | **20%** | **✗ FALSE POSITIVE** |

**Cap at 300 chars:**
- All genuine ≤175-char paragraphs pass via the short rules.
- The 333-char genuine case passes via >50% density (75%).
- The 594 and 1445 false positives fail: density well below 50%.

## Before/after class counts

| Tour | Name | NAV before→after | Scored before→after | ANCHORED% | NO_ANCHOR% | UNLINKED% |
|------|------|-----------------|--------------------:|----------:|-----------:|----------:|
| 1 | Palais Lascaris | 1→1 | 17→17 | 0.0→0.0 | 41.2→41.2 | 58.8→58.8 |
| 29 | French Riviera Biking | 1→0 | 31→32 | 0.0→0.0 | 35.5→34.4 | 64.5→65.6 |
| 12 | Walking tour Nice | 1→1 | 60→60 | 0.0→0.0 | 36.7→36.7 | 63.3→63.3 |
| 24 | Musée Marc Chagall | 0→0 | 30→30 | 3.3→3.3 | 53.3→53.3 | 43.3→43.3 |
| 14 | Museum Of Naïve Art | 3→3 | 45→45 | 0.0→0.0 | 64.4→64.4 | 35.6→35.6 |
| 46 | Boston Common | 0→0 | 12→12 | 0.0→0.0 | 25.0→25.0 | 75.0→75.0 |
| 44 | Musée d'Art Moderne | 0→0 | 17→17 | 47.1→47.1 | 23.5→23.5 | 29.4→29.4 |
| **152** | **FR cycling tour** | **1→0** | **31→32** | **9.7→9.4** | **22.6→21.9** | **67.7→68.8** |

**Total paragraphs reclassified:** 2 (both from NAVIGATION → UNLINKED_ENTITY)

ANCHORED percentages moved slightly down for tours 29 and 152 because the
denominator grew by 1 (newly scored paragraph is unanchored). This is the
metric becoming honest, not a regression.

## Acceptance criteria verification

### ✓ Three real directions still NAVIGATION

```
is_navigation_paragraph("Head south on Promenade de la Croisette with views of the Mediterranean Sea.") → True  (76 chars, 1 match, <150 rule)
is_navigation_paragraph("Turn left at the fountain and continue for two kilometres.") → True  (58 chars, 1 match, <150 rule)
is_navigation_paragraph("Continue along the seafront until you reach the old harbour.") → True  (60 chars, 1 match, <150 rule)
```

### ✓ Picasso paragraph NOT navigation

```
is_navigation_paragraph(<1445-char Musée Picasso paragraph>) → False
  (2 pattern matches but len > 300; density 2/10 = 20% < 50%)
```

### ✓ Michael's two anchor examples unchanged

```
Cap d'Antibes (generic prose): NO_ANCHOR (before: NO_ANCHOR)
Fitzgerald (name-drop): UNLINKED_ENTITY (before: UNLINKED_ENTITY)
```

### ✓ Length distribution measured (see table above)

### ✓ Before/after class counts reported (see table above)

### ✓ Read-only — `git status --short` clean after commit

### ✓ No generation changes, no container rebuilds, $0.00 spend

## Limitations

- The 594-char Tour 29 Matisse paragraph was ALSO a false-positive navigation
  classification that is now correctly reclassified. This was not mentioned in
  the issue but follows from the same logic fix.
- The density gate uses sentence-splitting on `[.!?]+` which may not handle
  ellipsis (`…`) perfectly. The Picasso paragraph uses `…` as punctuation but
  Python's `re.split(r'[.!?]+', ...)` does not split on `…` (Unicode
  character U+2026). This doesn't affect correctness here because the splits
  on actual periods produce enough sentences for the density calculation.
- Pattern 0 compass directions cover the 4 cardinal directions + "-wards"
  variants. It does not cover "northeast", "southwest" etc. These are rare
  in cycling/walking tour narration and can be added if needed.
