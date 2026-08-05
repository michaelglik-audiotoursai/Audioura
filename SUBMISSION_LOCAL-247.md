##### READY FOR REVIEW

## LOCAL-247: Payload false positive — `_sentence_has_concrete_payload` misidentifies place names as person names

**Commit:** 276fb6a
**Branch:** kiro/local247-payload-false-positive
**Base:** storied

---

### Files changed

| File | Summary |
|---|---|
| `style_validator_detector.py` | **Primary fix:** Unified `_PLACE_WORDS` vocabulary (one set consulted by both `_is_place_name` and `_sentence_has_concrete_payload`), French/Italian/Spanish lowercase particles (`d'`, `de`, `du`, `van`, `von`, etc.) no longer break capitalized-word runs, adjective→stem resolution (`coastal`→`coast`). **R7:** new patterns for fabricated multi-sensory + abstract emotional result. **R8:** new patterns for "this stop aligns with the tour's theme". **R9:** place-name-only subjects with generic predicates no longer exempt; new filler patterns for "inspired countless X over the years". |
| `run_local247_payload_fix.py` | Run script: boundary verification (6 rows), tour regeneration, residual measurement, post-checks, ROUND5 output. |
| `RIVIERA_2STOP_ROUND5.md` | Regenerated tour with all 4 fixes live. |
| `tours/LOCAL247_riviera_2stop_round5.txt` | Raw generated tour text. |
| `tours/LOCAL247_riviera_2stop_round5_evidence.json` | Generation evidence (API calls, costs). |

---

### Root cause (payload false positive)

Three bugs converging in `_sentence_has_concrete_payload`, branch 4 ("named person" heuristic):

1. **Particle break:** `d'Antibes` starts with lowercase `d`, breaking the capitalized run after `Cap`. "Cap d'Antibes Coastal Path" is never evaluated as one name — it's shredded into fragments.
2. **Vocabulary disagreement:** `_place_suffixes` and `_place_only_words` were separate sets. `path` was in `_place_only_words` but not `_place_suffixes`. The surviving fragment `['Coastal', 'Path']` is checked against `_place_suffixes` only → not a place.
3. **Adjective blindness:** `coastal` is the adjective form of `coast` (which IS in the sets), but no resolution existed.

Result: `['Coastal', 'Path']` → 2 caps, not a known place → "named person" → concrete payload → True → R10's backward-delivery check treats the previous sentence as fulfilling the promise → the promise sentence escapes.

### Fix

| Component | What changed |
|---|---|
| `_PLACE_WORDS` | One unified set (~80 terms) replacing both `_place_suffixes` and `_place_only_words`. Includes `path`, `walk`, `way`, `promenade`, `sentier`, etc. |
| `_NAME_PARTICLES` | Set of French/Italian/Spanish/Dutch/German lowercase particles that are transparent to the capitalized-word scanner. |
| `_ADJECTIVE_TO_PLACE_STEM` | Maps adjective forms to base place words (`coastal`→`coast`, `mountainous`→`mountain`, etc.). |
| `_normalize_for_place_check()` | Resolves adjectives to stems. |
| `_is_place_name()` | Now uses `_PLACE_WORDS` directly, checks all words in the sequence (not just first/last), resolves adjective forms. |
| Cap-word scanner | Handles `d'Antibes`-style tokens by splitting on apostrophe, recognizing the particle prefix, and keeping the capitalized suffix in the run. |

---

### Boundary verification (6 rows, all run and confirmed)

| Sentence | Expected | Actual | Rule |
|---|---|---|---|
| "In January 1888, Claude Monet painted the same shoreline from Juan-les-Pins." | SILENT | ✓ SILENT | — |
| "The Hôtel du Cap-Eden-Roc was built in 1870 at the southern tip." | SILENT | ✓ SILENT | — |
| "Start cycling south on the main road with the sea on your right." | SILENT | ✓ SILENT | — |
| "The salty breeze carries the scent of the sea, and the sound of gentle waves lapping against the rocky shore creates a soothing ambiance." | FIRE | ✓ FIRES | R7 |
| "This stop aligns with the tour's theme of exploring the cultural and natural wonders of the French Riviera." | FIRE | ✓ FIRES | R8 |
| "The Cap d'Antibes, along with Cap Ferrat to the northeast, forms a stunning coastal landscape that has inspired countless creatives over the years." | FIRE | ✓ FIRES | R9 |

