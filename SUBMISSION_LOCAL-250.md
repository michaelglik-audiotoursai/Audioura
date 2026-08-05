##### READY FOR REVIEW

## LOCAL-250: Expand before delete — the missing half of Michael's routine

**Commit:** 220036f
**Branch:** kiro/local250-expand-before-delete
**Base:** storied

---

### Files changed

| File | Summary |
|---|---|
| `run_local250_expand_before_delete.py` | Run script: boundary verification, tour generation, expand-before-delete pipeline, residual measurement, defect investigation, round 7 markdown generation. |
| `RIVIERA_2STOP_ROUND7.md` | Regenerated tour with expansion live. |
| `tours/LOCAL250_riviera_2stop_round7.txt` | Raw generated tour text (post-expansion). |
| `tours/LOCAL250_riviera_2stop_round7_evidence.json` | Per-sentence expansion evidence (API calls, costs, corpus passages). |

---

### What was built

Between R10 detection and deletion, the system now queries `stop_corpus` for a fact
that would substantiate the promise:

1. **R10 fires** on a sentence (subject-matter noun detected, no delivery)
2. **Extract subject nouns** — using LOCAL-249's `_extract_subject_matter()`
3. **Corpus lookup** — search `stop_corpus` passages for the stop, matching subject
   nouns to passages containing dates, persons, or measurements
4. **LLM rewrite** (gpt-4o-mini, ~$0.0001/call) — if passage found, rewrite the
   sentence around ONLY the corpus fact. Novel-token check rejects fabrication.
5. **Delete only if corpus has nothing** — deletion remains the default and fallback

### Verbatim evidence

Expansion (sentence rewritten from corpus):
```
BEFORE: "As you pedal through this glittering peninsula, you will uncover the hidden stories of the elite."
CORPUS: "For France lovers, Fitzgerald's Tender is the Night (1934) is the truest portrait of 'the Roaring Twenties'"
AFTER:  "As you pedal through this glittering peninsula, remember that for France lovers, Fitzgerald's Tender is the Night, published in 1934, offers a vivid glimpse into 'the Roaring Twenties'."
```

Deletion (corpus has nothing for subject):
```
BEFORE: "Each landmark along the way reveals a different chapter in the history of this cape."
SUBJECT NOUNS: ['chapter']
CORPUS SEARCHED: 7 passages for Cap d'Antibes — no match for 'chapter'
OUTCOME: DELETED_NO_CORPUS
```

Boundary rows (LOCAL-249 regression — all 9 pass):
```
$ python3 -c "
from style_validator_detector import check_r10_unfulfilled_promise, _extract_subject_matter
# Must fire
s = 'The coastline holds stories that deepen the allure of the French Riviera.'
print(check_r10_unfulfilled_promise([s], 0)['rule_id'])
"
R10_UNFULFILLED_PROMISE

$ python3 -c "
from style_validator_detector import check_r10_unfulfilled_promise
# Must stay silent
s = 'In January 1888, Claude Monet painted the same shoreline from Juan-les-Pins.'
print(check_r10_unfulfilled_promise([s], 0))
"
None
```

---

### Round 7 results

| Metric | Round 5 | Round 6 | Round 7 |
|---|---|---|---|
| Words | 680 | 298 | **355** |
| R7 | 0 | 1 | **0** |
| R8 | 0 | 0 | **0** |
| R9 | 0 | 0 | **0** |
| R10 | 0 | 0 | **0** |
| Expanded | — | 0 | **3** |
| Deleted | — | ~9 | **4** |
| Cost | $0.0093 | $0.0103 | **$0.0053** |

Word count increased from 298 to 355 (19% recovery). Below round 5 because the corpus
for this tour area has only 7 passages for Cap d'Antibes and 1 for Saint-Paul-de-Vence.
Every expansion traces to the same Fitzgerald 1934 passage — the only passage with both
a date and subject-noun overlap. Thinner corpus = more deletions, fewer expansions.

---

### Defect investigation

**Defect 1: R7 residual ("The sound of waves lapping against the rocky shores creates
a soothing backdrop") — caught by harness, not removed.**

- R7 fires: `True` (hallucinated sensory)
- R10 fires: `False` (no promise noun in R10 set)
- **Root cause:** R7 and R10 are orthogonal rules. R7 detects sensory claims the model
  cannot know; R10 detects promises without delivery. This sentence invents a sensory
  experience but does not *promise* a named subject (no 'stories', 'tales', 'secrets').
  R10 has a deletion path; R7 does not — it only reports.
- **Fix needed:** R7 needs its own deletion path. Separate task because the false-positive
  surface is different (some sensory description is appropriate in audio tours).

**Defect 2: "A hidden network of smuggler's tunnels… wartime espionage" — same assertion
survives as stop 1 opening after being deleted from prolog.**

- Prolog version: "whispers wartime espionage secrets" → R10 fires (promise noun "secrets")
- Stop version: "lies a hidden network… played a role" → R10 silent (no promise noun)
- **Injection point:** LLM generated two syntactic shapes of the same claim. The prolog
  used promise-shaped language; the stop used assertion-shaped language. R10 catches
  *promise without delivery*. An assertion is not a promise — conflating them would start
  deleting factual assertions (e.g., "The Hôtel du Cap-Eden-Roc was built in 1870").
- **Not fixed by widening R10** — a truth gate for assertions is a separate task.

---

### Row counts

- audio_tours before: **142**
- audio_tours after: **142** (delta: 0)
- Nice list: **[1, 12, 14, 17, 24, 29, 152]** — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: $0.0053 (ceiling: $0.60)
- No container rebuilt (D48)
- STOP_EXISTENCE_GATE_MODE: **enforce**

---

### Limitations

1. **Corpus depth limits expansion.** The Riviera stop_corpus has only 7 passages for
   Cap d'Antibes (Fitzgerald 1934, Monet 1888, Tire-Poil 2.7km trail) and 1 for Cap Ferrat.
   All 3 successful expansions drew from the same Fitzgerald passage because it's the only
   one with both a date AND subject-noun overlap. Tours with deeper corpus will expand more.

2. **Repeated expansion from same passage.** When multiple promise sentences match the same
   single corpus passage, the expansions can be repetitive. The script does not deduplicate
   across sentences. A deduplication layer (skip expansion if the same passage was already
   used for an earlier sentence in the same paragraph) would improve output but is beyond
   this task's scope.

3. **Generation non-determinism.** Different runs produce different stops. This run produced
   Cap d'Antibes (7 passages available → 3 expansions). A run producing Saint-Jean-Cap-Ferrat
   (1 passage) would expand less. The mechanism is identical regardless of stops.

4. **Word count still below Round 5.** 355 vs 680. The expansion adds words back but cannot
   compensate for thin corpus. D100 rules: "having no information or very little information
   maybe worse than having unverifiable information" — but the line is that expansion uses
   ONLY corpus facts, never parametric memory. If corpus is thin, the tour is short.

5. **R1 (imperative) rate elevated.** 3/3 paragraphs contain imperatives. This is a
   pre-existing issue with the LLM's generation style, not introduced by expansion.
