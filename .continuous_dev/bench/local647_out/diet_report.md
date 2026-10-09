### Prompt-diet experiment (arm A gpt-4.1, arm B gpt-4.1-mini)

| Arm | Variant | Mean prompt tok | Mean cached tok | Mean out tok | Mean score | $/stop |
|-----|---------|-----------------|-----------------|--------------|-----------|--------|
| A | full | 2304 | 0 | 712 | 7.583 | $0.010301 |
| A | diet | 1830 | 1355 | 668 | 7.333 | $0.006972 |
| A | fixedfirst | 2304 | 1941 | 695 | None | $0.007257 |
| B | full | 2304 | 0 | 574 | 7.833 | $0.001840 |
| B | diet | 1830 | 1504 | 539 | 7.375 | $0.001144 |
| B | fixedfirst | 2304 | 1536 | 591 | None | $0.001407 |

**Deltas (diet vs full):**
- Arm A: prompt tokens 2304→1830 (−474, −20.6%); score 7.583→7.333 (Δ-0.250); $/stop $0.010301→$0.006972 (Δ$-0.003329)
- Arm B: prompt tokens 2304→1830 (−474, −20.6%); score 7.833→7.375 (Δ-0.458); $/stop $0.001840→$0.001144 (Δ$-0.000696)

**OpenAI automatic prompt caching (fixed-instructions-first):**
- Arm A: mean cached_tokens=1941 of 2304 prompt tok (84% cached); caching saves ≈$0.002912/stop on input (cached billed at $0.5/1M vs $2.0/1M).
- Arm B: mean cached_tokens=1536 of 2304 prompt tok (67% cached); caching saves ≈$0.000461/stop on input (cached billed at $0.1/1M vs $0.4/1M).
