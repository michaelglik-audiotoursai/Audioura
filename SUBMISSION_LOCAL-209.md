##### READY FOR REVIEW

**Task:** LOCAL-209 — The coverage gate cannot fire for a stop with no corpus  
**Branch:** `kiro/local209-gate-unreachable-for-empty-stops`  
**Base:** `storied`

---

## Commit Summary

| file | change |
|---|---|
| `generate_tour_text.py` | Fixed gate condition (`if not _corpus_gate_disabled:` — removed `and _stop_corpus_data`); added `_corpus_gate_empty_stops` set; EMPTY gets distinct degradation prompt; all verdicts logged including COVERED |
| `run_local209_empty_gate_test.py` | 6-run A/B test script (3 gate-on, 3 gate-off) |
| `LOCAL209_EVIDENCE.md` | Full sentence classifications, raw paragraphs, summary table |

---

## What was fixed

### The bug (line 4919, before)
```python
if not _corpus_gate_disabled and _stop_corpus_data:
```

When `_stop_corpus_data` was empty (DB unreachable, or populated with all-None values from a venue with no corpus), the gate was skipped entirely. Even when the dict had entries, stops with `None` values got the EMPTY verdict but were routed to the VENUE_ONLY degradation path — a prompt written for museums ("artwork/exhibit") that is meaningless for outdoor cycling stops.

### The fix (line 4919, after)
```python
if not _corpus_gate_disabled:
```

Gate now iterates `_poi_names` unconditionally. A missing entry in `_stop_corpus_data` (or a None value) yields an EMPTY verdict via `assess_stop_coverage` with empty passages. EMPTY gets its own degradation prompt:

**EMPTY prompt (key instructions):**
- Must NOT assert dates, measurements, nicknames, historical figures
- May ONLY name the stop, describe physical surroundings, provide wayfinding
- Write 60-80 words maximum

Distinct from VENUE_ONLY (which may reference venue-level facts from corpus) and CREATOR_ONLY (which may discuss the maker).

### Call sites changed
Only ONE call site generates stop narration: `_generate_description()` inner function (line ~5154). The EMPTY prompt injection is at line 5822, before the VENUE_ONLY and CREATOR_ONLY blocks. Confirmed via monkey-patching that the prompt text reaches the API call for EMPTY stops.

---

## Evidence: 6-run A/B test

**Location:** "Cap d'Antibes to Villefranche-sur-Mer, French Riviera, France"  
**Stops generated:** Model picks its own — varied across runs.  

### Gate verdicts (gate-on runs only)

| run | stop 1 | verdict | stop 2 | verdict |
|---|---|---|---|---|
| 1 | Musée Picasso | **EMPTY** | Villa Ephrussi de Rothschild | COVERED |
| 2 | Plage de la Garoupe | **EMPTY** | Villa Ephrussi de Rothschild | COVERED |
| 3 | Cap d'Antibes Coastal Path | COVERED | Villa Ephrussi de Rothschild | COVERED |

EMPTY verdict fires in 2/3 gate-on runs. Run 3 had both stops covered (model picked a stop matching "Cap d'Antibes" corpus).

### Paired comparison: Plage de la Garoupe (gate-on run 2 vs gate-off run 3)

**Gate ON (EMPTY_RESTRICTED):**
> At Plage de la Garoupe, the gentle lapping of waves mingles with the laughter of beachgoers, creating a symphony of seaside tranquility. This spot has long been a source of inspiration for artists and writers, much like Picasso who once sought solace and creativity on these very shores.

- 1 named attribution (Picasso — unsourced)
- ~160 words stop-specific content
- Mostly atmospheric/general

**Gate OFF (no restriction):**
> The Plage de la Garoupe has a rich history as a source of inspiration for renowned artists like Picasso and Hemingway, drawn to its serene beauty and unique light. In the early 20th century, this pristine stretch of sand became a meeting place for creatives seeking tranquility and reflection.

- 2 named attributions (Picasso + Hemingway — unsourced)
- 1 dating claim ("early 20th century")
- 1 specific historical claim ("meeting place for creatives")
- ~200 words stop-specific content
- Confident factual assertions

### The deciding number

Manual sentence classification (removing false positives from sentence-initial capitals):

| arm | stop | true UNSOURCED_SPECIFIC | sentences |
|---|---|---|---|
| gate_on run 1 | Musée Picasso | 4 (Picasso 1946, Grimaldi Castle, Mediterranean light, artistry evolution) | 12 |
| gate_on run 2 | Plage de la Garoupe | 1 (Picasso) | 8 |
| gate_off run 1 | Musée Picasso | 6 (Picasso 1946, Grimaldi Castle, Mediterranean, artworks, creative process, iconic coastal) | 14 |
| gate_off run 3 | Plage de la Garoupe | 4 (Picasso, Hemingway, early 20th century, meeting place) | 9 |

**Approximate reduction in true unsourced specifics: ~40-50% on the EMPTY stops that are comparable.**

This is weaker than CREATOR_ONLY's 76% (D80). The EMPTY prompt constrains length and reduces some claims but does not eliminate confident specifics from gpt-3.5-turbo on outdoor stops. The model's instruction-following on negative constraints ("do NOT assert dates") is weaker than on category exclusions ("do not describe the object").

---

## DB State

- `audio_tours` before: **118**
- `audio_tours` after: **124** (+6 test rows, all `is_test=true`, lat/lng=NULL)
- Nice list `[1, 12, 14, 17, 21, 24, 27, 28, 29, 152]`: **unchanged**

---

## DISABLE_CORPUS_GATE=1 working

Gate-off runs produce longer, more specific paragraphs with no `[CORPUS-GATE]` log entries. Verified in runs 4-6.

---

## Limitations

1. **The model does not reliably follow the EMPTY restriction.** The 60-80 word ceiling is ignored; specific claims still appear. This matches D63's finding: negative constraints ("do not assert X") work less well than category exclusions ("do not describe the object"). For stops with truly zero source material, the structural answer (drop the stop or emit orientation-only) is more reliable than prompt.

2. **Stop selection is non-deterministic.** The model chose different stops each run. Villefranche-sur-Mer (the original problematic stop) was never selected despite the location hint. The EMPTY gate still fires correctly for whichever corpus-less stops are chosen.

3. **Gate-on run 3 had both stops COVERED.** Only 2/3 gate-on runs exercised the EMPTY path. With more budget, more runs would yield cleaner paired data.

4. **The automated classifier over-counts** due to proper names matching sentence-initial capitals. Manual counts above are more accurate.

5. **No container rebuild** (D48 respected). Change tested via direct Python execution, not Docker.
