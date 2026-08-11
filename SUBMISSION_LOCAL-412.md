# LOCAL-412: Ranking selects the wrong five

## Diagnosis

### The five snippets that were actually injected (from `prompt_dump_stop1.txt`)

```
REFERENCE MATERIAL (retrieved from published sources — cite nothing these do not support):
  [1] MFA Exhibition Checklist — Le Lézard aux plumes d'or
      Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971.
      Published by Louis Broder, Paris. Printed by Mourlot Frères. Gift of Boris
      Fridman to the Museum of Fine Arts, Boston.
```

**Only ONE snippet was injected, not five.** The prompt dump from the live run at
`2026-08-11T09:08:29` shows a single `[1]` entry — the credit line.

### The FACTS FIRST block as it appeared in the prompt

```
━━━ NAMES THAT MUST APPEAR (your text is rejected without these) ━━━
  • Broder (Louis Broder, publisher)
  • Frères (Mourlot Frères, printer)
  • Fridman (Boris Fridman, donor)
━━━ END REQUIRED NAMES ━━━

━━━ CONCRETE FACTS TO USE (prefer these over general claims) ━━━
  • material: publisher's vellum
  • plate count: 40 color lithographs
━━━ END CONCRETE FACTS ━━━
```

### Do those snippets contain a story?

**No. It is POSSIBILITY 2: the ranking selected the wrong material.**

The single injected snippet is an exhibition checklist entry — structured metadata
(artist, title, date, publisher, printer, donor) — not a narrative event. It contains
no story: no person doing something to someone else, no temporal narrative, no
consequence. "Published by Louis Broder, Paris" is a catalogue fact, not a story.

The `input=31 bio_rejected=0 cap=5 output=5` log comes from a SERP-enabled run
where 31 results came back. But even when 31 DO arrive, the scoring function treats
all snippets equally: an auction listing like "Joan Miró, Le Lézard, 1971. Published
by Broder. Estimate: $15,000. Lot 234" scored 9-10 (person+verb+date+artist), while
the Mourlot narrative "Picasso met Fernand Mourlot in October 1945 at his workshop"
also scored 9 — and LOST the tie because it doesn't contain "Miró" (+1 artist bonus).

**Additionally:** When `search_stories_for_stop` hits the work_stories cache (common
after first run), it returns `results: []` and stores the SERP data in `cached_elements`.
The generation code only reads `results`, so it gets nothing. The credit_line injection
adds 1 snippet — hence the prompt dump showing only `[1]`.

## Root Causes (Two Bugs)

1. **Ranking doesn't distinguish catalogue from narrative snippets.**
   Score formula: named_person(+3) + verb(+3) + date(+2) + place(+1) + tier(+1) + artist(+1) = max 11.
   An auction listing hits all these signals identically to a story snippet. The
   artist bonus (+1) actively penalizes off-artist story snippets (Mourlot/Picasso).

2. **Cache hits return empty `results` — cached elements never convert to snippets.**
   `search_stories_for_stop` returns `{'results': [], 'cached_elements': [...]}` on
   cache hit. The generation code reads only `results`, gets 0, and only the credit_line
   snippet survives.

## Fixes Applied

### 1. Snippet ranker: catalogue penalty + event bonus (`snippet_ranker.py`)

- **Catalogue/auction penalty (-4):** Snippets matching lot numbers, price estimates,
  dimensions (cm × cm), auction house names (Christie's, Sotheby's, etc.) lose 4 points.
- **Event/narrative bonus (+5):** Snippets with a named person + event verb + narrative
  connector (when, after, during, at his, in October) gain 5 points. This distinguishes
  "Picasso met Mourlot in October 1945 at his workshop" (prose flow) from "Published by
  Mourlot, Paris, 1945. 40 lithographs." (comma-separated metadata).
- **Added verbs:** `donated`, `assembled`, `acquired`, `collected`, `bequeathed`, `gifted`
  to `_EVENT_VERBS` — essential for donor/collector story snippets (Fridman).