---

### ROUND4 re-measurement (false zeros)

| Rule | ROUND4 reported | True residual (with fix) | False zeros |
|---|---|---|---|
| R7 | 0 | 1 | **1** |
| R8 | 0 | 1 | **1** |
| R9 | 0 | 1 | **1** |
| R10 | 0 | 1 | **1** |

All 4 false zeros are in Cap d'Antibes paragraph 2 of ROUND4's delivered text.

---

### R7 analysis

**Why it fires now:** New pattern detects fabricated multi-sensory scenes that attribute an abstract emotional quality via a causation verb. Pattern: `[sensory carrier (breeze/scent/sound)] + [causation verb (creates/produces)] + [abstract quality (ambiance/atmosphere/serenity)]`.

**Why it didn't fire before:** Old R7 patterns only matched absence/impossibility markers (faint, lingering, almost, echoes of history). Present-tense sensory fabrication without those markers was undetected.

**False positive guard:** The pattern requires BOTH a qualified sensory carrier AND an abstract emotional result word. "The market smells of lavender" (factual sensory, no abstract result) → silent. "Waves crash against the rocks" (no abstract emotional attribution) → silent.

---

### Row counts

- audio_tours before: **144**
- audio_tours after: **144** (delta: +0)
- Nice list: **[1, 12, 14, 17, 24, 29, 152]** — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: $0.0093 (ceiling: $0.35)

---

### Verbatim evidence

Payload fix:
```
$ python3 -c "import style_validator_detector as V; print(V._sentence_has_concrete_payload(\"The Cap d'Antibes Coastal Path showcases the region's unspoiled beauty and rich history, making it a must-visit for those seeking tranquility and inspiration.\"))"
False
```

R10 fires on previously-silent promise:
```
$ python3 -c "
import style_validator_detector as V
prev = \"The Cap d'Antibes Coastal Path showcases the region's unspoiled beauty and rich history, making it a must-visit for those seeking tranquility and inspiration.\"
promise = 'The coastline holds stories that deepen the allure of the French Riviera.'
r = V.check_r10_unfulfilled_promise([prev, promise], 1)
print(r['rule_id'] if r else 'SILENT')
"
R10_UNFULFILLED_PROMISE
```

R7 fires:
```
$ python3 -c "import style_validator_detector as V; print(V.check_r7_hallucinated_sensory('The salty breeze carries the scent of the sea, and the sound of gentle waves lapping against the rocky shore creates a soothing ambiance.')[0]['rule_id'])"
R7_HALLUCINATED_SENSORY
```

R8 fires:
```
$ python3 -c "import style_validator_detector as V; print(V.check_r8_prompt_leakage(\"This stop aligns with the tour's theme of exploring the cultural and natural wonders of the French Riviera.\")[0]['rule_id'])"
R8_PROMPT_LEAKAGE
```

R9 fires:
```
$ python3 -c "import style_validator_detector as V; print(V.check_r9_generic(\"The Cap d'Antibes, along with Cap Ferrat to the northeast, forms a stunning coastal landscape that has inspired countless creatives over the years.\")[0]['rule_id'])"
R9_GENERIC
```

---

### Limitations

1. **Single-word person names** (e.g., "Picasso") are not detected by branch 4 of `_sentence_has_concrete_payload` — they require 2+ consecutive caps. This is pre-existing behavior unchanged by this PR. Sentences with single-word person names are typically caught by other branches (date, measurement, or literary-work reference).

2. **R7 pattern scope is narrow by design.** It fires on fabricated sensory + abstract emotional attribution. Present-tense sensory without the "creates a [feeling] ambiance" structure remains undetected — expanding further risks catching legitimate descriptions. Michael's 1/5 complaint was specifically about "guessing what one would feel"; the pattern targets that structure.

3. **R9 generic-predicate check requires a geographic prefix sibling.** If a sentence uses place names that have no geographic prefix word (e.g., "Nice" alone), the check won't classify them as all-place-like. This is conservative — false negatives over false positives per D55.

4. **Generation non-determinism.** The 2-stop Riviera tour may produce different stops on different runs. This run produced Cap d'Antibes + Cap Ferrat (vs. Cap d'Antibes + La Croisette in ROUND4). The detector fixes are deterministic regardless of generated content.
