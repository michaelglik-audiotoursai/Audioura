# SUBMISSION_LOCAL-411.md

## LOCAL-411: Rank and Cap Snippets

**Branch:** `kiro/local411-rank-and-cap-snippets` (off `kiro/local410-trace-the-hop`)

---

### Problem

LOCAL-410 correctly wired `search_stories_for_stop` into the real generation path
for the first time. But it injected **all** SERP results (86 snippets across 3 stops,
~30 per stop) unranked into the prompt. This re-buried the FACTS FIRST block and
the required names (`Broder`, `Fridman`) that LOCAL-408 had fixed.

The model received more material than it could use and fell back on generic phrasing.

### Solution

**New module: `snippet_ranker.py`**

Scores each snippet on story quality before injection:
- Named person (proper noun pattern): **+3**
- Verb of consequence (published, printed, met, commissioned, etc.): **+3**
- Date (4-digit year): **+2**
- Named place/institution: **+1**
- Tier1/Tier2 domain: **+1**
- Contains artist surname: **+1**
- Biography-only (LOCAL-406 Part B): **hard reject (-999)**

After scoring, snippets are sorted descending and capped at **5 per stop**
(`SNIPPET_CAP_PER_STOP`, configurable via env var).

**Changes to `generate_tour_text.py`:**
1. At snippet injection time (the `[LOCAL-402/403]` block), snippets are now
   passed through `rank_and_cap_snippets()` before building the prompt block.
2. Prompt size is reported before and after snippet injection for every stop.
3. The SERP summary reports the cap that will be applied.
4. `_all_snippet_text` for candidate-specific extraction uses the ranked list
   (not the raw `:12` slice).

### Effect on prompt size

Before (LOCAL-410): ~30 snippets × 350 chars = ~10,500 chars of snippet material per stop.
After (LOCAL-411): 5 snippets × 350 chars = ~1,750 chars of snippet material per stop.

Reduction: **~8,750 chars per stop**, putting the prompt well under 20K.
FACTS FIRST block stays at position 2 (after task statement line 1).

### Files Changed

| File | Change |
|------|--------|
| `snippet_ranker.py` | **NEW** — scoring + ranking + capping logic |
| `generate_tour_text.py` | Apply ranking at injection; prompt size reporting |
| `test_local411_rank_and_cap.py` | **NEW** — 6 tests (4 unit + 2 wiring) |

### Tests

```
test_local411_rank_and_cap.py::TestSnippetRanker::test_story_rich_snippet_scores_high        PASSED
test_local411_rank_and_cap.py::TestSnippetRanker::test_biography_only_snippet_rejected       PASSED
test_local411_rank_and_cap.py::TestSnippetRanker::test_cap_limits_output                     PASSED
test_local411_rank_and_cap.py::TestSnippetRanker::test_ranking_report_structure               PASSED
test_local411_rank_and_cap.py::TestLocal411GenerationWiring::test_generation_path_imports_snippet_ranker  PASSED
test_local411_rank_and_cap.py::TestLocal411GenerationWiring::test_search_stories_for_stop_called_on_real_path  PASSED
```

**Expected red-on-revert count: 6**

Reverting LOCAL-411 removes `snippet_ranker.py` (tests 1–4 fail on import) and the
`rank_and_cap_snippets` call in `generate_tour_text.py` (tests 5–6 fail on source inspection).

The LOCAL-410 test suite (5 tests) also passes unchanged — the search wiring is preserved.

### D307 Invariant (Required per ticket)

`test_search_stories_for_stop_called_on_real_path` verifies:
- `search_stories_for_stop` is imported inside `generate_tour_text()`
- `_s_result = search_stories_for_stop(` is called
- `_DIRECT_SNIPPETS_PER_STOP = _local410_snippets` populates the injection dict

This is the test whose absence allowed the gap to survive six rounds.

### Acceptance Readiness

The ranking and capping logic is in place. Live acceptance with the MFA tour
(`Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested)
requires `SERP_API_KEY` and a running PostgreSQL instance — to be run separately
with `run_local410_acceptance.py` or equivalent.

Expected outcomes after this fix:
- Top-5 ranked snippets contain Mourlot + 1945 + Fernand (highest-scoring stories)
- FACTS FIRST block stays at prompt position 2 (names not buried)
- Prompt size drops from ~30K to ~15K per stop
- `Broder` and `Fridman` restored via credit_line snippet (always rank 1, injected first)
