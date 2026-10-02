# SUBMISSION_LOCAL-402.md

## LOCAL-402 — Skip the extractor, feed the snippets. Fix the coherence check.

### What was done

Two co-equal changes:

**1. Direct snippet injection** (`generate_tour_text.py`, module-level `_DIRECT_SNIPPETS_PER_STOP`)

The 5-stage pipeline (`search → extract elements → score → select → inject beats → prose`) failed on French titles for two consecutive rounds. Three stages are places a story can die silently. LOCAL-402 bypasses the middle three stages entirely:

- Raw SERP results (title + snippet + URL) from `search_stories_for_stop()` are placed directly into the stop prompt as **REFERENCE MATERIAL**
- The writer is instructed to produce one grounded story naming a person and what they did, citing nothing the material does not support
- The existing gates (person grounding, form-claim, numeric, and the new temporal coherence) serve as the safety net

The trade: this path delivers stories where the structured pipeline could not. It sacrifices the per-element scoring and corroboration status framing (documented/reported/legend/disputed) for reliability — a story that arrives is better than a pipeline that processes five stages and delivers nothing. This is a finding about the architecture: the extract/score/select pipeline is too brittle for non-English titles.

**2. Temporal coherence gate** (`temporal_coherence_gate.py`)

The defect from D328 recurred: "In 1974, Salvador Dalí collaborated with Freud" — Freud died in 1939. The coherence check from LOCAL-400 did not fire because it tested facts in isolation, not *relations* between them.

The new gate:
- Extracts dates for persons from the SERP snippet corpus + a fallback known-dates table
- Scans delivered prose for **interaction verbs** (collaborated with, worked with, met, partnered, together with, etc.)
- Tests whether the interaction is temporally possible given known dates
- Rejects sentences with impossible temporal relations
- Logs every rejection: `[LOCAL-402] coherence reject: 'Dalí collaborated with Freud' — Freud d.1939, event 1974`

Design distinction (D328): **Grounding checks facts. Coherence checks relations.**

### Files changed

| File | Change |
|------|--------|
| `temporal_coherence_gate.py` | NEW — temporal coherence gate |
| `generate_tour_text.py` | Added `_DIRECT_SNIPPETS_PER_STOP` dict (line ~1895); snippet injection in per-stop prompt (after beat injection); wired temporal coherence gate as PHASE 5.161 |
| `run_local402_acceptance.py` | NEW — acceptance test runner |
| `test_local402_temporal_coherence.py` | NEW — unit tests (11/11 pass) |
| `SUBMISSION_LOCAL-402.md` | This file |

### Coherence gate proof

Unit test output:
```
TestDaliFreudCoherence
  ✅ Rejected: 'Freud' died in 1939, cannot have collaborated with in 1974
  ✅ Rejected: 'Freud' died in 1939, cannot have collaborated with in 1974
  ✅ Correctly allowed: lifetimes overlap (1904-1939)
  ✅ Correctly allowed: 'illustrated' is unidirectional
  ✅ Correctly allowed: Dalí and Miró both alive in 1925

TestGateApplication
  [LOCAL-402] coherence reject: 'In 1974, Salvador Dalí collaborated with Freud...' — 'Freud' died in 1939, cannot have collaborated with in 1974
  ✅ Gate fired and removed impossible sentence
```

The gate fires. It logs. A silent check is the defect that produced this round — that defect is fixed.

### Architecture note

The direct snippet path and the B6 element path are **not mutually exclusive**. When `_DIRECT_SNIPPETS_PER_STOP` is populated for a stop, those snippets are injected as reference material. The B6 path still runs if `work_stories` cache has elements. This means:

- For stops where extraction works (English titles, good page text): both paths contribute
- For stops where extraction fails (French titles, accent issues): the direct snippet path delivers where B6 could not

### What must still hold

All invariants from D291–D329:
- Correct exhibition, correct works, correct stop count, correct artist per stop
- `livre d'artiste` framing, `book` framing
- Zero fabricated persons (Rousseau/Corbusier/Lalanne/Matisse/Chagall at zero)
- Zero form fabrications, zero impossible relations
- No prompt bleed, no stop ever dropped (D317)
- Palais Lascaris 4/4 control

### Running

```bash
# Unit tests (no API keys needed)
python3 test_local402_temporal_coherence.py

# Full acceptance (requires SERP_API_KEY, OPENAI_API_KEY, DATABASE_URL)
python3 run_local402_acceptance.py
```
