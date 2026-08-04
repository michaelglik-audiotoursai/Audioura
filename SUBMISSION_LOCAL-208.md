##### READY FOR REVIEW

## LOCAL-208: French Riviera 2-Stop Cycling Tour for Michael

**Commit:** `4e8db3c`
**Branch:** `kiro/local208-riviera-2stop-for-michael`
**Base:** `storied`

---

### Per-File Summary

| File | Purpose |
|------|---------|
| `RIVIERA_2STOP_FOR_MICHAEL.md` | Annotated deliverable — 6 paragraphs numbered, anchor/style/coverage per paragraph |
| `tours/LOCAL208_riviera_2stop_for_michael.txt` | Raw generated text (D71 — persisted) |
| `tours/LOCAL208_riviera_2stop_for_michael_evidence.json` | Pipeline evidence trace |
| `run_local208_riviera_2stop.py` | Generation script (STORIED_MODE=true, 2 stops, all gates ON) |
| `run_local208_postprocess.py` | Post-processing: style validator + anchor detector + annotated markdown |

---

### Verbatim Evidence

**audio_tours count:**
```
[PRE] audio_tours row count: 117
audio_tours total: 118 (delta: +1)
```

**Nice list unchanged:**
```
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] (expected: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152])
Nice list matches expected: YES
```

**Tour stored safely:**
```
Stored as tour_id=163 (is_test=true, lat/lng=NULL)
```

**Coverage verdicts (pre-narration):**
```
Cap d'Antibes: COVERED (passages=8, matched=['antibes'])
Villefranche-sur-Mer: NO_CORPUS (no stop_corpus data; used Wikipedia retrieval)
```

**Pipeline gates fired:**
```
[LOCAL-198] Corpus gate: ENABLED — checking stop coverage...
[CORPUS-GATE] stop='Villefranche-sur-Mer' verdict=EMPTY action=SHORTENED
[LOCAL-198] Corpus gate: 1 PASSED, 0 CREATOR_ONLY, 1 SHORTENED
[LOCAL-192] Style retry summary: 2 paragraphs retried, 2 fixed/improved, 0 kept original
[LOCAL-36] PRACTICAL FACTS GATE: 1 claim(s) dropped
```

**Generation cost:**
```
Total API cost: $0.0086 (10755 tokens)
SPINE_COST: tokens=1259 cost=$0.0104
Style retry cost: $0.0007 (824 tokens)
```

**git status clean:**
```
$ git status --short
(empty — all committed)
```

---

### Per-Paragraph Annotations (from RIVIERA_2STOP_FOR_MICHAEL.md)

| # | Stop | Anchor | Style | Coverage |
|---|------|--------|-------|----------|
| 1 | Cap d'Antibes | UNLINKED_ENTITY | R1_IMPERATIVE | COVERED |
| 2 | Cap d'Antibes | UNLINKED_ENTITY | R1_IMPERATIVE | COVERED |
| 3 | Cap d'Antibes | ANCHORED | clean | COVERED |
| 4 | Villefranche-sur-Mer | UNLINKED_ENTITY | R1_IMPERATIVE | NO_CORPUS |
| 5 | Villefranche-sur-Mer | UNLINKED_ENTITY | clean | NO_CORPUS |
| 6 | Villefranche-sur-Mer | UNLINKED_ENTITY | clean | NO_CORPUS |

---

### Limitations

1. **Paragraph 1 is orientation/directions content** — the parser treats orientation text as narration (by design, per `stop_anchor_detector_v2.py:705`). The R1 hit is from imperatives like "Start biking", "Take the second exit", "Look out for". This is route instruction, not narration style failure.

2. **Paragraph 2 is the prolog** (D64) — stapled inside Stop 1. It has R1 ("Join us as we delve…") which is an imperative inviting the listener. The style retry did not target this paragraph (it retried paragraphs 4 and the now-fixed paragraph in stop 1).

3. **Villefranche-sur-Mer has NO_CORPUS** — no stop_corpus data exists for this stop. The pipeline used Wikipedia retrieval and flagged it SHORTENED via the corpus gate. Despite this, the narration still ran to ~3 paragraphs because SHORTENED reduces paragraph length, not count.

4. **Anchor detector limited without story_elements** — for outdoor/biking tours, the stop_corpus `pages_json` has passage text but no `story_elements_json`. The anchor detector falls back to UNLINKED_ENTITY for paragraphs that mention real entities not found in (the sparse) corpus data. Only paragraph 3 (Cap d'Antibes) achieves ANCHORED because the corpus text explicitly mentions "Antibes" keywords.

5. **Total cost: ~$0.020** — well under the $0.30 ceiling.

6. **No container rebuild performed.**
