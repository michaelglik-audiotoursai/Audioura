##### READY FOR REVIEW

# LOCAL-177: Let the detector read stop_corpus

## Commit

```
Branch: kiro/local177-detector-reads-stop-corpus
```

## What changed

One new file: `tests/stop_anchor_detector_v2_with_stop_corpus.py`

This script imports ALL classification logic from the existing v2 detector
unchanged and adds only a **corpus lookup layer**: when a stop has a row in
`stop_corpus`, its attributed passages are prepended to the anchor-building
step before the same rules apply.

**The original detector (`tests/stop_anchor_detector_v2.py`) is unmodified.**
`git diff tests/stop_anchor_detector_v2.py` produces zero output.

## What does NOT change (D55 compliance)

- `classify_paragraph()` — imported, not modified
- `build_corpus_anchors()` — imported, not modified
- `build_sibling_corpus_texts()` — imported, not modified
- `is_navigation_paragraph()` — imported, not modified
- The 50% sibling discrimination threshold
- The NAVIGATION patterns
- The geographic self-reference exclusion
- The anchor type definitions (person, date, title, stop_specific_mention)

## What changes (input only)

- New function `get_stop_corpus_passages(venue_name, stop_title, conn)` — looks
  up per-stop passages from the `stop_corpus` table
- New function `enrich_venue_corpus_with_stop_passages()` — adds passage text as
  additional story_elements so `build_corpus_anchors` sees richer input
- New function `analyze_tour_with_stop_corpus()` — identical to `analyze_tour()`
  except it enriches the venue_corpus per-stop before feeding it to the same rules

## Results

### Side-by-side comparison (7 tours, identical set)

```
                           Mode A        Mode B       Delta
                        (venue only)  (stop_corpus)
ANCHORED                    4.2%          6.6%       +2.4%
NO_ANCHOR                  43.4%         42.9%       -0.5%
UNLINKED_ENTITY            52.4%         50.5%       -1.9%
```

### Category breakdown

| Category | Mode A | Mode B | Delta |
|----------|--------|--------|-------|
| Museums (attributable pages) | 8.3% | 12.8% | +4.6% |
| Walking/Biking (no pages) | 0.0% | 0.0% | +0.0% |

### Per-tour detail (museums with stop_corpus only)

| Tour | Mode A | Mode B | Delta |
|------|--------|--------|-------|
| Chagall (4/6 stops attributed) | 3.3% | 10.0% | +6.7% |
| MAMAC (10/10 stops attributed) | 47.1% | 64.7% | +17.6% |
| All others (0 attributed stops) | 0.0% | 0.0% | +0.0% |

### Newly anchored paragraphs (5 total)

1. **Chagall / La Bible : Abraham et Isaac** — anchored via person "Bible: Abraham"
   (was UNLINKED_ENTITY)
2. **Chagall / Le Cirque bleu** — anchored via dates 1950, 1952
   (was NO_ANCHOR — stop_corpus provided dates that distinguish this stop)
3. **MAMAC / Richard Long** — anchored via person "Niki de Saint Phalle"
   (was UNLINKED_ENTITY)
4. **MAMAC / Donations and deposits** — anchored via person "Niki de Saint Phalle"
   (was UNLINKED_ENTITY)
5. **MAMAC / Le Déjeuner sur l'herbe** — anchored via person "Jacquet" + date 2005
   (was UNLINKED_ENTITY)

## Sanity checks

```
Example 1 (generic prose):    NO_ANCHOR         ✓ PASS
Example 2 (Fitzgerald):       UNLINKED_ENTITY   ✓ PASS
Example 3 (wayfinding):       NAVIGATION        ✓ PASS
```

## Noise floor

```
Run 1: A=4.2%  B=6.6%
Run 2: A=4.2%  B=6.6%
Run 3: A=4.2%  B=6.6%
All runs IDENTICAL. Noise floor: ZERO.
```

## Coverage

- Total stops across 7 tours: 58
- Stops with stop_corpus row: 14 (24.1%)
- stop_corpus table total rows: 20
- Tours with coverage: Chagall (4/6 stops), MAMAC (10/10 stops)
- Tours without coverage: Palais Lascaris, French Riviera, Walking Nice, Naïve Art, Boston

## Constraints met

- ✓ $0.00 API spend (no LLM, no fetching, no generation)
- ✓ No container rebuilds (D48)
- ✓ No database writes (read-only)
- ✓ No DELETE FROM
- ✓ Classification rules unchanged (diff proves it)
- ✓ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md
- ✓ Both modes run over identical 7 tours
- ✓ Museums and walking areas reported separately
- ✓ Noise floor confirmed: 3 runs, identical

## Files changed

| File | Change |
|------|--------|
| `tests/stop_anchor_detector_v2_with_stop_corpus.py` | NEW — comparison script |
| `tests/report_local177_stop_corpus_comparison.txt` | NEW — full report output |
| `SUBMISSION_LOCAL-177.md` | NEW — this file |

## Limitations

1. **Coverage is low (24.1%).** Only 14 of 58 stops have stop_corpus data.
   The +2.4% aggregate lift is diluted by the 44 stops that run in
   venue-corpus-only mode (unchanged).

2. **The 7-tour set has no Matisse tour.** The Matisse museum (tour 54) has
   6 stops in stop_corpus but is not in the canonical 7-tour test set
   established in earlier rounds.

3. **One anchor is questionable.** "Bible: Abraham" is parsed as a proper
   noun from the title literal in the paragraph text — it's the artwork
   name, not an independent entity. The anchor is technically correct under
   the rule but is a self-reference rather than enriched knowledge.

4. **Passage quality varies.** Some stop_corpus passages contain navigation
   menus and header text from web scraping rather than substantive content
   (e.g., Matisse entries).

5. **The stop_corpus does not cover walking tours at all.** The attribution
   pipeline only finds passages for museum artwork stops with distinctive
   titles. The 0% → 0% result for walking areas is structural, not a
   deficiency of this round's change.
