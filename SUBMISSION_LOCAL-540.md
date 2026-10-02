# SUBMISSION — LOCAL-540: Wire the scorer into the generation path

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-540-wire-scorer-into-generation`
**Base:** storied = `43d407e` (verified: `git merge-base --is-ancestor 43d407e HEAD` → 0)

---

## The problem, verified

```
$ grep -c "tour_quality" generate_tour_text.py
0
$ grep -rn "REQUIRED_CLEAN" --include='*.py' . | grep -v tests
tour_quality.py:42:REQUIRED_CLEAN = ('truncated', 'repeated', 'refuted', 'bare_death', 'distance', ...
tour_quality.py:1002:            'clean': not any(k in defects for k in REQUIRED_CLEAN)}
```

`REQUIRED_CLEAN` was read in exactly one place — the line that sets a `clean` flag
on the dict `score_tour` returns. Every caller of `score_tour` was a standalone
`run_*` measurement script. **The generation path never imported the module.** A
tour that failed every REQUIRED_CLEAN check was written, packed, cached and shipped
exactly as if it had passed. Round 9 shipped "Gustave Eiffel's iconic Control
Tower" at Boston Logan because nothing in generation was ever going to stop it.

This was `geo_refutation` again — a module that judges after the fact and gates
nothing — but across the whole defect suite.

## What changed

Two files touched, one new helper, plus tests and run artifacts.

### `scorer_retry.py` (new)
The piece that acts on a score. `score_and_retry(text, requested_stops,
is_building_tour, regenerate_section=…)`:
1. Scores the assembled tour with `tour_quality.score_tour` — the exact call the
   reference caller `run_round9.py` makes.
2. If a REQUIRED_CLEAN defect is present, attributes each offending quote to the
   section it lives in — a specific `Stop N` block when the defect is attributable
   to a stop; the whole-tour stop-1 `Orientation` preview or the `epilog` recap
   when it is a framing/mismatch defect — and regenerates **only** those sections,
   **once**, via a caller-supplied `regenerate_section` callback (one LLM rewrite
   per section, not the whole tour).
3. Re-scores, then stops. One retry, then ship. Returns before/after defect sets,
   removed/remaining lists, and the retry's cost.

The helper issues no network calls of its own; the caller owns the LLM call and
reports its token/dollar cost back through the callback.

### `generate_tour_text.py` (wired)
- Added `import scorer_retry` and a call to `score_and_retry` at the assembly
  point — **after** the tour is fully assembled, **before** the cache store, the
  file write, and the cost print/record.
- `is_building_tour = tour_category in ('museum', 'facility')` — matches
  `run_round9.py`, which passes `True` for both the facility (LOGAN) and the
  museum (CHURCH).
- The `regenerate_section` callback makes ONE targeted OpenAI chat-completions
  call (`TOUR_STORY_MODEL`, default `gpt-4o`) that rewrites only the offending
  section, instructed to drop off-itinerary places, drop unverified attributions,
  and not contradict itself while keeping the section's headers/format. Its cost is
  priced with the existing `_tour_llm_cost` and **folded into `total_cost` /
  `total_tokens` before they are printed and recorded**, so a caller reads a cost
  that already includes the retry.
- The before/after score is recorded in the generation record: a new `score`
  sub-dict on `_LAST_GENERATION_COST` (`defects_before`, `defects_after`,
  `removed`, `remaining`, `retried`, `clean_after`, `retry_cost`,
  `cost_without_retry`) and a module-level `_LAST_SCORE_RECORD`. **The defect is
  visible afterwards, not swallowed** (D577).
- The cache-HIT path (`return _cache_hit, …` at line 5852) returns far above the
  scoring block (line ~19604) — a cached tour is neither re-scored nor
  re-generated.

## Acceptance — live end-to-end run

`Boston Logan International Airport, Boston MA`, facility, 4 stops, cache disabled
(`DISABLE_TOUR_CACHE=1`), real generation. Full log: `local540_logan_run.log`;
runner: `run_local540_logan.py`; delivered tour: `TOURS_FOR_REVIEW/local540/LOGAN_1.txt`.

**The scorer ran, the defect was seen, the retry was issued** (log lines 635–644):

```
  [LOCAL-540] scorer ran on assembled tour (8584 chars, 4/4 stops)
  [LOCAL-540] defects seen: ['fabricated_attribution']
  [LOCAL-540]   fabricated_attribution [REQUIRED_CLEAN]: 1 attribution(s); unverified attribution: "constructed in 1887 by Gustave Eiffel" (no source confirms it)
  [LOCAL-540] REQUIRED_CLEAN defect present (['fabricated_attribution']) — issuing ONE retry over 1 section(s)
  [LOCAL-540] retry: regenerating orientation (stop 1) for ['fabricated_attribution']
  [LOCAL-540] retry rewrite: 789 tokens, $0.003750 (gpt-4o)
  [LOCAL-540] rescored after retry: defects ['fabricated_attribution'] -> []
  [LOCAL-540] retry removed: ['fabricated_attribution']
  [LOCAL-540] retry cleared all REQUIRED_CLEAN defects
