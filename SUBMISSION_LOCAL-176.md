##### READY FOR REVIEW

## LOCAL-176: Per-Stop Corpus Attribution

**Commit:** `7431400`
**Branch:** `kiro/local176-per-stop-corpus-attribution`
**Base:** `storied`

### Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `tests/stop_corpus_attribution.py` | +340 | Attribution pipeline: splits venue page text into passages, attributes to stops |
| `migrations/local176_stop_corpus.sql` | +21 | Additive DDL: `stop_corpus` table with unique(venue_name, stop_title) |
| `SUBMISSION_LOCAL-176.md` | +this | Submission document |

### Attribution method

For each venue with tours, the pipeline:

1. **Extracts key terms** from each stop title (stripping accents, apostrophes, splitting compounds)
2. **Computes venue-wide terms** — words appearing in >50% of a venue's pages (e.g., "yves", "klein" at MAMAC). These cannot distinguish stops and are excluded from matching.
3. **URL-maps pages to stops** — pages whose URL slug matches a stop's distinctive terms are attributed wholesale (e.g., `/collection/objet/les-amoureux-en-vert` → stop "Les amoureux en vert")
4. **Passage-level attribution** — for non-URL-mapped pages, splits text into paragraphs and attributes if ≥2 distinctive (non-venue-wide) terms from the stop title appear

A passage is attributed to a stop if it names the work, its artist (not venue-wide), a distinctive date, or its subject — the same principle as Michael's anchor test applied in reverse.

### Attribution results

| Venue | Stops | Attributed | Passages | Failure rate |
|-------|-------|-----------|----------|--------------|
| MAMAC | 10 | 10 | 59 | 0% |
| Chagall | 6 | 4 | 8 | 33% (L'Exode, King David got 0) |
| Matisse | 8 | 6 | 10 | 25% |
| Palais Lascaris | 3 | 0 | 0 | 100% |
| Walking areas (6 venues) | 40 | 0 | 0 | 100% |

**Failure rate (titles with no passage): 47/67 = 70%**

Failures fall into two categories:
- **Walking areas** (40 stops): pages are venue-level prose about cities/parks with no per-stop content. Expected.
- **Museum stops not mentioned in pages** (7 stops): pages exist but never name these works (Palais Lascaris paintings aren't in the Wikipedia instrument lists; Chagall's "L'Exode" and "King David" aren't in the collection pages fetched).

### Migration SQL (additive only)

```sql
CREATE TABLE IF NOT EXISTS stop_corpus (
    id SERIAL PRIMARY KEY,
    venue_name TEXT NOT NULL,
    stop_title TEXT NOT NULL,
    passages_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    passage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(venue_name, stop_title)
);
CREATE INDEX IF NOT EXISTS idx_stop_corpus_venue ON stop_corpus(venue_name);
CREATE INDEX IF NOT EXISTS idx_stop_corpus_stop ON stop_corpus(stop_title);
```

### v2 detector measurement: BEFORE vs AFTER

**Result: 4.2% → 4.2%. No change.**

| Tour | Type | v2 BEFORE | v2 AFTER |
|------|------|-----------|----------|
| 44: MAMAC | museum | 47.1% | 47.1% |
| 24: Chagall | museum | 3.3% | 3.3% |
| 1: Palais Lascaris | museum | 0.0% | 0.0% |
| 14: Naïve Art | museum (no corpus) | 0.0% | 0.0% |
| 29: French Riviera Biking | walking | 0.0% | 0.0% |
| 12: Nice walking | walking | 0.0% | 0.0% |
| 46: Boston Common | walking | 0.0% | 0.0% |
| **GRAND TOTAL** | | **4.2%** | **4.2%** |

**Museums separately:** 8.3% → 8.3% (9/108 content paragraphs ANCHORED, all in MAMAC+Chagall)
**Walking areas separately:** 0.0% → 0.0%

### Why the score did not move

The v2 detector (`stop_anchor_detector_v2.py`) reads per-stop corpus data from `venue_corpus.story_elements_json` and `venue_corpus.canonical_titles_json`. It explicitly excludes shared `pages_json` text from anchor qualification (the LOCAL-175 hardening change that eliminated `corpus_mention`).

The new `stop_corpus` table stores per-stop passages, but **the detector does not read it**. The constraint "do not modify `stop_anchor_detector_v2.py`" means this data cannot influence the score this round.

This is an architectural gap: the data now exists per-stop, but the detector's data path is `venue_corpus` → `build_corpus_anchors` → classify. Adding a `stop_corpus` read path requires modifying the detector.

### Michael's examples — unchanged

```
Example 1 (generic prose): NO_ANCHOR ✓
Example 2 (Fitzgerald name-drop): UNLINKED_ENTITY ✓  
Example 3 (wayfinding): NAVIGATION ✓
```

Three runs identical. Noise floor: ZERO.

### What this means for round 4

The per-stop data EXISTS (77 passages across 20 stops). To make the score move:

**Option A — Detector reads stop_corpus (smallest change):** Add a `stop_corpus` lookup in `build_corpus_anchors` so that per-stop passages contribute people/dates/facts to the anchor pool. The sibling discrimination logic already prevents venue-wide tokens from counting. This is a detector change → must be a separate round.

**Option B — Backfill story_elements per stop:** Write the attributed passages as synthetic story elements into `venue_corpus.story_elements_json`, keyed per-work. This modifies existing data → violates additive-only.

**Option C — Fetch per-work sources for gaps:** The 70% failure rate means most stops have no attributable page text. Palais Lascaris paintings, Chagall's biblical series, walking tour landmarks — these need per-work web searches (STORY_QUALITY_DESIGN.md SQ-S1 through SQ-S4). This requires paid API calls.

**Recommendation:** Option A first (detector change, $0.00), then Option C for the remaining gaps (paid search for stops that still score 0 after A).

### Database verification

- `audio_tours` row count: **108** (unchanged)
- `stop_corpus` rows: 20 (new table, all INSERTs)
- No DELETE, no UPDATE to existing tables
- No DROP

### Constraints honored

- ⛔ No paid API calls: **$0.00 spent**
- ⛔ No web fetching: all data from existing `venue_corpus.pages_json`
- ⛔ No generation changes
- ⛔ No container rebuilds
- ⛔ No DELETE FROM anything
- ⛔ `tests/stop_anchor_detector_v2.py` unmodified
- ⛔ DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md untouched

### Limitations

1. **Score did not move** — correctly reported as finding, not as failure
2. **70% of stops got no passages** — pages are venue-level prose that doesn't mention individual works
3. **Walking areas are unattributable** — their pages are about cities/parks, never individual stops
4. **Palais Lascaris is unattributable** — Wikipedia pages list instruments, but the tour stops are paintings (Triumph of David, Annunciation, Raquel) not mentioned in those pages
5. **Attribution quality is unverified by the metric** — the passages look correct to a human reader but cannot be validated mechanically until the detector reads stop_corpus
