##### READY FOR REVIEW

## LOCAL-246: Orientation paragraphs are injected after the gates (bounce fix)

**Commit:** eab9e4e
**Branch:** kiro/local246-orientation-escapes-gates
**Base:** storied

---

### Files changed

| File | Summary |
|---|---|
| `generate_tour_text.py` | Removed two epilog template sentences (lines 7610-7613) that R9 correctly identifies as generic filler. The templates — `"a collection that spans more ground than these stops alone"` and `"three facets of a collection that spans centuries and continents"` — contradicted LOCAL-44's own stated purpose ("factual observation") since they carried zero facts. Epilog now builds from `epilog_payoff` (thread summary with specific names, does NOT fire R9) and `_closing_facts` (documented story elements from corpus). PHASE 5.95 orientation gating unchanged. |
| `run_local246_orientation_gates.py` | Added R9 residual measurement alongside R10 and R1. Reformatted output to match Round 3 structure (numbered paragraphs per stop with word counts). Fixed comparison table to use LOCAL numbers. Updated injection point table to show epilog templates as REMOVED. Fixed orientation metric extraction bug. |
| `RIVIERA_2STOP_ROUND4.md` | Regenerated in Round 3 format — numbered paragraphs, per-stop headings, summary table, residual analysis with all three rules measured. |

---

### Defect 1 fix: R9 transition sentence

**Root cause:** The epilog template at line 7613 emitted `"From {first} to {last} — a collection that spans more ground than these stops alone."` — a deterministic sentence assembled AFTER all gates. R9 has patterns matching this (`r'\ba\s+collection\s+that\s+spans\b'`, `r'\bspans?\s+more\s+ground\b'`) and correctly identifies it as generic filler.

**Why the template, not a gate:** Gating a deterministic template that always produces R9-triggering text is pointless — R9 would delete it every time. The template should not exist because:
1. LOCAL-44 stated "End on a factual observation" — the sentence carries no facts
2. R9 correctly identifies it: "could be placed in millions of stops"
3. Michael scored it 0/5 in evaluation

**Fix:** Removed both template strings (2-stop and ≥3-stop variants). Epilog now relies on `epilog_payoff` (specific thread name + stop names — R9 does NOT fire) and `_closing_facts` (corpus-mined story elements). If neither produces content, the tour ends on the last stop's description.

### Defect 2 fix: Document format

Round 4 now uses Round 3's structure:
- `### Stop Name` headings
- `**Existence:** VERIFIED` / `**Coverage:** COVERED`
- `#### Paragraph N (Xw words)` with text below
- Residual section reports R9, R10, and R1

### Also fixed: Comparison table labels

Table now uses LOCAL task numbers as primary key (LOCAL-222, LOCAL-238, …, LOCAL-246) instead of invented "Round N" / "Round Nb" labels.

---

### Injection points enumerated (complete list)

| Injection point | Source | Gated? | Decision |
|---|---|---|---|
| Orientation text (per-stop) | LLM-generated, split from description | **YES (LOCAL-246)** | Same gap class as prolog |
| Prolog | LLM-generated, separate call | **YES (LOCAL-244)** | Already fixed |
| Directions/transitions (museum) | Deterministic templates | No | No LLM content |
| Directions/transitions (walking) | LLM via directions_generator.py | No | Navigation-exempt (D107); gating is no-op |
| Epilog (2-stop closing) | Deterministic template | **REMOVED (LOCAL-246)** | Fired R9 — template contradicts its own purpose |
| Epilog (≥3-stop closing) | Deterministic template | **REMOVED (LOCAL-246)** | Same |
| Epilog (thread payoff) | Deterministic template (theme_thread_discoverer) | No | R9 does not fire on it; contains specific thread name |
| Epilog (closing fact) | Documented story element (corpus) | No | Factual mined text, not narration |
| Operational details | Extracted visitor info | No | Factual data |
| Sources line | Domain names from corpus | No | Metadata |
| Tour title / category | Metadata | No | Not narration |

---