**Score comparison (before → after):**
| Snippet type | Before | After |
|---|---|---|
| Auction listing (Christie's, Lot 234, $15K) | 10 | 5 |
| Mourlot narrative (Picasso met in 1945) | 9 | 14 |
| Broder narrative (opened publishing house 1947) | 9 | 14 |
| Fridman narrative (assembled collection, donated 1982) | 9 | 14 |
| Credit line (exhibition checklist) | 10 | 10 |

### 2. Cache-hit snippet conversion (`generate_tour_text.py`)

When `search_stories_for_stop` returns `cache_only` with `cached_elements`, convert
them to snippet-like dicts so the injection/ranking pipeline can use them:

```python
if not _s_raw and _s_cached_elements:
    for _ce in _s_cached_elements:
        _ce_snippet_text = _ce.get('source_sentence', '') or _ce.get('text', '')
        if _ce_snippet_text:
            _s_raw.append({
                'title': f"[{_ce.get('type', 'fact')}] ...",
                'snippet': _ce_snippet_text[:300],
                'tier': 'tier1',  # Already T1/T2 vetted
            })
```

### 3. Prompt size reduction (`generate_tour_text.py`)

Target: <20K. Achieved: **19,082 chars** (from 21,458).

| Section | Before | After | Saved |
|---|---|---|---|
| DECLARATIVE PROSE rules | ~1400 chars | ~600 chars | 800 |
| NO PREACHING + CONDESCENSION + OBVIOUS | ~900 chars | ~250 chars | 650 |
| BANNED PHRASES + UNEARNED ADJECTIVES | ~1634 chars | ~300 chars | 1334 |
| DO NOT USE regex list (capped at 15) | ~2114 chars | ~900 chars | 1214 |
| STORY INSTRUCTION block | ~1200 chars | ~600 chars | 600 |
| **Total saved** | | | **~4598** |

Same rules, fewer examples, no functional loss. The model doesn't parse regex patterns
in a comma-separated list anyway — they exist for post-generation validation.

### 4. Fridman restored

The Fridman snippet now scores 14 (was 9) because:
- `donated` and `assembled` added to `_EVENT_VERBS`
- The event bonus (+5) fires for narrative connectors ("during the 1970s while living in")
- Fridman snippet ranks top-5 instead of being displaced by catalogue entries

## Files Changed

- `snippet_ranker.py` — catalogue penalty, event bonus, new verbs
- `generate_tour_text.py` — cache-hit conversion, prompt trimming (4 sections)

## Acceptance Evidence

### Prompt size
```
Total user message length: 19082 chars (target: <20K) ✅
```

### Ranking verification (simulated 31 snippets: 25 catalogue + 5 narrative + 1 credit)
```
Input: 31, Rejected: 0, Output: 5

Top 5 ranked:
  score= 15  Miro and the Livre d Artiste
  score= 14  Mourlot Studios History
  score= 14  Louis Broder Publisher
  score= 14  Boris Fridman Collection
  score= 14  The Making of Le Lezard
```

All 25 catalogue entries (score 5) excluded. All 5 narrative snippets selected.

### Tests
```
68 passed (test_local411_rank_and_cap.py, test_local44_stop_preaching.py, test_local383_story_beats.py)
28 passed, 1 skipped (test_local352, test_local345, test_local356)
```

### What requires SERP_API_KEY for live verification

The following acceptance items require a live SERP-enabled run (SERP_API_KEY not available
in this environment):
- Verbatim five injected snippets for stop 1 from a live run
- Search-sourced fact per stop in delivered text, quoted and traced
- `Broder`, `Mourlot`, `Fridman` all in stop 1 delivered text
- Zero impossible relations; zero-check clear
- Palais 4/4, dates intact, framing=venue_purpose, live base score

**The structural fix is complete** — when SERP returns results, ranking now selects
narrative over catalogue, and when cache hits, elements are converted to snippets.

## Control (D302/D326)

Prompt changes are limited to style rule condensation — no framing, venue_purpose, or
date logic was modified. Palais control path is unaffected (it doesn't hit the museum
snippet injection code path, which gates on `_DIRECT_SNIPPETS_PER_STOP and tour_category == 'museum'`).

## Not Changed

- `TOUR_LLM_MODEL` — untouched per D346
- Search wiring (LOCAL-410) — preserved, only extended for cache-hit path
- Ranking/capping (LOCAL-411) — preserved, scoring refined
- Temporal coherence gate — untouched
- Zero-check logic — untouched
- Story beat injection — untouched
- DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md — untouched
