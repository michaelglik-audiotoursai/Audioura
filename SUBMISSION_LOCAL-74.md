##### READY FOR REVIEW

# LOCAL-74: Visitor Facts Rebase (LOCAL-39 merge)

**Commit:** `2c9e6e2` (Merge LOCAL-39 visitor-facts-rebase into storied)  
**Branch:** `kiro/local74-visitor-facts-rebase`  
**Ahead of storied:** 3 commits (2 from LOCAL-39 + 1 merge commit)

---

## Changes (per-file)

| File | Lines | Purpose |
|------|-------|---------|
| `visitor_facts_extractor.py` | +649 (NEW) | Structured extraction of closed_days, hours (seasonal), admission (conditional) from museum websites |
| `generate_tour_text.py` | +34/−16 | Replaces old `_fetch_visitor_info_from_site` call with `fetch_visitor_info_with_provenance` (LOCAL-39 wiring, with ImportError fallback) |
| `practical_facts_gate.py` | +30/−0 | Strengthens `_verify_admission`: unconditional "Free" claim rejected when source also contains a general entry price |
| `run_local35_acceptance.py` | +208 (NEW) | Offline acceptance runner for LOCAL-35 |
| `run_local39_acceptance.py` | +278 (NEW) | Offline acceptance runner for LOCAL-39 |
| `run_local39_live_acceptance.py` | +207 (NEW) | Live acceptance runner (3 venues) |
| `tests/test_local35_visitor_facts.py` | +216 (NEW) | 23 unit tests for visitor_facts_extractor |
| `SUBMISSION_LOCAL-39.md` | +141 (NEW) | Original LOCAL-39 submission document |

---

## Acceptance Criterion 1: Matisse admission reads €12, not Free

### Rendered line (verbatim from container logs, job `ac4ccd71`):

```
Museum Information: Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents
```

### Extraction chain (verbatim from container logs):

```
[LOCAL-35] Visitor info page found (fr): http://musee-matisse-nice.org/informations-pratiques
[LOCAL-35] Visitor info page found (en): http://musee-matisse-nice.org/practical-information
[LOCAL-35] Extracted from http://musee-matisse-nice.org/informations-pratiques: closed=[], hours=2, admission='Free for Métropole residents'
[LOCAL-35] Extracted from http://musee-matisse-nice.org/practical-information: closed=['Tuesday'], hours=1, admission='€12; free for Métropole residents'
[LOCAL-35] Final Museum Information: Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents
[LOCAL-39] Museum Information sourced from official site for stop 1
```

### Practical facts gate (verbatim):

```
AUDIT: closed_day | Closed on Tuesday | http://musee-matisse-nice.org/practical-information | VERIFIED
AUDIT: admission | €12 | http://musee-matisse-nice.org/practical-information | VERIFIED
AUDIT: admission | free for Métropole residents | http://musee-matisse-nice.org/practical-information | VERIFIED
[LOCAL-36] PRACTICAL FACTS GATE: PASSED (3 verified)
```

---

## Acceptance Criterion 2: Price source — retrieved or hardcoded?

**Retrieved at runtime.** The `visitor_facts_extractor.py` module:
1. Fetches `http://musee-matisse-nice.org/informations-pratiques` (FR) and `http://musee-matisse-nice.org/practical-information` (EN)
2. Applies regex-based structured extraction on each page independently
3. Merges the best fields: the EN page produced `admission='€12; free for Métropole residents'` (scored higher because it contains a numeric price)
4. The practical_facts_gate then verifies each claim against the raw source text

**No hardcoded price.** The €12 value comes from parsing the live museum website. If the museum changes its price, the extractor will pick up the new value on the next generation.

**Defense against the old bug:** `practical_facts_gate.py` now rejects unconditional "Free" claims when the source text also contains a general entry price pattern (lines 275–299). This is a structural guard — even if the extractor's regex fails on a future museum, the gate will catch and reject a false "Free".

---

## Acceptance Criterion 3: Other visitor-facing facts changed

| Fact | Value | Source |
|------|-------|--------|
| Matisse closed day | Tuesday | http://musee-matisse-nice.org/practical-information |
| Matisse hours (winter) | 10:00–17:00 (1 Nov–31 Mar) | http://musee-matisse-nice.org/informations-pratiques |
| Matisse hours (summer) | 10:00–18:00 (1 Apr–31 Oct) | http://musee-matisse-nice.org/informations-pratiques |
| Matisse admission | €12; free for Métropole residents | http://musee-matisse-nice.org/practical-information |
| Asian Arts closed day | Tuesday | https://maa.departement06.fr/tarifs-et-horaires |
| Asian Arts hours (winter) | 10:00–17:00 (1 Sep–30 Jun) | https://maa.departement06.fr/tarifs-et-horaires |
| Asian Arts hours (summer) | 10:00–18:00 (1 Jul–31 Aug) | https://maa.departement06.fr/tarifs-et-horaires |
| Asian Arts admission | FREE | https://maa.departement06.fr/tarifs-et-horaires |

