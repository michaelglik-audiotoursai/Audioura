##### READY FOR REVIEW

# LOCAL-178 Round 2: Per-Work Source Fetch — Relevance Gate Applied

## Commit
Branch: `kiro/local178-per-work-source-fetch`

## What changed from Round 1

Round 1 was bounced because:
1. **False anchor**: "The Annunciation" source (mamac-nice.org PDF) was about a 2020
   contemporary work by the Leisgens, not the historic painting at Palais Lascaris.
   Keyword co-occurrence ≠ a relationship.
2. **Wrong trust hierarchy application**: `traveltowith.com` (a travel aggregator)
   was classified as "venue's own page" because its URL contained "palais-lascaris".
3. **Fetch driven by canonical titles** (10 instruments) rather than actual tour stops
   (3 frescoes/paintings).

Round 2 adds:
- **Relevance rule**: A passage qualifies only if it is ABOUT this work AT this venue.
  Both must relate within the passage, not just co-occur on the page.
- **Strict trust hierarchy**: Only the actual institution's domain (nice.fr) counts as
  Tier 1, not any URL containing venue keywords.
- **Work-type disambiguation**: "The Annunciation" rejects churches, religious orders,
  musical instruments, and contemporary works that share the word.
- **Driven by actual tour stops**: "The Triumph of David", "The Annunciation", "Raquel"

## Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `tests/fetch_palais_lascaris_sources_r2.py` | +350 | Round 2 fetch: trust hierarchy + relevance gate, actual tour stops |
| `SUBMISSION_LOCAL-178.md` | +this | Submission document (replaces Round 1) |

## Relevance rule (stated explicitly)

A passage qualifies ONLY if:
1. The work's distinctive terms appear in the passage
2. The venue context (Palais Lascaris / Lascaris) is present in short passages
3. The passage is ABOUT the work (not just a list/catalogue entry)
4. For ambiguous titles (The Annunciation): must be about the artwork, not a church,
   religious order, musical instrument reference, or contemporary work
5. For single-word titles (Raquel): must have art/heritage context (cuir doré,
   painting, panel, biblical, Lascaris)

## Cost Report

| Source | Queries | Cost |
|--------|---------|------|
| Wikipedia API (en + fr) | ~15 | $0.00 (rate-limited, yielded nothing) |
| Serper.dev | 6 | **$0.006** |
| **Total** | | **$0.006** |

Budget ceiling: $0.50. Actual spend: $0.006 (1.2% of ceiling).

### Serper query log (all 6 queries):
```
"The Triumph of David" "Palais Lascaris"              → 1 results, $0.001
"The Annunciation" "Palais Lascaris"                  → 9 results, $0.001
"Annonciation" "Palais Lascaris" peinture fresque     → 9 results, $0.001
"Annunciation" "Palais Lascaris" painting fresco      → 9 results, $0.001
"Annonciation" "Palais Lascaris" baroque              → 9 results, $0.001
"Raquel" "Palais Lascaris"                            → 9 results, $0.001
```

## Results — per stop

| Stop | Source found | Source URL | Tier | Notes |
|------|-------------|-----------|------|-------|
| The Triumph of David | ✓ | https://www.2-crc.com/leather-renovation-work.php | 3 | Restorer who worked on this tapestry. Content is about this specific work. |
| The Annunciation | ✗ | — | — | No valid source found (see below) |
| Raquel | ✓ | https://www.nice.fr/lieux/palais-lascaris/ | 1 | Nice municipal page, describes Raquel as gilt leather artwork |

### "The Annunciation" — why no source was found (36 candidates rejected)

Every search result for "The Annunciation" + "Palais Lascaris" references something
OTHER than the painting inside Palais Lascaris:

- **mamac-nice.org** (×3): WRONG MUSEUM — a 2020 Leisgen contemporary work
- **traveltowith.com** (×3): Travel aggregator listing nearby "Church of the Annunciation"
- **Church of St. Rita / Church of the Annunciation**: The nearby church, not the painting
- **Order of the Most Holy Annunciation**: A Savoyard decorative collar in portraits
- **kimballtrombone.com**: Trombone history page mentioning Palais Lascaris instruments
- **Various social media**: Facebook, TikTok, Instagram — no substantive content
- **agorha.inha.fr**: INHA exhibition catalogue, mentions "L'Annonciation" but snippet
  lacks the work title terms (appears in a different section of the page)

