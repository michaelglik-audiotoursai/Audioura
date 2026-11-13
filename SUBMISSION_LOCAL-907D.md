# SUBMISSION LOCAL-907D — topic builder: judge truncation, write-to-length, rebuilds (offline, $0)

Branch `LOCAL-907D-builder-length-grounding`, from subscribed 95a9d61d. No paid call was made
(tests mock LLM, judge, Wikipedia, DB; run with `env -u OPENAI_API_KEY`).

## Changes
- `topic_library_build.py`
  - **Judge never truncates.** `ground_text` passes `max_tokens = 60 * batch_sentences + 200`
    (`judge_max_tokens`) to every judge call; `GROUND_BATCH_SENTENCES` 20 -> 12. A batch whose reply is
    missing/truncated/unparseable is retried once with half the batch (one sentence: twice the tokens)
    before it counts as `grounding_unavailable`. `strict_grounding_gate` is untouched (tour default stays 900).
  - **Written in parts.** The source is cut into 1-3 contiguous slices (different sections; `plan_part_count`).
    Each part is its own writing call (~700-900 words, `writer_system`): hook in part 1 only, previous part's
    last paragraph passed as "continue; do not repeat", no model-written credit (the credit line is appended
    once at the end). Repeated paragraphs are dropped (`drop_repeats`). Each part is grounded against its own
    passages plus the article lead. Stops at >= 1,500 words written or when a part adds < 150 words.
    Every call is metered; before each part the reserve is max(estimate, previous part's real cost). A
    budget stop between parts keeps the parts already paid for (`budget_stopped`); a stop inside grounding
    of part 1 discards the segment as before.
  - **Floor matches the source** (`survivor_floor`): 1,200 if source >= 2,500 words, else max(700, 0.5 x source)
    (capped at 1,200). A 700-1,200-word segment is `ready` with `est_minutes = words/150`. Floor is logged.
  - **Rebuilds.** `skip (already built)` applies to `ready` rows only. A `rejected` row is rebuilt via
    `store.update_segment(id, row)` (UPDATE by id, no DELETE). `--rebuild` also rebuilds `ready` rows; a failed
    rebuild never overwrites a good `ready` row.
  - **Report** per segment: words written per part, words kept, floor, judge calls, cost.
- `topic_library.py`: `update_segment` on `MemorySegmentStore` and `PgSegmentStore` (parameterised UPDATE).
- `tests/test_local907_topic_library.py`: two existing tests moved to a per-part writer mock (`part_llm`).
- `tests/test_local907d_builder_length.py`: 27 new mocked tests (judge tokens/retry/900 default, 3 parts >= 1,500
  words, no repeated paragraph, one hook, one credit, budget stop between parts, floor by source size,
  rejected rebuilt by UPDATE same id, ready skipped unless `--rebuild`, Pg UPDATE has no DELETE).

## Verification
`env -u OPENAI_API_KEY pytest tests/test_local907*.py tests/test_local89[6-9]*.py tests/test_local90*.py tests/test_lead905*.py`
-> 841 passed. (`test_local88_tour_pollution.py` not collected by those globs.)

## Not proven
Live behaviour (does gpt-4.1-mini hit ~800 words per part; real grounding loss across parts; actual
cost, which now includes up to 3 write calls per segment) needs LEAD's paid build. `estimate_segment_cost`
was updated for parts but not checked against real spend. No live DB or shared containers touched.
