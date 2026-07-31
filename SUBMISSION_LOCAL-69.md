##### READY FOR REVIEW

# LOCAL-69 — Meter the News Path

## Cost Model Finding

LOCAL-60's claim that the news path is "TTS only" is **partially wrong**.

**Paid components identified by tracing `news-generator-1` → `news-processor-1`:**

| Component | Service | When | Rate |
|---|---|---|---|
| **Polly TTS** | `news_processor_service.py` via `polly-tts-1:5018` | Always — multiple audio segments per article | $4.00 / 1M chars |
| **LLM (GPT-3.5-turbo)** | `news_processor_service.py` → `voice_control:5008` → `voice_nlp_service.py` | Conditional — only when extracted title > 12 words | $0.002 / 1K tokens |
| Article extraction | None (text arrives pre-extracted from client/newsletter) | — | $0.00 |
| Search API | None (news path does not use Serper) | — | $0.00 |

**Dominant cost is TTS.** A typical article costs $0.006–$0.030 depending on length,
with LLM adding $0.0003 when triggered. Compare: a tour costs $0.069.

## What Was Built

1. **`record_operation`** wired into `news_orchestrator_service.py` after successful
   generation — records `news_generate` with real cost and component breakdown.

2. **Cost formula:**
   - TTS chars = `min(len(article_text), 5000) + 1200 + major_points × 400`
   - TTS cost = TTS chars × $0.000004
   - LLM cost = $0.00032 (if title > 12 words) or $0.00 (otherwise)
   - Total = TTS + LLM

3. **Human-readable description** stored in new `cost_ledger.description` column:
   `"Article: <headline>"` — uses original `request_string` from the caller.

4. **Migration 007** adds `description VARCHAR(256)` to `cost_ledger`.
   `_ensure_table()` updated for dev-convenience auto-migration.

## Cache Semantics

**There is NO cache layer for news articles.** Each `/generate-news` call creates a
fresh `article_id` and generates from scratch, even if identical text was processed
before. The download path (`/download/<article_id>`) is a simple DB fetch (free), but
there's no deduplication at generation time.

**Proposed follow-up:** Add article-text hash deduplication at the orchestrator.
Before generating, hash `article_text` and check `news_audios` for an existing match.
If found, skip generation and meter as `news_cache_hit` at $0.00. This requires:
- Adding a `content_hash` column to `article_requests` (indexed)
- Adding `news_cache_hit` to `VALID_OPERATION_TYPES`
- Cross-user sharing semantics (Michael's rule: sharing is free)

**Not built in this task** per the explicit instruction:
> "do not build a cache in this task"

## Live Evidence

### Ledger row — Article 2 (short title, no LLM)

```
operation_type | our_cost_usd | cache_hit | job_id                               | breakdown                   | description
news_generate  |     0.006300 | f         | bff4714c-08de-4e74-93b8-b7a18b910515 | {"llm": 0.0, "tts": 0.0063} | Article: Apple Unveils iPhone 17
```

**Arithmetic cross-check:**
- Input: 375 chars, 0 major points
- TTS chars: min(375, 5000) + 1200 + 0×400 = 1575
- TTS cost: 1575 × $0.000004 = **$0.006300** ✓
- LLM cost: title "Apple Unveils iPhone 17" = 4 words ≤ 12 → **$0.00** ✓
- Total: **$0.006300** ✓ matches ledger

### Ledger row — Article 1 (long title, LLM triggered)

```
operation_type | our_cost_usd | cache_hit | job_id                               | breakdown                         | description
news_generate  |     0.011352 | f         | c0b92359-173d-4dad-8077-0f061f4253ce | {"llm": 0.00032, "tts": 0.011032} | Article: The Supreme Court ruled ...
```

**Arithmetic cross-check:**
- Input: 758 chars, 2 major points
- TTS chars: min(758, 5000) + 1200 + 2×400 = 2758
- TTS cost: 2758 × $0.000004 = **$0.011032** ✓
- LLM cost: title > 12 words → 160 tokens × $0.002/1000 = **$0.000320** ✓
- Total: $0.011032 + $0.000320 = **$0.011352** ✓ matches ledger
- Breakdown sum: 0.011032 + 0.00032 = 0.011352 = total ✓

### Cache hit test

**No cache path exists.** A second request with the same text generates a new article
with a new `article_id` and a fresh ledger row at full cost. There is no mechanism to
detect or deduplicate. This is the gap proposed as a follow-up above.

### Regression suite

```
28 passed, 1 warning in 0.20s
```
- `test_local60_cost_metering.py`: 8/8 PASS (backward compat verified)
- `test_local64_cost_ceiling.py`: 9/9 PASS
- `test_local69_news_metering.py`: 11/11 PASS

Baseline comparison: 41 collection errors exist identically at
`~/audioura-worktrees/prepush-baseline` (missing dependencies, pre-existing).

## Files Changed

| File | Change |
|---|---|
| `cost_meter.py` | +`description` parameter to `record_operation`; `_ensure_table` adds column |
| `news_orchestrator_service.py` | Wire `record_operation` after successful news generation |
| `migration/sql/007_cost_ledger_description.sql` | New — adds `description VARCHAR(256)` to `cost_ledger` |
| `tests/test_local69_news_metering.py` | New — 11 tests covering cost model, description, migration |
