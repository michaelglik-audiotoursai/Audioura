# SUBMISSION_LOCAL-438.md

## Task: Story selection is a packing problem

**Branch:** `LOCAL-438-story-packing`
**Base:** `c18224d` (verified: `git merge-base --is-ancestor c18224d HEAD` exits 0)

---

## Part 1 — `score_story_quality(story) -> float`

**Module:** `story_selection.py`, module scope.

### Composition

```
quality = provenance_weight + verification_weight + specificity_score
```

| Component | Range | Source |
|-----------|-------|--------|
| Source provenance | 0.5–3.0 | Reuses `corpus_source_quality`'s SOURCE_WEIGHTS table (D392 requirement) |
| Verification outcome | 0.5–2.0 | `corroboration_status` from story_element_extractor: documented(2.0) > disputed(1.5) > reported(1.0) > legend(0.5) |
| Specificity | 0.0–3.0 | +1 per signal: named person, date, consequence verb. Same signals the story classifier detects. |

**Total range:** 1.0–8.0

**Tie-breaking:** when two stories score identically, `select_stories_for_stop`
breaks ties by word count (LONGER first — maximises budget fill with greedy
packing, per Michael's worked example), then by text content (deterministic).

### Weights — not calibrated to current output (D386's lesson)

The weights come from:
- Provenance: the existing `corpus_source_quality` table (museum_official 3.0, wikipedia 2.5, etc.) — already in production.
- Verification: a natural ordinal (multi-source > single-source > unverified).
- Specificity: binary presence signals (named person, year, consequence verb).

No fitting to output was performed. The weights are justified by what each signal means, not by what they produce on the current corpus.

### Hand-checked scores

**Score 1:** Museum-official, documented, fully specific
```
Text: "Louis Broder published Le Lézard aux plumes d'or in 1971, enabling Miró to create his most ambitious livre d'artiste."
  Provenance: 3.0 (museum_official)
  Verification: 2.0 (documented)
  Specificity: 3.0 (person:Broder ✓, date:1971 ✓, consequence:"enabling" ✓)
  TOTAL: 8.0
```

**Score 2:** Wikipedia, reported, person+date but no consequence verb
```
Text: "Mourlot Frères operated a lithography workshop in Paris from 1852 to 1997."
  Provenance: 2.5 (wikipedia)
  Verification: 1.0 (reported)
  Specificity: 2.0 (person:Mourlot ✓, date:1852 ✓, consequence: ✗)
  TOTAL: 5.5
```

**Score 3:** Web search, legend, no specificity
```
Text: "The technique was supposedly unique in the history of printmaking."
  Provenance: 0.5 (web_search)
  Verification: 0.5 (legend)
  Specificity: 0.0 (person: ✗, date: ✗, consequence: ✗)
  TOTAL: 1.0
```

---

## Part 2 — Budget constant and packing selector

### `STOP_WORD_BUDGET`

**Module:** `story_selection.py`, line 30.
**Value:** 450 (D392: measured delivery is 169–459 words/stop; initialised at high end so day-one behaviour does not shrink).
**To change:** edit `STOP_WORD_BUDGET` in `story_selection.py`.

### `select_stories_for_stop(stories, budget=None) -> list`

**Module:** `story_selection.py`, module scope.

Algorithm (Michael's, verbatim from D392):
1. Score each story's quality via `score_story_quality`.
2. Sort by quality descending (ties: longer first, then text for determinism).
3. Greedy pack: take best that fits, then best remaining that fits, etc.
4. Number of stories used is whatever fits — one, two, or three.
5. **50% exception:** best story exceeds budget but by <50%, AND clearly best (score ≥1.0 above second), use alone.
6. No story dropped for any reason except it doesn't fit.

The 120-word floor (LOCAL-393) applies to the delivered stop narration, not to the packing selection. The narration prompt enforces minimum output length from whatever stories are selected.

### Michael's worked example — all three cases passing

```
Budget 100 words. Stories: A good/30w, B excellent/80w, C bad-but-legitimate/20w,
D good/25w, E good/70w.

Case 1 (with B): B(80) wins, 20 left, only C(20) fits → [B, C] ✓
Case 2 (without B): sort A,D,E by quality (equal), longest-first: E(70)+A(30)=100 → [E, A] ✓
Case 3 (F excellent/125w): 125 < 150 (100+50%), far the best → [F] alone ✓
```

All three cases pass in `tests/test_local438_story_selection.py::TestMichaelsWorkedExample`.

---

## Part 3 — Wiring

**Where stories are chosen:** `generate_tour_text.py` at two points:
1. **Pre-computation (line ~8640):** where elements from `work_stories` cache are selected per stop before generation. Previously called `select_stop_elements(elements, max_selected=3)`. Now routes through `select_stories_for_stop(elements, budget=STOP_WORD_BUDGET)`.
2. **Per-stop B6 fallback (line ~9810):** the direct cache read when diversity-adjusted selections are unavailable. Same change.

**Story pool source:** The pool comes from what `story_element_extractor` already produces per stop via the `work_stories` cache (keyed by work+artist). These are LLM-extracted story elements with `text`, `type`, `corroboration_status`, `source_domain`, `people`, `dates` fields — exactly what `score_story_quality` reads.

**No silent restructuring:** the selection step was replaced in-place. The story pool construction (extraction, corroboration scoring, caching) is unchanged. Only the selection mechanism changed from "rank and take top 3" to "score, sort, greedy-pack into budget".

---

## Neutralisation evidence (D242 #1)

### Neutralising `select_stories_for_stop` → return all input unchanged
```
9 failed, 10 passed
  FAILED TestMichaelsWorkedExample::test_case1_with_B_present
  FAILED TestMichaelsWorkedExample::test_case2_without_B
  FAILED TestMichaelsWorkedExample::test_case3_single_story_exception
  FAILED TestSelectStoriesForStop::test_respects_budget
  FAILED TestSelectStoriesForStop::test_exception_does_not_fire_above_150_percent
  FAILED TestSelectStoriesForStop::test_exception_requires_clear_best
  FAILED TestSelectStoriesForStop::test_packing_stops_at_budget
  FAILED TestSelectStoriesForStop::test_annotates_quality_score
  FAILED TestNeutralisation::test_selection_is_not_passthrough
```

### Neutralising `score_story_quality` → return constant 5.0
```
5 failed, 14 passed
  FAILED TestMichaelsWorkedExample::test_case3_single_story_exception
  FAILED TestScoreStoryQuality::test_excellent_story_scores_high
  FAILED TestScoreStoryQuality::test_good_story_scores_medium
  FAILED TestScoreStoryQuality::test_bad_but_legitimate_scores_low
  FAILED TestNeutralisation::test_score_is_not_constant
```

---

## Live runs

**Gate mode:** `STORIED_MODE=true`, `STOP_EXISTENCE_GATE_MODE=log_only` (default), `DISABLE_TOUR_CACHE=1`
**Model:** `TOUR_LLM_MODEL=(default gpt-3.5-turbo)`, `TOUR_STORY_MODEL=(default gpt-4o)`

### MFA Unbound (3 stops)

| Stop | Word count | story_count | Within budget (450)? |
|------|-----------|-------------|---------------------|
| Le Lézard aux plumes d'or | 347 | 3 | ✓ |
| Moses and Monotheism | 219 | 0 | ✓ |
| Au Soleil du Plafond | 196 | 2 | ✓ |

3/3 stops delivered. All word counts within STOP_WORD_BUDGET=450. Story gate: informational, does not block delivery.

### Palais Lascaris (4 stops)

| Stop | Word count | story_count | Within budget (450)? |
|------|-----------|-------------|---------------------|
| Raquel (panneau, fin du XVIe siècle) | 306 | 1 | ✓ |
| Basse de violon by Testore (Milan, 1696) | 175 | 1 | ✓ |
| Guitar by Antonio de Torres (1884) | 238 | 1 | ✓ |
| Guitare baroque by Giovanni Tesler (1618) | 363 | 0 | ✓ |

4/4 stops delivered. All word counts within STOP_WORD_BUDGET=450. Date 1696 intact.

**Control note:** The expected Palais stops (Harpe 1780, Violes gambe 1652, Sacqueboute 1581, Basse de violon 1696) were not all generated because stop selection (Phase 3) is non-deterministic (D385's finding: the same venue produces different stops between runs). The packing change does not affect WHICH stops get picked — only which stories fill each stop. Date 1696 (Testore) is present. The other dates are absent because the corresponding stops were not selected in this run, not because of a packing regression.

**Work_stories cache unavailable:** PostgreSQL (postgres-2) is not running locally, so `work_stories_get()` returned empty for all stops. The `[LOCAL-438] packed` log line did not fire. The packing logic is exercised through the unit tests (19/19 passing). In production (with Docker services), elements from the cache would route through `select_stories_for_stop`.

---

## Targeted suite

```
19 passed in 0.09s — tests/test_local438_story_selection.py
```

Full suite baseline 211/247 (D383) is not re-run per task instruction.

---

## Summary of changes

| File | Change |
|------|--------|
| `story_selection.py` (NEW) | `score_story_quality`, `select_stories_for_stop`, `STOP_WORD_BUDGET`, `SOURCE_PROVENANCE_WEIGHTS` |
| `generate_tour_text.py` | Two call sites: replaced `select_stop_elements(elements, max_selected=3)` with `select_stories_for_stop(elements, budget=STOP_WORD_BUDGET)` |
| `tests/test_local438_story_selection.py` (NEW) | 19 tests including Michael's three worked-example cases |
