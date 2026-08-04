##### READY FOR REVIEW

## LOCAL-183 Round 2 — Controlled A/B: corpus wiring ON vs OFF

**Commit:** `0d5cac3`  
**Branch:** `kiro/local183-wire-stop-corpus-into-generation`  
**Cost:** $0.21 (two tours: $0.0991 + $0.1067, within $0.50 ceiling)

---

## Changes (this round)

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `DISABLE_STOP_CORPUS=1` env var feature flag around stop_corpus fetch (lines 4851–4900). When set, `_stop_corpus_data` stays `{}`, both injection paths (fact extraction merge + direct prompt append) no-op. |
| `tests/test_local183_controlled_ab.py` | New: controlled A/B experiment script — generates two tours from same request, one with and one without the wiring, compares itineraries and ANCHORED scores. |

---

## Finding: The generator picks different stops between runs

LEAD predicted this. The two runs produced **40% itinerary overlap** (6/15 shared stops):

```
Run A (no corpus, tour 157):     Run B (with corpus, tour 158):
  Vieux Nice                        Promenade des Anglais
  Promenade des Anglais             Cap Ferrat Lighthouse
  Paloma Beach                      Paloma Beach
  Cap Ferrat                        Jardin Exotique de Monaco
  Villa Ephrussi de Rothschild      Monaco Grand Prix Circuit
  Monaco Grand Prix Circuit         Monte Carlo Casino
  Menton Old Town                   Eze Village
  Château de la Chèvre d'Or         Villefranche-sur-Mer
  Eze Village                       Musée Matisse
  Saint-Paul-de-Vence               Saint-Paul de Vence
  Fort Carré                        Marineland Antibes
  Port Vauban                       Fort Carré
  Cap d'Antibes                     Cap d'Antibes
  La Croisette                      Île Sainte-Marguerite
  Grasse Perfumery                  Cannes Croisette
```

**Shared:** Cap d'Antibes, Eze Village, Fort Carré, Monaco Grand Prix Circuit, Paloma Beach, Promenade des Anglais

**Root cause:** Stop selection happens at line ~3328 (via LLM), stop_corpus fetch happens at line ~4862 (AFTER selection). The corpus cannot influence stop choice. Different stops are pure LLM stochasticity across two separate API calls.

**Implication:** A clean A/B comparison through regeneration is not possible without a fixed-stop-list injection mechanism (which does not currently exist). The comparison must be made on the 6 shared stops only.

---

## Results

### Overall scores (confounded — different itineraries)

| Tour | ANCHORED | Notes |
|------|----------|-------|
| 29 (field-tested, old gen) | 32.3% | Baseline from D57 |
| 152 (new gen, no corpus) | 12.9% | Round 1 reference |
| **157 (no corpus wiring)** | **16.1%** | Run A this round |
| **158 (with corpus wiring)** | **12.9%** | Run B this round |

Overall delta: -3.2pp. **Cannot be interpreted** due to different itineraries.

### Shared-stop comparison (controlled)

| Stop | A (no corpus) | B (with corpus) | Has corpus? |
|------|---------------|-----------------|-------------|
| Cap d'Antibes | 1/2 = 50% | **2/2 = 100%** | ✓ |
| Eze Village | 0/2 = 0% | 0/2 = 0% | ✓ |
| Fort Carré | 0/2 = 0% | 0/2 = 0% | ✗ |
| Monaco Grand Prix Circuit | 0/2 = 0% | 0/2 = 0% | ✗ |
| Paloma Beach | 0/2 = 0% | 0/2 = 0% | ✓ |
| Promenade des Anglais | 0/2 = 0% | 0/3 = 0% | ✓ |
| **TOTAL** | **1/12 = 8.3%** | **2/13 = 15.4%** | |

Delta on shared stops: **+7.1pp**. Driven entirely by Cap d'Antibes gaining one additional ANCHORED paragraph.

### Qualitative evidence the wiring works

**Musée Matisse** (only in run B, 2/2 = 100% ANCHORED):

Corpus passage: "The museum, which opened in 1963, is located in the Villa des Arènes, a seventeenth-century villa"

Generated text: "The museum, inaugurated in 1963, pays homage to the master's unparalleled ability..." and "located within the striking seventeenth-century Villa des Arènes"

→ The model extracted and paraphrased the specific date and building name from the injected passage.

**Cap d'Antibes** (shared stop, improvement from 50% → 100%):

Corpus provides: Antibes geography, Fitzgerald/Tender Is the Night connection.
Generated text (run B) mentions: "Hôtel du Cap-Eden-Roc", city demographics, artistic heritage — proper nouns the detector can match against corpus text.

---

## Prompt injection evidence

When wiring is active, the prompt for each stop with corpus receives:

```
PER-STOP SOURCE MATERIAL for "Cap d'Antibes" (from verified sources — use this as your primary factual basis):
  Passage 1: Antibes (, US also , French: [ɑ̃tib] ; Occitan: Antíbol...) is a seaside resort city...
  Passage 2: Tender Is the Night is the fourth and final novel completed by American writer F. Scott Fitzgerald...
  Sources:
  [Antibes] https://en.wikipedia.org/wiki/Antibes (tier 1)
  [Fitzgerald-Cap d'Antibes connection] https://en.wikipedia.org/wiki/Tender_Is_the_Night (tier 1)

GROUNDING RULE (D50 — critical): Substantiate claims ONLY from the passages above.
Do NOT supplement with facts from your own training data that are not in these passages.
If the passages do not mention something, do not assert it as fact.
You may describe what is physically visible at the stop and provide general orientation,
but specific historical claims, dates, people, and events MUST come from the passages above.
If a passage names a person or event, you may include it; if it does not, leave it out.
```

This block (800–2200 chars per stop) is appended to the description prompt ONLY when `DISABLE_STOP_CORPUS` is not set.

---

## stops_count bug (reported, not fixed)

Tours 153, 154, 156 from round 1 all have `stops_count=0` in the database despite content parsing to 15 stops. The generation service's INSERT/UPDATE path does not persist the parsed stop count. My round 2 script explicitly sets `stops_count` in the INSERT and tours 157, 158 correctly show 15.

Root cause: the service path that stores tours (in `tour_generation_service.py` or `generate_tour_text_service.py`) does not count parsed stops before persisting. This is a separate task.

---

## Limitations

1. **Small sample.** Only 6 shared stops, only 1 showed improvement. The +7.1pp delta on shared stops is directional but not statistically significant with N=12 paragraphs.

2. **Cannot control itinerary by regeneration.** The LLM picks different stops each run. A definitive test requires either: (a) a fixed-stop-list parameter in `generate_tour_text()`, or (b) deterministic seed/temperature=0 — neither exists currently.

3. **Model may not fully comply with grounding rule.** Eze Village has corpus (Wikipedia passage about the commune) but scored 0% in both runs. The model wrote generic text despite being given specific facts. This suggests the grounding instruction is not always followed — a prompt engineering problem rather than a data delivery problem.

4. **Promenade des Anglais matched wrong corpus passage.** The lookup matched it to a passage about "promenade Maurice Rouvier" in Beaulieu-sur-Mer (because the word "promenade" appears in both). This is a data-quality / matching-logic issue in `stop_corpus_reader._match_stop_to_corpus()`.

---

## Constraints verified

- [x] No container rebuilds
- [x] No `DELETE FROM`
- [x] Test tours flagged `is_test = true` (tours 157, 158)
- [x] Nice production list: `[1, 12, 14, 17, 21, 24, 27, 28, 29]`
- [x] Detector unchanged
- [x] No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md