```

**Did the retry remove the defect? Yes.** The delivered text independently
re-scores CLEAN, and the fabrication is gone from the file:

```
$ grep -n "Eiffel\|constructed in 1887" TOURS_FOR_REVIEW/local540/LOGAN_1.txt
NOT PRESENT (good)
```

All four stops survive; the rewritten stop-1 orientation keeps the format and
replaces the invented builder with factual content (Lindbergh's 1927 landing, the
1973 control-tower completion).

### Honest note on which defect fired

Live generation is non-deterministic. This run produced the Gustave-Eiffel
hallucination as a **`fabricated_attribution`** ("constructed in 1887 by Gustave
Eiffel") rather than Round 9's **`offsite_entity` + `self_contradiction`** framing
of the same "Gustave Eiffel's iconic Control Tower" fabrication. It is the same
hallucination class at the same venue, and the scorer caught it where nothing did
in Round 9. That the retry also clears the exact Round-9 `offsite_entity` +
`self_contradiction` pair is proven offline against the Round-9 evidence tour —
see `test_local540_scorer_retry.py::test_retry_clears_defects_and_tracks_cost`,
which attributes both defects to a single stop-1 orientation section and clears
both on re-score.

## Two-channel cost of the run

From `_LAST_GENERATION_COST` (the LOCAL-533 instrument), read from the module, not
parsed from the log:

| | OpenAI (per token) | Grounding (per request) | Tour total |
|---|---|---|---|
| **WITH retry** | $0.173630 (26,469 tok) | $0.140000 (4 req) | **$0.313630** |
| **WITHOUT retry** | $0.169880 (25,680 tok) | $0.140000 (4 req) | **$0.309880** |
| **retry alone** | $0.003750 (789 tok) | — (issues no grounded requests) | $0.003750 |

**One retry cost $0.003750 (789 gpt-4o tokens)** — the OpenAI-channel delta; the
grounding channel is unchanged because the retry issues no grounded requests. That
is 1.2% on top of this tour's $0.309880.

## Cache hit is untouched — $0.00, no calls

`test_local540_cache_hit_no_score.py` forces a cache hit, installs a spy over
`score_and_retry` that raises if called, and runs generation:

```
CACHE HIT: Cached Venue / facility / 4
Total API cost: $0.0000 (0 tokens)
Grounding:      $0.0000 (0 requests)
Tour total:     $0.0000
cache-hit _LAST_GENERATION_COST: {'total_cost': 0.0, 'total_tokens': 0, 'cache_hit': True, 'tour_total_cost': 0.0, 'has_score_key': False}

PASS: cache HIT returned cached tour, scorer NOT called, cost $0.00
```

The scorer is never called on a cache hit, cost is $0.00 / 0 tokens, and no score
record is attached.

## Tests

- `test_local540_scorer_retry.py` — 4/4 pass (offline). Score-only (no retry when
  no regenerator), single-orientation attribution of the Round-9 defect pair, one
  retry clears both defects + tracks cost, a clean tour triggers no retry.
- `test_local540_cache_hit_no_score.py` — pass. Cache hit: no scoring, $0.00.
- `test_local536_self_contradiction.py` — 10/10 pass (no regression in
  `tour_quality`).
- `python3 -m py_compile generate_tour_text.py scorer_retry.py` — OK.

## Files

- `scorer_retry.py` (new) — attribution + one-shot retry orchestration.
- `generate_tour_text.py` — scorer wired into the generation path; `score`
  sub-record; `_LAST_SCORE_RECORD` module global.
- `run_local540_logan.py` (new) — live acceptance runner.
- `test_local540_scorer_retry.py`, `test_local540_cache_hit_no_score.py` (new).
- `local540_logan_run.log`, `TOURS_FOR_REVIEW/local540/LOGAN_1.txt`,
  `TOURS_FOR_REVIEW/local540/LOCAL540_SUMMARY.json` — run artifacts/evidence.

Round-9 evidence tours under `TOURS_FOR_REVIEW/round9/` were not modified.
