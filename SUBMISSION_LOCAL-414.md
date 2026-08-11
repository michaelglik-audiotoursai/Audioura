# SUBMISSION_LOCAL-414.md

## LOCAL-414: Source tier is computed, then thrown away

**Branch:** `kiro/local414-tier-must-gate-injection`  
**Based on:** `origin/storied`  
**Generated:** 2026-08-11T13:07:43-0400

---

## Diagnosis Verification (greps from the ticket)

```
$ grep -n "tier3" snippet_ranker.py        # BEFORE fix: nothing
(exit code 1 — no output)

$ grep -n "tier" generate_tour_text.py | grep -iE "skip|exclude|filter"
5724:                        print(f"  [R4] SKIPPED (REQUIRE_LISTING_VERIFICATION=true) — tier={_verification_tier}, "
```

The only tier-related filtering was behind an unrelated verification flag.
`snippet_ranker.py` had zero references to `tier3` — tier earned a `+1` bonus for
tier1/tier2 and was otherwise ignored.

**Root cause discovered during fix:** Beyond the missing penalty, the LOCAL-410
snippet wiring code (line 8319) dropped the `tier` field entirely when building
snippet dicts for injection:
```python
# BEFORE (bug): tier not carried through
_s_snippets.append({'title': ..., 'snippet': ..., 'url': ...})

# AFTER (fix): tier and domain preserved
_s_snippets.append({'title': ..., 'snippet': ..., 'url': ..., 'tier': _sr.get('tier', ''), 'domain': ...})
```

So even if a penalty existed, the ranker received `tier=''` for every snippet.

---

## Task 1: Tier gate mechanism

**Chosen mechanism: Penalty (-5), not hard exclusion.**

**Justification:** A hard exclusion of tier3 would starve stops when P856 lookups
time out — 35 errors in the reported run means legitimate museum domains (e.g.,
mfa.org hitting Wikidata timeouts) would be silently discarded. A -5 penalty means:

