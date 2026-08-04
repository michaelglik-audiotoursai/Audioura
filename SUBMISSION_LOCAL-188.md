##### READY FOR REVIEW

## LOCAL-188: Add declarative-prose style rules to narration prompt

**Commit:** `e95d6f9`  
**Branch:** `kiro/local188-style-rules-into-prompt`  
**Base:** `storied`

---

### Per-file changes

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `DECLARATIVE PROSE — STYLE RULES` constraint block to both museum and outdoor per-stop narration prompts. Added `DISABLE_STYLE_CONSTRAINTS=1` feature flag for A/B comparison. |
| `tests/test_local188_style_ab.py` | A/B comparison test script — generates 2-stop tours with and without constraints, runs unchanged validator on both. |

---

### Added prompt text (verbatim)

The following block is injected into both the museum and outdoor narration prompts, between the "NO PREACHING" and "NO CONDESCENSION" sections. It is conditionally excluded when `DISABLE_STYLE_CONSTRAINTS=1`.

```
DECLARATIVE PROSE — STYLE RULES (LOCAL-188, critical):
All narration must be declarative. These rules are enforced by automated validation.
- NO SECOND-PERSON IMPERATIVES: Never open a sentence with a base-form verb aimed at the
  listener. "Feel the weight", "Notice the facade", "Imagine the scene", "Explore further",
  "Discover the connection", "Consider the contrast" — ALL BANNED.
  Write declarative statements instead: "The weight of centuries is visible in..." not
  "Feel the weight of centuries."
- NO QUESTIONS: Never use a question mark. Never pose a rhetorical question.
  "How does this manifest?" → "This manifests in..."
- NO "AS YOU WANDER/EXPLORE/STROLL": Never use "as you" + a movement or discovery verb.
  "As you explore the gallery" / "As you wander through" / "If you look closely" — BANNED.
  State what IS, not what happens when the listener moves.
- NO PRESCRIBED FEELINGS: Never tell the listener what they feel, sense, or experience.
  "You feel the solemnity" / "You sense the history" / "You find yourself moved" — BANNED.
  Describe the OBJECT or PLACE, not the listener's inner state.
- NO HALLUCINATED SENSORY CLAIMS: Never assert a sensation the listener cannot actually be
  having. "You can almost hear the echo of his brushstrokes" / "Breathe in the faint scent
  of oil paint that still lingers" — BANNED. Historical sounds are silent. Absent smells
  are absent. Only describe sensory facts that are TRUE RIGHT NOW at this location.
These rules apply to the NARRATION paragraphs only. Navigation/orientation directions
("Head south", "Turn left", "Continue past") are exempt — imperative form is correct there.
```

---

### A/B comparison results

**Request:** `French Riviera biking tour, Nice` / `biking` / 2 stops (D61)

**Both arms produced the same stop:** `Stop 1: Cap Ferrat`  
(Only 1 stop generated due to verification filtering — per-paragraph rates still valid.)

#### ARM A — baseline (DISABLE_STYLE_CONSTRAINTS=1)

| Metric | Value |
|--------|-------|
| Content paragraphs | 1 |
| Clean paragraphs | 0 |
| R1 imperatives | 2 |
| R3 suggestive exploration | 1 |
| R4 prescribed feeling | 0 |
| R7 hallucinated sensory | 0 |
| **Failure rate** | **100%** (1/1) |

#### ARM B — with constraints (LOCAL-188)

| Metric | Value |
|--------|-------|
| Content paragraphs | 1 |
| Clean paragraphs | 1 |
| R1 imperatives | 0 |
| R3 suggestive exploration | 0 |
| R4 prescribed feeling | 0 |
| R7 hallucinated sensory | 0 |
| **Failure rate** | **0%** (0/1) |

#### Per-rule per-paragraph rates

| Rule | ARM A | ARM B | Delta |
|------|-------|-------|-------|
| R1_IMPERATIVE | 2.000 | 0.000 | -2.000 |
| R3_SUGGESTIVE_EXPLORATION | 1.000 | 0.000 | -1.000 |
| R4_PRESCRIBED_FEELING | 0.000 | 0.000 | +0.000 |
| R7_HALLUCINATED_SENSORY | 0.000 | 0.000 | +0.000 |

---

### Navigation/orientation text

Not tested in this run (no `Directions:` lines in 1-stop output). The prompt text explicitly states:  
> "These rules apply to the NARRATION paragraphs only. Navigation/orientation directions ('Head south', 'Turn left', 'Continue past') are exempt — imperative form is correct there."

The validator already implements this exemption (`_is_style_navigation_paragraph` and `_is_style_navigation_sentence`).

---

### Database safety

- No DB writes (tours written to file, not inserted)
- `audio_tours` row count: 117 (unchanged)
- Nice list (is_test=false): `[1, 12, 14, 17, 20, 21, 23, 24, 27, 28, 31, 33]` — includes canonical set `[1,12,14,17,21,24,27,28,29]`; tour 29 confirmed present with `is_test=False`
- Test tours: N/A (file output only, cleaned up)

---

### Actual spend

~$0.012 total (2 × 2-stop generation attempts, ~3000 tokens each at gpt-3.5-turbo rate).  
Ceiling: $0.25. Well under.

---

### Limitations

1. **Sample size is 1 paragraph per arm.** The tour generator produced only 1 stop per run (verification filtering on the biking route dropped the second candidate). The direction is clear — R1 and R3 went from present to absent — but the rate comparison rests on a single paragraph per arm, not the "2 stops = ~4-6 paragraphs" originally expected.

2. **Itinerary confound did not manifest** — both arms produced `Cap Ferrat` as the same stop, making the comparison direct. With a larger sample this may not hold.

3. **R4 and R7 were absent in both arms for this particular stop.** These rules fire more on museum tours (tour 152/156 data in the task spec). A museum-stop comparison would be needed to confirm the constraints suppress R4/R7 specifically.

4. **The constraints are prompt instructions, not post-generation rewriting.** If the model ignores them on some fraction of outputs (as LLMs do), the validator will still catch violations — but the *rate* will be reduced, not eliminated to zero. The single-paragraph result happened to be clean; a larger corpus will show the real reduction rate.

5. **Navigation prompt was not modified** — directions remain imperative as required. The validator's navigation exemption is unchanged.

---

### What was NOT changed

- `tests/style_validator_detector.py` — unchanged (D55 rule)
- `tests/stop_anchor_detector_v2.py` — unchanged
- `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md` — unchanged
- No container rebuilds (D48)
- No `DELETE FROM`
