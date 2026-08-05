##### READY FOR REVIEW

## LOCAL-224: R1 fires on cycling directions — nav exemption fix

**Commit:** `808ba32` on branch `kiro/local224-nav-exemption-cycling`
**Cost:** $0.00 (deterministic code change, no LLM calls)

---

## Files changed

| File | Summary |
|---|---|
| `style_validator_detector.py` | +104 −17: Replace hardcoded `_STYLE_NAV_ROUTE_VERBS` with transport-mode-derived set; add composite verb handling for "Start cycling south…"; derive `_NAV_VERBS_R1` from same canonical list; add compound compass directions; reconcile sentence/paragraph heuristics |

---

## Acceptance criteria — evidence

### 1. Both cycling sentences classify as navigation

```
>>> _is_style_navigation_sentence("Start biking southeast on the main road, continue straight until you reach the roundabout near the coast.")
True

>>> _is_style_navigation_sentence("Start cycling south on the main road with the sea on your right until you reach the peninsula's tip.")
True
```

### 2. All four attention-directing sentences still fire R1

```
>>> "Look for the Rue Obscure along the waterfront."                          → R1=True
>>> "Pause to take in the breathtaking view of the bay."                      → R1=True
>>> "Turn your attention to the smaller canvas on the left wall."              → R1=True
>>> "Take a moment to absorb the ancient aura emanating from the cobblestone…" → R1=True
```

### 3. Verb coverage derived from transport modes

`_TRANSPORT_MODE_ROUTE_VERBS` dict keyed by the same modes as `generate_tour_text.py:_TRANSPORT_MODE_KEYWORDS` — on_foot, bike, animal, vehicle, country_scale. Adding a new transport mode there requires adding its verbs in one place here.

### 4. Two heuristics reconciled

**Sentence-level is authoritative.** It checks: verb + directional word (or verb + transport gerund + directional). Precise, binary, per-sentence.

**Paragraph-level is a density fallback.** It exempts the entire paragraph when >50% of sentences match route patterns, OR the paragraph is short + has patterns. It now uses the same dynamically-built verb alternation (`_NAV_VERB_ALT`) so both agree on what constitutes a route verb.

When they disagree: sentence-level decides per-sentence within `validate_paragraph()` (line 1309). Paragraph-level only provides a bulk exemption for the whole paragraph (line 1288).

### 5. Corpus-wide R1 before/after by tour type

```
Type        Tours   Paras  R1 before  R1 after     Δ
-------------------------------------------------------
cycling        16     250  148 (59.2%)  141 (56.4%)   -7
walking        23     311  116 (37.3%)  113 (36.3%)   -3
museum         23     607  221 (36.4%)  221 (36.4%)   +0
other          20     404  231 (57.2%)  228 (56.4%)   -3
ALL            82    1572  716 (45.5%)  703 (44.7%)  -13
```

13 false-positive paragraphs eliminated. Cycling tours see the largest improvement (-7 paragraphs, −4.7%). Museum tours unchanged (no transport verbs in their content).

### 6. Corrected RIVIERA_2STOP_ROUND2 rate

```
ROUND2 REPORTED:  R1 = 50% (3/6 paragraphs)
ROUND2 CORRECTED: R1 = 40% (2/5 paragraphs, excluding R9-deleted para 6)

  Paragraph 1: [clean]          ← was R1_IMPERATIVE; now nav-exempt ✓
  Paragraph 2: [clean]
  Paragraph 3: [R1_IMPERATIVE]  ← pre-existing "Cap" proper-noun false positive
  Paragraph 4: [R1_IMPERATIVE]  ← genuine: "Position yourself", "Take a moment"
  Paragraph 5: [clean]
```

### 7. Regression sets pass

```
R9 generic deletion test:  39/39 pass  ✓ ALL PASS
R8 prompt leakage test:    31/31 pass  ✓ ALL PASS
```

Includes: R1 regression (3/3), R8 fires (2/2), R8 silent (2/2), R9 fires (2/2), R9 silent (23/23), Navigation exempt (3/3 + 3/3).

### 8. audio_tours and Nice list

```
audio_tours: 133
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] — UNCHANGED ✓
```

### 9. git status clean, no container rebuild

```
$ git status --short
(empty — clean)

$ git rev-list --count storied..HEAD
1
```

No Docker operations performed. No `docker-compose build` or `docker-compose up`.

---

## Why this does not reintroduce D69's problem

D69 identified that a closed **detection** verb list will always miss the next verb. R1's inverted design detects ANY sentence-initial base-form verb (open-class detection), then subtracts exemptions.

The transport verbs are **exemption** entries, not detection entries. The exemption has two structural bounds:

1. **Finite source:** transport modes are enumerated in `generate_tour_text.py`; each mode has a small set of movement verbs.
2. **Directional gate:** every verb in the exemption still requires a directional word (or transport gerund + directional) to fire. "Cycle" alone is detected as R1. "Cycle south" is exempt.

A new transport mode added to `_TRANSPORT_MODE_KEYWORDS` without corresponding verbs here would fail open (fire R1 on its navigation text) rather than fail closed (let bad content through). The error is visible and fixable.

---

## Limitations

1. **Paragraph 3 false positive persists:** "Cap d'Antibes, situated on the French Riviera, holds a special place…" fires R1 because "Cap" is parsed as a base-form verb. This is a pre-existing proper-noun heuristic gap (the word after "Cap" is `d'Antibes` which starts with lowercase, defeating the capitalized-second-word gate). Not in scope — unrelated to transport verbs.

2. **The 'start' verb is general-purpose.** Guarded by requiring strong directionals (not 'the', 'on', 'to') for the direct match path. "Start the tour by considering…" correctly fires R1. But edge cases like "Start toward the exit" would be exempt — this is defensible (it IS a route-movement instruction) but worth monitoring.

3. **Corpus "before" is simulated, not measured on old code.** The old `_STYLE_NAV_ROUTE_VERBS` was reconstructed from its known contents. The simulation correctly identifies 13 paragraphs where new verbs make the difference, but the old paragraph-level density heuristic's exact behavior on all 1572 paragraphs was not re-run from the actual old code commit.

4. **No new tours generated.** The corrected R1 rate reflects scoring only — it does not demonstrate that the style retry would now leave cycling navigation alone in a live generation run. Verified at the rule level; end-to-end pipeline verification would require a generation run.
