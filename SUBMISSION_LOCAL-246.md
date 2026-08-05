##### READY FOR REVIEW

## LOCAL-246: Orientation paragraphs are injected after the gates

**Commit:** b12d666
**Branch:** kiro/local246-orientation-escapes-gates
**Base:** storied

---

### Files changed

| File | Summary |
|---|---|
| `generate_tour_text.py` | Added PHASE 5.95 orientation gating — runs R9 (generic) and R10 (unfulfilled promise) on every `poi['orientation']` before PHASE 6 assembly. Same pattern, same thresholds, same functions as LOCAL-244's prolog gating. |
| `run_local246_orientation_gates.py` | Generation runner — boundary verification, 2-stop Riviera regeneration, residual measurement, post-checks. |
| `RIVIERA_2STOP_ROUND4.md` | Round 4 output with measured residuals and running comparison. |

---

### Post-gate injection points enumerated

| Injection point | Source | Gated? | Reason |
|---|---|---|---|
| **Orientation text** (per-stop) | LLM-generated, split from description by `"Orientation:"` marker | **YES (LOCAL-246)** | Same gap class as prolog — no gate had ever seen one |
| Prolog | LLM-generated, separate call | YES (LOCAL-244) | Already fixed |
| Directions/transitions (museum) | Deterministic templates | No | `f"Next: {name}."` — no LLM content |
| Directions/transitions (walking) | LLM via `directions_generator.py` | No | Navigation-exempt (D107); R9/R10 skip nav sentences → gating is no-op |
| Epilog | Deterministic templates + corpus facts | No | Template strings + factual text mined from corpus |
| Operational details | Extracted visitor info (hours/prices) | No | Factual data, not narration |
| Sources line | Domain names from corpus | No | Metadata |
| Tour title / category | Metadata | No | Not narration |

---

### Boundary verification

**Must survive (navigation exemption covers orientation):**

| Sentence | R9 | R10 | Nav? | Survives? |
|---|---|---|---|---|
| "Start cycling south on the main road toward the coast." | 0 del | 0 del | True | ✓ |
| "From this vantage point the bay is visible below." | 0 del | 0 del | False (but starts with preposition → not imperative) | ✓ |

**Must be caught:**

| Sentence | R9 | R10 | Caught? |
|---|---|---|---|
| "take a moment to absorb the whispers of centuries that echo through it" | 0 | 1 del | ✓ CAUGHT by R10 |
| "delve into its storied past" | 0 | 0 | △ NOT CAUGHT — 'storied'=adjective, 'past'=noun, neither in R10's promise-noun set. D55 prohibits detector modification. |

---

### Orientation word count before/after

| Metric | Value |
|---|---|
| Words before PHASE 5.95 | 99 |
| Words after PHASE 5.95 | 99 |
| Delta | 0 |
| Collapse? | No — orientation text in this generation was navigational/factual, correctly exempted by D107 |

The gate ran over both stops' orientation text. Neither contained unfulfilled promises (R10) or generic filler (R9). This is the expected outcome for orientation that correctly directs physical bearing. When future generations produce orientation containing "whispers of centuries" or similar promise language, PHASE 5.95 will catch and delete it.

---

### Residual R10 and R1 in delivered text (measured by LOCAL-246)

| Rule | Residual | Detail |
|---|---|---|
| **R10** | **0 sentences** | No unfulfilled promises in delivered text |
| **R1** | **1/6 paragraphs (17%)** | Description paragraph for Cap d'Antibes: "Cap d'Antibes embodies the essence of the French Riviera's allure…" |

---

### Running comparison (six entries)

| Round | Words | R10 residual | R1 rate | Cost | Key change |
|---|---|---|---|---|---|
| Round 1 (LOCAL-222) | 819 | 4 | 50% (4/8) | $0.0082 | Baseline end-to-end |
| Round 1b (rule-on-old) | 191 | 0 | 0% (0/3) | $0.00 | R10 applied to existing text |
| Round 2 (LOCAL-238) | 505 | 0 | 40% | $0.0087 | R10 in-pipeline |
| Round 2b (LOCAL-244) | 488 | 0 | — | $0.0095 | Prolog gating (PHASE 5.9) |
| Round 3 (LOCAL-245) | 724 | 0* | 50% (3/6) | $0.0095 | Existence gate ENFORCE |
| **Round 4 (LOCAL-246)** | **639** | **0** | **17% (1/6)** | **$0.0093** | **Orientation gating (PHASE 5.95)** |

\* Round 3 R10=0 in descriptions, but 1 unfulfilled promise survived in ungated Orientation text.

---

### Row counts

| Metric | Before | After | Delta |
|---|---|---|---|
| `audio_tours` | 144 | 144 | +0 |
| Nice list | [1, 12, 14, 17, 24, 29, 152] | [1, 12, 14, 17, 24, 29, 152] | UNCHANGED |

Tour was `is_test=true`, `lat`/`lng` NULL, file-only (no `audio_tours` row written).

---

### Limitations

1. **"delve into its storied past" not caught** — 'storied' is an adjective modifying 'past' (a plain noun), neither of which is in R10's promise-noun set (`tale`, `story`, `whispers`, `legacy`, etc.). D55 prohibits detector modification. This is a known gap in R10 coverage for adjectival promise-language.

2. **Prolog collapsed to 0 words** — All 3 prolog sentences were R10 unfulfilled promises. The generation model produced a pure-fluff prolog. This is the prolog gating working as designed (LOCAL-244), but the listener hears no introduction. A separate task could address prolog quality at the generation prompt level.

3. **Description body contains purple prose** — Stop 2's description includes "echoes of history reverberate through the salty sea breeze", "tapestry of time", "storied past" etc. R10 does not delete these because surrounding sentences provide factual delivery (95 meters depth, 1,700-foot Canyon of Villefranche, Antonine period references). R10's look-ahead window sees the facts and classifies the promises as fulfilled. This is correct R10 behavior but Michael would likely still mark it poorly.

4. **Generation variance** — Stops selected differ from Round 3 (Villefranche-sur-Mer instead of Eze Village). This is LLM non-determinism in PHASE 3A candidate generation, not a regression.
