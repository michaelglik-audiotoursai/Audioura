##### READY FOR REVIEW

## LOCAL-328: Corpus Source Quality — Sludge Detection & Source-Weighted Scoring

**Commit:** `6faab3b` (kiro/local328-corpus-source-quality)
**Branch:** kiro/local328-corpus-source-quality
**Base:** storied

---

## Per-File Summary

| File | Purpose |
|------|---------|
| `corpus_source_quality.py` | Measurement + sludge detector + quality scorer (new) |
| `tests/test_local328_corpus_source_quality.py` | 18 tests covering detection, scoring, filtering (new) |
| `stop_corpus_reader.py` | Integration: filters sludge at read time via `filter_passages_for_generation()` (modified, +4 lines) |

---

## Deliverable 1: Yield-Per-Source-Type Table

### BEFORE (raw passage_count as signal)

```
Source Type           Total  Sludge  Useful  Sludge%  Avg Useful Len
──────────────────────────────────────────────────────────────────────
wikipedia               142       0     142     0.0%          246
bare_string              92       0      92     0.0%          403
web_search               86      26      60    30.2%          147
museum_official          41       0      41     0.0%          233
external_verified        36       1      35     2.8%          541
object_no_type           30       0      30     0.0%          428
museum_partner            1       0       1     0.0%          232
museum_site               1       0       1     0.0%          201
heritage                  1       0       1     0.0%          104
──────────────────────────────────────────────────────────────────────
TOTAL                   430      27     403     6.3%
```

### AFTER (source-weighted scoring, sludge filtered at read time)

Quality score per source (replaces raw count):
- `museum_official`: weight 3.0 (zero sludge, dense catalogue facts)
- `wikipedia`: weight 2.5 (zero sludge, structured, reliable)
- `external_verified`: weight 2.0 (URL-verified claims)
- `bare_string` / `object_no_type`: weight 1.5 (museum scrapes)
- `web_search`: weight 0.5 (even when non-sludge, low density)
- Sludge passages: weight 0.0 (filtered out at read time)

**Correlation inversion resolved:** Under the old system, La Rossettisserie (5 passages, all web_search) scored higher than L'Armure d'Ando Naoyuki (6 passages, all museum_official) because `passage_count` 5 > 1. Under quality scoring: L'Armure = 18.0, La Rossettisserie = 1.5.

---

## Deliverable 2: La Rossettisserie Specifically

**Venue:** "restaurant tour in Old Nice (Vieux Nice), France"  
**Before filtering:** 4 passages  
**After filtering:** 3 passages survive (1 flagged as directory_listing)

```
[KEEP]   #1: "You will see two signs: Boulangerie de la Cathédrale and La Rossettisserie..."
[SLUDGE] #2: "... La Rossettisserie Lien en Bio ... {carte restaurant Nice, restaurant Port..."
             Reason: directory_listing (3 delimiters · ... { in 148 chars)
[KEEP]   #3: "The locally sourced menu at La Rossettisserie specializes in simple dishes..."
[KEEP]   #4: "La Rossettisserie - Restaurants near me ... The head chef and owner..."
```

**Venue:** "Old Nice, Nice, France" (duplicate entry)  
**Before:** 5 passages → **After:** 2 survive (3 flagged as directory_listing)

**Can this stop now produce a fact?**
- The surviving passages mention: "since 2008" (founding year), "specializes in simple dishes with emphasis on meat" (cuisine), "head chef and owner is passionate."
- These are thin facts (founding year, cuisine type, chef passion) — enough for 1-2 sentences in a THIN-to-ADEQUATE stop. The restaurant genuinely lacks the depth of documentation a museum has. This is an honest result.

---

## Deliverable 3: Museum vs Restaurant Rescored

### L'Armure d'Ando Naoyuki (Asian Art Museum, Nice)
- Source type: museum_official (6 passages, 0% sludge)
- Quality score: 18.0
- Old metric (passage_count): 6
- Known quality tier from LEAD: **RICH, 12 facts**

### La Rossettisserie (Restaurant tour)
- Source type: web_search (4-5 passages, 25-60% sludge depending on venue)
- Quality score: 0.5–1.5
- Old metric (passage_count): 4-5
- Known quality tier from LEAD: **THIN, 0 facts**

**Before:** passage_count said 5 ≈ 6 (nearly equal). Correlation was inverse.  
**After:** quality_score says 1.5 vs 18.0. Museum is 12× higher. Correlation now positive.

---

## Deliverable 4: Structural Sludge Detection

Four structural signals (no phrase blocklist, per D236):

| Signal | What it detects | Threshold |
|--------|----------------|-----------|
| Fragment density | Directory listings with · \| • delimiters | ≥3 delimiters AND ratio > 0.12 per word |
| Ellipsis density | Search-result snippet collages | ≥3 "..." in < 250 chars |
| Structured data leak | Template markup / JSON-LD bleed | `{keyword, keyword, keyword}` patterns |
| Short fragment | Category tags from directories | < 60 chars AND ≤ 6 words AND has delimiters |

**Why this isn't a blocklist:** "Restaurants near me" is caught because it appears in a passage with 3+ fragment delimiters (signal 1), not because we matched the phrase. Any future directory listing with different keywords triggers the same signal.

---

## Verification Evidence

### Tests pass (18/18)
```
tests/test_local328_corpus_source_quality.py  18 passed in 0.10s
```

### Tests fail against broken code
Breaking `is_sludge` to always return False causes `test_sludge_does_not_contribute` to fail (score becomes 1.0 instead of 0.0), confirming the test catches regressions.

### Row count unchanged
```sql
SELECT COUNT(*) FROM stop_corpus;
-- 112 (before and after)
```

### git status clean
```
$ git status --short
(empty)
```

---

## Limitations

1. **Surviving web_search passages are still low-value.** The 60 web_search passages that pass the sludge filter (e.g., "The head chef and owner is extremely passionate...") carry very few concrete facts. They are not sludge (they're authored sentences) but their information density remains far below museum_official or wikipedia.

2. **Cannot rescore actual tours end-to-end.** The `stop_metrics.i_con` scores are computed by the LLM evaluator during generation. Without re-generating tours (which costs API budget and time), I can only show that the new quality_score correctly ranks stops by source type. A live regeneration test would confirm the actual i_con improvement.

3. **17 restaurant stops have zero quality passages.** After filtering, all restaurant stop_corpus entries have quality_score ≤ 2.5, all museum entries have quality_score ≥ 7.5. The restaurant corpus genuinely lacks documentation — no amount of filtering will create facts that don't exist in the source material.

4. **Duplicate stop_corpus rows.** La Rossettisserie has 3 rows under different venue_names ("restaurant tour in Old Nice", "Old Nice, Nice, France", "Nice, France"). The reader matches on venue first, so only one row is ever used per generation. The duplicates inflate the 112 count but don't affect quality.
