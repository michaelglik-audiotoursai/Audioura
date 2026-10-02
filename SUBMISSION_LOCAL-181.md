##### READY FOR REVIEW

## SUBMISSION_LOCAL-181.md

**Task:** Propose truncation limits — document only, no code  
**Branch:** `kiro/local181-truncation-limits-proposal`  
**Base:** `subscribed`

---

### Commit

`7ad958a87958b0246a5a5bd5c95eb51f48d39e13`

---

### Per-File Changes

| File | Action | Purpose |
|------|--------|---------|
| `TRUNCATION_LIMITS.md` | Created | Truncation limits proposal with cost analysis, candidate pairs, draft messages, and pipeline insertion point analysis |

---

### Verbatim Evidence

#### 1. Cost Rates (from `cost_rates.py`)
```
POLLY_COST_PER_1M_CHARS = 4.00
POLLY_COST_PER_CHAR = POLLY_COST_PER_1M_CHARS / 1_000_000  # $0.000004
GPT35_TURBO_COST_PER_1K_TOKENS = 0.002
AWS_TRANSLATE_COST_PER_1M_CHARS = 15.00
```

#### 2. TTS Cap Already Exists (from `news_processor_service.py` line 177–180)
```python
# Limit to 5000 characters per TTS call to control costs
if len(text) > 5000:
    text = text[:5000] + "... Content truncated for cost control."
    logging.warning(f"Text truncated to 5000 characters for Polly cost control")
```

#### 3. Orchestrator TTS Cost Formula (from `news_orchestrator_service.py` line ~315)
```python
_tts_chars = min(len(article_text), 5000) + 1200  # full article cap + overhead
if major_points_count > 0:
    _tts_chars += major_points_count * 400
```

#### 4. LOCAL-165 Measured Cost
```
our_cost=$0.008264 | cache_hit=False | breakdown={'llm': 0.0, 'tts': 0.008264}
```
Article was ~775 chars → user charge $0.04 (×5 multiplier, rounded).

#### 5. Database Article Distribution (queried via `tests/db_connection.py`)
```
Total articles with text: 3
Min: 758 chars | Median: 775 chars | Max: 1,439 chars
Articles > 2,000 chars: 0 (0%)
```
Only 3 test articles exist in local DB — not representative of production.

#### 6. Text Extraction Cap (from `robust_text_extractor.py` line 8)
```python
def extract_clean_text(html_content, max_length=50000):
```

#### 7. Pricing Multiplier (from `pricing.py`)
```
PRICING_MULTIPLIER default: 5.0
```

#### 8. D41 Overdraft Floor (from `projected_costs.py`)
```python
OVERDRAFT_FLOOR_CENTS = -200  # −$2.00
```

---

### Limitations

1. **Sparse article data:** Only 3 test articles exist in the local database (all < 1,500 chars). Real-world distribution is estimated from industry norms and pipeline design (50K extraction cap, quality bonuses for articles > 500 words). A production database query would give definitive percentiles.

2. **No D58 found:** The task references DECISIONS.md D58 but the file only goes up to D31. The directive was provided verbatim in the task description and used as the authoritative source.

3. **Translation cost not fully modeled:** The document notes that translation scales linearly ($0.000015/char) unlike TTS which is capped. For multi-language deployments, truncation saves significant translation cost — this deserves its own analysis if Michael plans translated articles.

4. **No API spend:** All cost figures are derived from rate tables and LOCAL-165 measurements. No live API calls were made.

5. **Audio vs text truncation:** The document identifies that TTS is already capped at 5K chars — truncating displayed text at a different limit than the audio creates a mismatch (user reads 3K but hears up to 5K, or vice versa). This UX consideration is flagged but not resolved — it's Michael's call.