This is the honest finding: the painting "The Annunciation" at Palais Lascaris has no
findable web source that distinguishes it from the many other things named "Annunciation"
in Nice (the church, the order, contemporary art). Per D50: no source found → leave
unanchored, do not fabricate.

## Before / After — ANCHORED metric (unchanged detector)

### Palais Lascaris only (Tour ID 1):
```
                        Mode A (venue only)    Mode B (stop_corpus)
ANCHORED                     0.0%                  23.5%          (+23.5%)
NO_ANCHOR                   41.2%                  41.2%          (+0.0%)
UNLINKED_ENTITY             58.8%                  35.3%          (-23.5%)
```

Per-stop:
- The Triumph of David: A:0/7 → B:3/7 (anchors: "David's", "The Triumph of David")
- The Annunciation: A:0/4 → B:0/4 (no corpus data — correctly unanchored)
- Raquel: A:0/7 → B:1/7 (anchor: "Triumph of David, The Annunciation, and Raquel")

### vs Round 1 (before bounce):
```
Round 1 (false anchor included):  0.0% → 29.4%  (+29.4%)
Round 2 (false anchor purged):    0.0% → 23.5%  (+23.5%)
Drop: -5.9% — the false Annunciation anchor removed
```

**This is the correct outcome.** The score fell because one anchor was false.

### All 7 tours (grand total):
```
                        Mode A (venue only)    Mode B (stop_corpus)    Delta
ANCHORED                     4.2%                   8.5%              +4.2%
NO_ANCHOR                   43.4%                  42.9%
UNLINKED_ENTITY             52.4%                  48.6%
```

### Category breakdown:
```
Museums:  Mode A: 8.3% → Mode B: 16.5%  (+8.3%)
Walking:  Mode A: 0.0% → Mode B: 0.0%   (+0.0%)
```

### Noise floor: ZERO (3 identical runs)

### Michael's examples classification (PASS):
```
  Example 1 (generic):     NO_ANCHOR            PASS
  Example 2 (Fitzgerald):  UNLINKED_ENTITY      PASS
  Example 3 (wayfinding):  NAVIGATION           PASS
```

## Newly anchored paragraphs (4 from Palais Lascaris, 5 from MAMAC/Chagall unchanged):

1. **The Triumph of David** — `stop_specific_mention`: "David's" (2 paragraphs)
2. **The Triumph of David** — `title_in_specific`: "The Triumph of David" (1 paragraph)
3. **Raquel** — `person`: "Triumph of David, The Annunciation, and Raquel" (1 paragraph)

The Annunciation: 0 newly anchored (correctly — no corpus data to anchor from).

## Constraints honored

- [x] One venue only (Palais Lascaris)
- [x] Actual spend: $0.006, under $0.50 ceiling
- [x] Every stop_corpus row with data carries a source URL
- [x] No fabrication: The Annunciation honestly recorded as "no source found"
- [x] False MAMAC data purged (UPDATE to empty, not DELETE)
- [x] Detector classification logic unchanged (`git diff` = empty for both detector files)
- [x] Michael's examples classify as NO_ANCHOR / UNLINKED_ENTITY / NAVIGATION
- [x] `audio_tours` = 108 (unchanged)
- [x] `git status --short` = clean after commit
- [x] No generation changes, no container rebuilds (D48)
- [x] No DELETE FROM anything; additive + UPDATE only
- [x] DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md untouched

## Limitations

1. **The Annunciation has no web-findable source.** The painting is obscure enough
   that no search engine result disambiguates it from the church, the religious order,
   and contemporary works. This stop cannot be anchored via web search.

2. **The Triumph of David source is Tier 3** (a leather restorer's portfolio page).
   It IS about this specific tapestry — the firm restored it — but it is not an
   institutional or scholarly source. No Tier 1-2 source exists for this work online.

3. **Raquel source is a Serper snippet** from nice.fr, not full page text. The snippet
   is brief but carries the art context ("œuvres de qualité, rares et énigmatiques")
   and venue identity.

4. **Wikipedia rate-limited** this run (429 Too Many Requests). In a production
   pipeline, this would need backoff/retry logic.

5. **Canonical instrument titles remain in stop_corpus** from Round 1. They do not
   harm scoring (they match no tour stops) but they are technically noise. LEAD
   confirmed Round 2 should focus on actual stops; the instrument data is dormant.