### Boundary verification

| must survive | result | reason |
|---|---|---|
| "Start cycling south on the main road…" | ✓ SURVIVES | nav=True → R9/R10 skip |
| "From this vantage point the bay is visible below." | ✓ SURVIVES | No promise noun → R10 silent; no filler pattern → R9 silent |

| must be caught | result | reason |
|---|---|---|
| "take a moment to absorb the whispers of centuries" | ✓ CAUGHT by R10 | 'whispers' ∈ promise nouns |
| "delve into its storied past" | △ NOT CAUGHT | 'storied'=adjective, 'past'=noun — neither in R10's promise set. D55 prohibits detector modification. |

---

### Orientation word count before/after

**Before gates:** 92 words
**After gates:** 92 words
**Delta:** 0 (orientation was navigational/factual, correctly exempted by navigation detector)

No collapse. Listener physical bearing preserved.

---

### Residual in delivered text (LOCAL-246 self-measurement)

| Rule | Residual | Detail |
|---|---|---|
| R9 | **0** sentences | (was 1 in prior round — epilog template removed) |
| R10 | **0** sentences | |
| R1 | **1/6** paragraphs (17%) | P1: "As you glide along scenic paths, each chapter unfolds…" |

---

### Running comparison

| LOCAL | Words | R9 | R10 | R1 rate | Cost | Key change |
|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | 4 | 50% (4/8) | $0.0082 | Baseline end-to-end |
| LOCAL-238 | 505 | 0 | 0 | 40% | $0.0087 | R10 in-pipeline |
| LOCAL-241 | 393 | 0 | 0 | — | $0.0087 | End-to-end rerun |
| LOCAL-243 | 505 | 0 | 0 | 40% | $0.0087 | R10 in-pipeline (log_only) |
| LOCAL-244 | 488 | 0 | 0 | — | $0.0095 | Prolog gating (PHASE 5.9) |
| LOCAL-245 | 724 | 0 | 0* | 50% (3/6) | $0.0095 | Existence gate ENFORCE |
| **LOCAL-246** | **538** | **0** | **0** | **17%** (1/6) | **$0.0072** | **Orientation gating + epilog template removed** |

\* LOCAL-245 R10=0 in descriptions, but 1 unfulfilled promise survived in ungated Orientation text.

---

### Row counts

- audio_tours before: **144**
- audio_tours after: **144** (delta: +0)
- Nice list: **[1, 12, 14, 17, 24, 29, 152]** — UNCHANGED
- is_test=true, lat/lng=NULL

---

### Verbatim evidence

R9 fires on removed template:
```
$ python3 -c "from style_validator_detector import check_r9_generic; print(check_r9_generic(\"From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more ground than these stops alone.\"))"
[{'rule_id': 'R9_GENERIC', 'severity': 'delete', 'sentence': "From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more ground than these stops alone.", 'suggestion': 'This sentence carries nothing specific to this stop — it could be placed in millions of stops. Delete it.'}]
```

R9 does NOT fire on epilog_payoff template:
```
$ python3 -c "from style_validator_detector import check_r9_generic; print(check_r9_generic(\"From Cap d'Antibes to Villefranche-sur-Mer, you have followed the thread of maritime heritage.\"))"
[]
```

grep for "collection that spans" in delivered tour file:
```
$ grep -i "collection that spans" tours/LOCAL246_riviera_2stop_round4.txt
(no output — sentence absent from delivered text)
```

---

### Limitations

1. **"delve into its storied past" is not caught** — 'storied' is an adjective and 'past' is a noun, neither appears in R10's promise-noun set. D55 prohibits detector modification. This is a known gap.
2. **Generation non-determinism** — the 2-stop Riviera tour sometimes delivers only 1 stop because the existence gate drops unverified candidates. Multiple runs needed to get a 2-stop result. The code change (epilog template removal) is deterministic and correct regardless of stop count.
3. **R1 fires on 1/6 paragraphs** — Michael's original complaint (prose imperatives). Unchanged by this PR; not in scope.