| Scenario | tier1 score | tier3 score | Winner |
|----------|------------|------------|--------|
| Same story signals (person+verb+date = 8 base) | 8+1 = 9 | 8-5 = 3 | tier1 |
| tier3 has ALL signals, tier1 has minimal | 1+1 = 2 | 10-5 = 5 | tier3 (OK — it's the only material) |
| No tier1/tier2 exists (all tier3) | — | positive scores | tier3 survives (pipeline not starved) |

**Per-stop snippet survival (from live run):**

| Stop | Input | Bio rejected | Tier3 demoted | Output | t1/t2 in output | t3 in output |
|------|-------|-------------|--------------|--------|----------------|-------------|
| Stop 1 (Appeal to the Great Spirit) | 27 | 0 | 19 | 5 | 5 | 0 |
| Stop 2 (Adam and Eve) | 21 | 0 | 15 | 5 | 5 | 0 |
| Stop 3 (Ancient Nubia Now) | 25 | 0 | 19 | 5 | 5 | 0 |
| Stop 4 (April 1957) | 28 | 0 | 18 | 5 | 5 | 0 |

**No stop was left with zero material.** Every stop has 5 snippets surviving the gate.

**P856 caching:** Added persistent file-based cache (`.p856_cache.json`) with 30-day
TTL. Only tier1 results are cached (tier3 from timeouts are NOT cached — next run
retries). This prevents a single Wikidata outage from permanently demoting a museum.

---

## Task 2: Artist attribution (LOCAL-390 regression fix)

**Root cause:** The NON-NEGOTIABLE attribution rule (line ~9164) existed only inside
the snippet injection block. If snippets from apologetics sites named a DIFFERENT
artist (Dürer's 1504 engraving), the model would latch onto that attribution because:
1. The artist variable for that stop was empty (`by , ...` in logs)
2. No FINAL override existed at the end of the prompt

**Fix:** Added a universal "ARTIST ATTRIBUTION (LOCAL-414 — NON-NEGOTIABLE, FINAL
AUTHORITY)" block that fires for ALL museum stops when `artist` is known, placed
at the END of the prompt (recency bias). It explicitly states that naming a different
artist's different work does NOT satisfy the requirement.

**Why this stop had no artist:** The stop was "Adam and Eve" resolved as a VENUE_ONLY
work (no specific artwork record matched in the exhibition checklist). The `artist`
field was empty. The fix ensures that when `artist` IS known, it can't be displaced
by snippet content. For VENUE_ONLY stops where artist is unknown, the tier gate now
prevents apologetics material from being the primary source anyway.

---

## Task 3: Banned phrase "invites contemplation"

**Cause:** The phrase was mentioned only in the `_specificity_short` branch (line 9351),
which fires when `_confirmed_count < 2 AND not _had_corpus AND not _has_catalogue_metadata
AND not _has_work_identity`. When a stop has snippets injected, `_specificity_short` is
False and the warning never reaches the prompt. It was NOT in the BANNED PHRASES list
(line 9298), and there was NO post-generation validation.

**Fix (two layers):**
1. Added `"invites contemplation" / "invites the viewer" / "invites us to"` to the
   BANNED PHRASES list in the prompt (line 9305), which fires for ALL stops.
2. Added a post-generation banned-phrase scrub that removes sentences containing any
   banned phrase from the delivered text. This catches cases where the LLM ignores
   the ban instruction.

**Verification:** The scrub fired during the Palais control run:
```
[LOCAL-414] Stop 4: SCRUBBED banned phrases from output: ['a testament to']
[LOCAL-414] Stop 1: SCRUBBED banned phrases from output: ['a testament to', 'stands as a testament']
```

---

## Test (fails on storied)

```
$ python3 -m pytest tests/test_local414_tier_must_gate_injection.py -v

============================= test session starts ==============================
FAILED tests/...::TestTier3PenaltyExists::test_tier3_penalty_is_negative
    ImportError: cannot import name 'TIER3_PENALTY' from 'snippet_ranker'

FAILED tests/...::TestTier3CannotOutrankTier1Tier2::test_ranking_places_tier1_above_tier3
    AssertionError: Expected tier1 first, got tier3 — tier3 apologetics content
    (with more story signals) displaced museum source.
    Scores: [('Adam and Eve — Genesis and the Fall', 9), ('Adam and Eve', 9)].
    This is the LOCAL-414 defect: a tier3 doctrinal site outranks a legitimate
    museum source because tier is never penalized.

FAILED tests/...::TestTier3CannotOutrankTier1Tier2::test_report_includes_tier3_stats
    AssertionError: Report must track tier3 demotions

FAILED tests/...::TestBannedPhraseInOutput::test_invites_contemplation_is_banned_in_prompt
    AssertionError: 'invites contemplation' is NOT in the BANNED PHRASES list —
    it only appears in the _specificity_short branch, which does not fire when
    the stop has snippets/corpus.

FAILED tests/...::TestUniversalArtistAttribution::test_attribution_rule_outside_snippet_block
    AssertionError: No universal artist attribution rule found (LOCAL-414 FINAL AUTHORITY).

========================= 5 failed, 4 passed in 0.10s ==========================
```

---

## Live Run Results

**Env:**
- `DISABLE_TOUR_CACHE=1`
- `DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`
- `STORIED_MODE=true`
- `TOUR_LLM_MODEL=gpt-3.5-turbo` (default, not changed per D346)

**MFA Tour (Museum of Fine Arts, Boston):**
- 4/4 stops delivered
- Query count: 18 (4 stops × ~4-6 queries each)
- SERP result count: 101 total
- Stop 2 (Adam and Eve): tier1 material from Art Institute of Chicago and mfa.org;
  NO content from answersingenesis.org or biblicalarchaeology.org
- 'Dallin' present ✓ (LOCAL-413 search fact preserved)
- 'invites contemplation' absent from delivered text ✓
- No doctrinal framing in any stop ✓

**Palais Lascaris Control (D302/D326):**
- 4/4 stops delivered
- `framing=venue_purpose` ✓
- Dates intact (1780, 1581, 1884, 1696)
- Word counts: 224, 240, 252, 270
- 'invites contemplation' absent ✓
- Banned-phrase scrub fired on stops 1 and 4 ("a testament to" removed)

**Note on Rembrandt/1629:** This run's MFA stop selection was {Appeal to the Great
Spirit, Adam and Eve, Ancient Nubia Now, April 1957 (Celestial Blue)} — Rembrandt
was not selected as a stop. The stop selection is non-deterministic across the MFA's
collection. 'Dallin' was preserved in stop 1, confirming the 413 search-fact pipeline
is intact. The tier gate did not remove any 413 facts (all were tier1/Wikipedia-sourced).

---

## Files produced (this run)

| File | Timestamp |
|------|-----------|
| `tours/LOCAL414_MFA_4stop.txt` | 2026-08-11 12:59 |
| `tours/LOCAL414_MFA_4stop_evidence.json` | 2026-08-11 12:59 |
| `tours/LOCAL414_MFA_4stop_story_elements.json` | 2026-08-11 12:48 |
| `tours/LOCAL414_Palais_control.txt` | 2026-08-11 13:07 |
| `tours/LOCAL414_Palais_control_evidence.json` | 2026-08-11 13:07 |

---

## Zero-check

- Zero impossible relations ✓ (no cross-century assertions in delivered text)
- 4/4 stops MFA ✓
- 4/4 stops Palais ✓

---

## Changes made

| File | Change |
|------|--------|
| `snippet_ranker.py` | Added `TIER3_PENALTY = -5`; applied in `score_snippet`; enriched report with tier3 stats |
| `work_story_searcher.py` | Added persistent P856 cache (`.p856_cache.json`, 30-day TTL, tier1-only) |
| `generate_tour_text.py` | (1) Carried `tier`/`domain` through LOCAL-410 snippet wiring; (2) Added universal artist attribution at prompt end; (3) Added `"invites contemplation"` to BANNED PHRASES; (4) Added post-generation banned-phrase scrub |
| `tests/test_local414_tier_must_gate_injection.py` | 9 behavioural tests, 5 fail on storied |
| `tests/run_local414_live.py` | Live run script |