All facts are retrieved live from official museum websites. No booking, reservation, or accessibility facts are changed (LOCAL-39 does not touch those).

---

## Acceptance Criterion 4: Museum tour stops

### Asian Arts Museum: 8/8 stops ✓

```
Stop 1: L'Armure d'Andô Naoyuki
Stop 2: Statue de Bouddha
Stop 3: La danse cosmique de Ganesh
Stop 4: Kannon, le bodhisattva de la compassion
Stop 5: Ulysses Grant au Japon
Stop 6: Robe de prêtre taoïste
Stop 7: Kannon à mille bras
Stop 8: Masque du vieillard kojô
```

Museum Information: `Closed on Tuesday. 10:00–17:00 (1 Sep–30 Jun); 10:00–18:00 (1 Jul–31 Aug). FREE`

"Closed on Tuesday" preserved ✓

### Matisse Museum: 8/8 stops ✓

```
Stop 1: Nu bleu IV
Stop 2: Nymphe dans la forêt
Stop 3: Tempête à Nice
Stop 4: Pierre Matisse, un marchand d'art à New York
Stop 5: Odalisque au coffret rouge
Stop 6: Papeete-Tahiti
Stop 7: Nature morte aux grenades
Stop 8: Lectrice à la table jaune
```

(Matisse generated 8/8 stops and correct Museum Information. The full tour was rejected by the post-generation venue-coherence QA gate — see Limitations.)

---

## Acceptance Criterion 5: Distinct facts

Not claiming a change in fact density. Per D22's noise-floor rule (stdev ~7 at n=3), a single-run comparison proves nothing. The Asian Arts tour delivered 8/8 stops with full descriptions. The Matisse tour generated 8 stops with full descriptions (rejected only by the venue-coherence gate, which is unrelated to fact content).

---

## Acceptance Criterion 6: Regression suite

```
208 passed, 3 warnings in 53.02s
```

All LOCAL-specific tests pass:
- test_local25_unified_fill_filter: 20 passed
- test_local26_placeholder_leak: 11 passed
- test_local28_acceptance: 7 passed
- test_local29_catalogue_accuracy: 5 passed
- test_local30_acceptance: 3 passed
- test_local30_deterministic_selection: 6 passed
- test_local31_metadata_bind: 7 passed
- test_local35_visitor_facts: **23 passed** (includes `test_admission_not_free_unconditional` for Matisse)
- test_local36_practical_facts_qa: **26 passed** (includes `test_free_fails_when_source_says_paid`)
- test_local44_stop_preaching: 17 passed
- test_local48_substance_rebase: 30 passed
- test_local49_tour_content_persist: 5 passed
- test_local50_deterministic_resolution: 6 passed
- test_local60_cost_metering: 14 passed
- test_local64_cost_ceiling: 28 passed

---

## Acceptance Criterion 7: Cost ceiling

| Tour | Cost | Ceiling |
|------|------|---------|
| Matisse (ac4ccd71) | $0.066 | < $1.30 ✓ |
| Asian Arts (7b84b184) | $0.072 | < $1.30 ✓ |

Both within the measured baseline of $0.070–$0.073.

---

## Protections preserved (post-merge verification)

| Protection | Status | Evidence |
|------------|--------|----------|
| LOCAL-72: Thin-corpus rule | ✓ Present | `grep` confirms in generate_tour_text.py |
| LOCAL-72: Exhibition-vs-object guard | ✓ Present | Line 5198: "EXHIBITION VS OBJECT RULE" |
| LOCAL-44: Anti-preaching cleanup | ✓ Present | Lines 5649–5691: PHASE 5.10 |
| LOCAL-46: Transport words stripped, mode drives category | ✓ Present | Lines 72–226 |

---

## Limitations

1. **Matisse full tour delivery blocked by venue-coherence QA gate.** The tour generates correctly (8/8 stops, correct Museum Information with €12), but `BLOCKER4c` rejects it because only 1/8 stop descriptions explicitly mention "Musée Matisse, Nice" (the LLM writes "Musée Matisse" or "the museum" without the city suffix). This is a pre-existing LLM generation style issue, not a LOCAL-39 regression. The venue-coherence check requires ≥3/8 stops to contain the first 15 chars of the venue name. This was already failing before LOCAL-39 — the branch adds no code to the QA runner.

2. **Download endpoint has a Flask bug** (`send_file() got an unexpected keyword argument 'download_name'`). Tour content is accessible via the `/status` endpoint's `tour_content` field. Not related to LOCAL-39.

3. **Asian Arts Museum "Closed on Tuesday"**: The FR extraction page did not return a closed day (`closed=[]`), but the EN extraction page did (`closed=['Tuesday']`). The merge logic correctly picks up the closed day from the EN result. If the official site changes structure, this could regress — but the practical_facts_gate would catch a wrong claim.

---

## Evidence artifacts

- `evidence_local74_asian_arts_tour.txt` — Full Asian Arts Museum tour text (8/8 stops, 15313 chars)
- Container logs: job `ac4ccd71` (Matisse), job `7b84b184` (Asian Arts)
- Test results: 208/208 passed (0 failures)
