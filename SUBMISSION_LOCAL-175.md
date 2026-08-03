##### READY FOR REVIEW

## LOCAL-175: Harden Anchor Metric Before Optimisation

**Commit:** `e3a9596`
**Branch:** `kiro/local175-harden-anchor-metric`
**Base:** `storied`

### Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `tests/stop_anchor_detector_v2.py` | +640 | Hardened detector with sibling discrimination + navigation classification |
| `tests/stop_anchor_v2_report.txt` | +285 | Full report output (deterministic, reproducible) |
| `SUBMISSION_LOCAL-175.md` | +this | Submission document |

### What changed vs v1

Two hardening changes, both motivated by the same principle — Michael's substitution test: "if you can substitute the names of places and say the same thing about another location, this paragraph is redundant."

#### 1. Sibling Discrimination (eliminates weak `corpus_mention` anchors)

**Problem:** v1 counted any token found via substring match in the venue's shared pages text (`all_corpus_text`) as a `corpus_mention` anchor. But that text is identical for every stop in a venue tour. Tokens like "Baroque", "Salon", "Christ", and the venue name itself appeared for every stop — they passed Michael's substitution test (say them about any stop and they're still true) but were scored as anchors.

**Fix:** `corpus_mention` is eliminated as a valid anchor type. A token is only an anchor if it comes from **stop-specific** corpus data:
- Story elements matched to this stop's artwork title (people, dates)
- Canonical titles for this stop's artwork
- The stop's specific corpus text (not shared venue pages)

Additionally, even stop-specific tokens are rejected if they appear in >50% of sibling stops' specific corpus texts (the >50% threshold means a token must be in the minority of stops to qualify as distinguishing).

**Possessive normalization:** "Chagall's" → "chagall" for sibling matching, preventing surface-form mismatches from circumventing the rule.

**Threshold justification:** 50% is the natural threshold for "majority". If a 6-stop tour has a token in 4 stops, that token cannot distinguish stop #5 from #4. The test is not whether the token is unique (too strict — would require 0 siblings) but whether it appears in a minority of siblings.

#### 2. Navigation Classification (separates wayfinding from content)

**Problem:** "As you enter the Palais Lascaris, make your way to the Grand Salon" was scored ANCHORED in v1 because it contained "Palais Lascaris" (corpus_mention). It's pure wayfinding — legitimate text that the metric should not score as storytelling.

**Fix:** New `NAVIGATION` classification, applied before anchor checking. A paragraph is NAVIGATION if:
- It matches 2+ navigation regex patterns (directional verbs + targets), OR
- It's short (<150 chars) and matches 1+ pattern, OR
- >50% of its sentences contain navigation patterns

NAVIGATION paragraphs are excluded from the scored denominator. They are reported separately (6 of 218, 2.8%).

### Michael's examples

| Example | Expected | v1 | v2 |
|---------|----------|----|----|
| Generic Cap d'Antibes prose | NO_ANCHOR | NO_ANCHOR ✓ | NO_ANCHOR ✓ |
| Fitzgerald name-drop | UNLINKED_ENTITY | UNLINKED_ENTITY ✓ | UNLINKED_ENTITY ✓ |
| "As you enter the Palais Lascaris, make your way…" | not ANCHORED | ANCHORED ✗ | NAVIGATION ✓ |

### Prevalence: v1 → v2 (same 7 tours, 218 paragraphs)

| Tour | Corpus | v1 ANCHORED | v2 ANCHORED | v2 NO_ANCHOR | v2 UNLINKED |
|------|--------|-------------|-------------|--------------|-------------|
| 1: Palais Lascaris (museum) | YES | 38.9% | **0.0%** | 41.2% | 58.8% |
| 29: French Riviera Biking | YES (thin) | 0.0% | 0.0% | 35.5% | 64.5% |
| 12: Nice walking tour | NO | 0.0% | 0.0% | 36.7% | 63.3% |
| 24: Chagall museum | YES (rich) | 70.0% | **3.3%** | 53.3% | 43.3% |
| 14: Naïve Art museum | NO | 0.0% | 0.0% | 64.4% | 35.6% |
| 46: Boston Common | YES (thin) | 0.0% | 0.0% | 25.0% | 75.0% |
| 44: MAMAC Nice | YES (rich) | 88.2% | **47.1%** | 23.5% | 29.4% |
| **GRAND TOTAL** | | **19.7%** | **4.2%** | **43.4%** | **52.4%** |

(v2 percentages exclude 6 NAVIGATION paragraphs from denominator; scored base = 212)

**Reading:** ANCHORED dropped from 19.7% → 4.2%. The 9 surviving ANCHORED paragraphs are in MAMAC (8) and Chagall (1) — tours with genuinely rich, artwork-specific corpus data where story elements tie named artists and artwork titles to specific stops.

### 9 ANCHORED paragraphs under hardened rule (all that exist)

| # | Tour | Stop | Anchor | Text excerpt |
|---|------|------|--------|-------------|
| 1 | Chagall | L'Arche de Noé | ('person', "L'Arche de Noé, Marc Chagall's") | "In the timeless work of L'Arche de Noé, Marc Chagall's interpretation…" |
| 2 | MAMAC | Richard Long… | ('title', 'Richard Long ou la sculpture en marchant.') | exhibit title referenced in quotes |
| 3 | MAMAC | She-Bam Pow POP Wizz | ('title', 'She-Bam Pow POP Wizz.') | exhibit title referenced in quotes |
| 4 | MAMAC | Tir, séance 26 juin 1961 | ('person', "Saint Phalle's") | "Niki de Saint Phalle's groundbreaking exhibit…" |
| 5 | MAMAC | Donations et dépôts | ('person', 'Nouveau Réalisme') | "surrounded by around twenty of Yves Klein's artworks…" |
| 6 | MAMAC | La mariée sous l'arbre | ('person', "Niki de Saint Phalle's") | sculpture attribution |
| 7 | MAMAC | Le Mur de Feu d'Yves Klein | ('title', "Le Mur de Feu d'Yves Klein,") | artwork title referenced |
| 8 | MAMAC | Le Village de grand-mère | ('person', 'Arman') | artist attribution |
| 9 | MAMAC | Le Village de grand-mère | ('stop_specific_mention', "Arman's") | "Arman's 'Le Village de grand-mère,' created in 1962…" |

**Human judgment:** 8/9 are genuinely distinguishing — they name an artist or artwork specific to this stop that you couldn't say about a sibling. #1 is borderline (entity extraction groups "L'Arche de Noé, Marc Chagall's" as one compound; the real anchor is the artwork title matching the stop name, which is legitimate).

### Noise floor (D22)

```
Run 1: ANCHORED=4.2%  NO_ANCHOR=43.4%  UNLINKED=52.4%  NAV=6
Run 2: ANCHORED=4.2%  NO_ANCHOR=43.4%  UNLINKED=52.4%  NAV=6
Run 3: ANCHORED=4.2%  NO_ANCHOR=43.4%  UNLINKED=52.4%  NAV=6
```

**All three runs identical. Noise floor: ZERO.**

The detector is fully deterministic — no random seed, no LLM calls, no sampling. Entity extraction uses regex and capitalization heuristics. Corpus lookup is a fixed database query. Any future change in the score represents a real change in either the metric logic or the underlying data.

### Database verification

```
audio_tours row count before: 108
audio_tours row count after:  108
Read-only: no INSERT, UPDATE, or DELETE executed
```

### Constraints honored

- ✓ No generation changes
- ✓ No container rebuilds (D48)
- ✓ No paid searches
- ✓ No DELETE FROM anything
- ✓ DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md untouched
- ✓ Read-only against the database

### Limitations

1. **ANCHORED at 4.2% is very low** — only MAMAC has rich enough stop-specific story elements to pass the hardened test. This correctly reflects the corpus quality: most tours lack per-stop grounding data. The score can only improve via better corpus data (D51's "search first, remove last" path).
2. **Entity extraction is still heuristic** — possessive forms, compound noun grouping, and sentence-boundary detection are approximate. The Chagall false positive (#1 above) comes from imperfect multi-word noun extraction.
3. **Navigation detection is pattern-based** — covers common phrasings but may miss creative wayfinding language. The 6 detected (2.8%) is likely an undercount; some mixed-content paragraphs that open with wayfinding but continue with content will not be classified as NAVIGATION.
4. **Walking tours with no corpus remain unscoreable** — Tours 12, 14 have no venue_corpus entry, so they can never have ANCHORED paragraphs regardless of quality. The metric is correct (corpus-backed anchors require a corpus) but incomplete.
5. **v1 is preserved** — `stop_anchor_detector.py` is unchanged. v2 is a new file; the original baseline can be re-run at any time for comparison.
