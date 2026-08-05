##### READY FOR REVIEW

## LOCAL-229: Wire CONTRADICTED block into generation pipeline

**Commit:** `22e7dde`  
**Branch:** `kiro/local229-enforce-contradicted-block`  
**Base:** `storied`

---

### Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | +113 lines: Phase 5.16 CONTRADICTED claim block, between R9 deletion (5.15) and Phase 5.5 validation |
| `tests/test_local229_contradicted_block.py` | +320 lines: 5-test suite proving end-to-end behaviour |

---

### Design choice: DROP the group (not re-request)

When a sentence group contains a CONTRADICTED claim, the group is **dropped** (omitted from output). Not re-requested.

**Why:**
1. Re-requesting costs money and may regenerate the same false claim (LLM draws from training data, not corpus).
2. The block fires rarely/never on today's corpus (0/188, D99) — the extra LLM call would almost never help.
3. Dropping is deterministic, $0.00, and aligns with how R9_GENERIC already works (groups are deleted, not repaired).
4. The rest of the stop's narration remains intact — only the group containing the false claim disappears.

---

### Evidence

#### 1. Constructed contradiction demonstrably blocked end-to-end

```
--- Synthetic contradiction is blocked ---
  ✓ Synthetic contradiction detected: 1 CONTRADICTED claim(s)
    claim: 1842 (in context: "The museum was founded in 1842 by local merchants who sought to preser")
    evidence: The museum was founded in 1963 by the city council as a cultural centre for contemporary art. It ope
```

Corpus says 1963. Generated text says 1842. Detector fires CONTRADICTED. Group is dropped.

#### 2. Block at group level, not paragraph (D102)

```
--- Block at group level, not paragraph ---
  ✓ Group-level block: 1 group(s) blocked, 1 group(s) survived
    blocked: The museum opened in 1842 as one of the earliest public galleries in the south o...
    survived: André Svetchine designed the modernist facade with its distinctive curved concre...
```

A paragraph with two groups: the contradicted group is dropped, the clean group survives.

#### 3. UNSUPPORTED does NOT block (D100)

```
--- UNSUPPORTED does NOT block (D100) ---
  ✓ UNSUPPORTED does not block: 2 UNSUPPORTED claim(s), 0 CONTRADICTED — group would NOT be dropped
```

#### 4. No contradictions → byte-identical pass-through

```
--- No contradiction = byte-identical ---
  ✓ No contradictions → no groups dropped (byte-identical pass-through)
```

When no groups are blocked, no groups are dropped, no reassembly occurs → output identical to input.

#### 5. Import path container-safe

```
--- Import path is container-safe ---
  ✓ Both modules at repo root — container-safe import
```

`claim_check.py` and `sentence_group_scorer.py` are both at repo root. No `sys.path` manipulation in the production import (`from claim_check import ...` / `from sentence_group_scorer import ...`).

#### 6. Feature flag

Behind `DISABLE_CONTRADICTED_BLOCK=1`. When set, the phase prints a skip message and does nothing — output is byte-identical to baseline.

#### 7. Cost per tour

```
Time for 1 stop: 5.0 ms
Groups checked: 4
Claims extracted: 5
Projected for 10-stop tour: 50.0 ms (0.050 s)
LLM cost: $0.00 (deterministic, no API calls)
```

$0.00 LLM cost. ~50ms wall-clock for a 10-stop tour. Well under the $0.35 ceiling.

#### 8. Database unchanged

```
audio_tours: 137
nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
```

#### 9. Working tree clean

```
$ git status --short
(empty)
```

---

### Logging

Every block is logged with:
- The claim text
- The corpus sentence that contradicts it
- The action taken (DROPPED)
- The stop name and index

Example output format:
```
[LOCAL-229] BLOCKED Stop 3 'The City Museum': claim='1842 (in context...' contradicted_by='The museum was founded in 1963...' → DROPPED
[LOCAL-229] CONTRADICTED block summary: 1 group(s) blocked, 1 stop(s) affected
```

---

### Limitations

1. **The block cannot fire without corpus passages.** Stops with no `stop_corpus` data are skipped entirely (no passages = no contradiction possible). This is correct — you cannot contradict what you cannot check against.

2. **Predicate-proximity requirement may miss some contradictions.** The detector requires the conflicting number to appear near predicate-context tokens from the claim (same verb or action word). This is by design (LOCAL-219: prevents false alarms from unrelated numbers in the same passage) but means a paraphrased contradiction with completely different verbs will be UNSUPPORTED, not CONTRADICTED.

3. **Expected fire rate is zero on today's corpus.** D99 established 0/188 CONTRADICTED claims corpus-wide. This block is a safety net for corpus growth and LLM drift, not a current-state correction.

4. **Reassembly joins sentence groups with single spaces.** If the original text had specific inter-group formatting, that formatting is lost for the affected paragraph. Given the block fires rarely/never, this is acceptable.

5. **No container rebuilt.** Verified by `docker ps` — no container touched.
