# SUBMISSION_LOCAL-423.md

## What was delivered

LOCAL-423 implements Michael's algorithm Steps 2-4 (verification before selection)
and integrates it into the production pipeline.

### New files:
- `story_verifier.py` — claim extraction, corpus verification, entity disambiguation,
  self-contradiction detection
- `test_local423_verified_stories.py` — 18 tests binding to production call sites
- `EVIDENCE_LOCAL-423.md` — claim → snippet → URL mapping from live runs

### Modified files:
- `generate_tour_text.py` — verification step after story gate (strips unsourced
  claims), VERIFICATION CONSTRAINT in prompt, fixed "Boston collector" example
- `work_story_searcher.py` — Michael's Step 2 query shape (visitor-facing framing)
- `test_local421_story_per_stop.py` — fixed "Boston-based" fixture (was unsourced)

### Cherry-picked:
- LOCAL-422's `resolve_final_description` refactoring (merged cleanly)

## What works

1. **Claim verification** — every factual claim (numbers, dates, locations, attributions)
   is checked against retrieved snippets before delivery
2. **Entity disambiguation** — Fridman-Mintz (linguist) and Fridman Gallery (NYC)
   correctly excluded; only the collector kept
3. **Self-contradiction detection** — "15 lithographs" + "40 lithographs" = automatic
   rejection (the lithograph-count bug is now impossible)
4. **Unsourced claim stripping** — sentences with unsourced claims are removed from
   delivered text
5. **Michael's query shape** — queries framed as visitor-facing story requests
6. **Prompt constraint** — LLM warned that unsourced claims will be stripped

## What does NOT work (blocking — needs Michael's decision)

**GPT-3.5 cannot produce ≥3 sourced story sentences per stop.**

Across two consecutive `run_mfa_unbound_eval.py` runs:
- Story gate: 0-2 story sentences (required: 3)
- The model generates evaluative fluff, not narrative
- When it does name people, it embeds them in evaluation rather than story

The verification infrastructure is correct — it catches and strips unsourced claims.
But gpt-3.5 cannot generate the sourced stories the verification is designed to
protect. Per D354: retrieval is no longer the bottleneck; model capability is.

**Michael decides whether to switch models.**

## Acceptance criteria status

| Criterion | Status |
|-----------|--------|
| Two consecutive runs, all 3 stops ≥3 story sentences | ❌ BLOCKED by gpt-3.5 |
| Every claim maps to source URL (evidence file) | ✓ `EVIDENCE_LOCAL-423.md` |
| At least one rejected candidate with reasons | ✓ (Boston-based, 15-vs-40) |
| No self-contradiction possible | ✓ (`detect_self_contradictions`) |
| Fridman not described as Boston-based without source | ✓ (location_descriptor check) |
| Entity disambiguation (linguist + gallery excluded) | ✓ (3 snippets excluded in live run) |
| Test red on storied, green with fix | ✓ (`test_snippet_block_contains_verification_constraint`) |
| Control: Palais 4/4, dates, framing=venue_purpose | Not re-run (blocked) |

## Files produced by live runs

- `TOUR_MFA_UNBOUND_EVAL.txt` — delivered tour text (run 2)
- `prompt_dump_stop1.txt` — literal prompt sent to LLM for stop 1
- `EVIDENCE_LOCAL-423.md` — full claim verification evidence
