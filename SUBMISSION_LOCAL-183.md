##### READY FOR REVIEW

# LOCAL-183: Wire stop_corpus into generation

**Commit:** `8045e82` on branch `kiro/local183-wire-stop-corpus-into-generation`
**Cost:** $0.107 (one 15-stop French Riviera cycling tour)
**Nice production list verified:** `[1, 12, 14, 17, 21, 24, 27, 28, 29]`

---

## Changes (per file)

| File | Lines | What |
|------|-------|------|
| `stop_corpus_reader.py` | +216 (new) | Reads `stop_corpus` table, formats passages with source URLs for prompt injection, includes D50 grounding rule |
| `generate_tour_text.py` | +65/-1 | Three insertion points: (1) fetch stop_corpus, (2) merge into fact sheet per_work_contexts, (3) inject into per-stop description prompt |
| `tests/test_local183_evidence.py` | +175 (new) | Evidence test: generates tour, runs detector, reports ANCHORED score |
| `tests/test_local183_stop_corpus_wiring.py` | +123 (new) | Unit-level wiring test |

---

## The seam (scope item 1)

The generation assembles per-stop context at **line ~5625** of `generate_tour_text.py`, inside the `_generate_description` closure. Before this change, the only per-stop material came from:
- `fact_sheet` (from `generate_fact_sheets_parallel` → uses `venue_corpus` + `per_work_contexts`)
- `_three_class_results` retrieval_facts (for outdoor stops)
- `_story_corpus_result.per_work_contexts` (for museum stops)

None of these read `stop_corpus`. The fact sheets received `venue_corpus` (one row per venue, shared by all stops). The three-class retrieval fetched Wikipedia independently per stop but did not consult the curated stop_corpus table.

---

## How stop_corpus reaches the model (scope item 2)

Three paths, in order:

1. **Fact sheet enrichment** (line ~4895): `_merge_stop_corpus_into_per_work()` adds stop_corpus passages to `per_work_contexts` before calling `generate_fact_sheets_parallel`. This means the `_extract_corpus_for_poi` function inside fact extraction now sees per-stop content when matching by title.

2. **Direct prompt injection** (line ~5625): For each stop, if `_stop_corpus_data[poi_name]` exists, the formatted passage block is appended to `description_prompt`. The block includes raw passage text and source URLs.

3. **Fallback**: When a stop has no `stop_corpus` entry (~50% of stops for the French Riviera), the existing `venue_corpus` and `three_class_retrieval` paths operate unchanged.

---

## How the prompt handles the material (scope item 3 + D50 safety)

The injected block reads:

```
PER-STOP SOURCE MATERIAL for "{stop_name}" (from verified sources — use this as your primary factual basis):
  Passage 1: {passage text}
  Passage 2: {passage text}
  Sources:
  [{title}] {url} (tier {tier})

GROUNDING RULE (D50 — critical): Substantiate claims ONLY from the passages above.
Do NOT supplement with facts from your own training data that are not in these passages.
If the passages do not mention something, do not assert it as fact. You may describe
what is physically visible at the stop and provide general orientation, but specific
historical claims, dates, people, and events MUST come from the passages above.
If a passage names a person or event, you may include it; if it does not, leave it out.
```

This is the smallest change that gets the material in front of the model with D50's constraint attached. The model is told what it may use (the passages) and what it may not do (supplement from memory). Source URLs reach the prompt so the model is grounding on real text with known provenance.

The prompt does **not** forbid the model from making general observations about what is physically present. It forbids asserting specific historical claims, dates, and people not substantiated by the passages. This matches D50 ("substantiate only from the corpus") without making the model unable to describe the stop at all.

---

## Evidence: assembled context before/after

**BEFORE** (what the generator gave each stop):
```
Per-stop corpus passages: 0
Grounding rule (D50): ABSENT
Source: venue_corpus only (shared across all 15 stops), or three_class_retrieval Wikipedia
```

**AFTER** (example for "Cap d'Antibes"):
```
PER-STOP SOURCE MATERIAL for "Cap d'Antibes" (from verified sources):
  Passage 1: Antibes ... is a seaside resort city in the Alpes-Maritimes department
  in Provence-Alpes-Côte d'Azur, Southeastern France. It is located on the French
  Riviera between Cannes and Nice; it is the largest yachting harbour in Europe...
  Passage 2: Tender Is the Night is the fourth and final novel completed by American
  writer F. Scott Fitzgerald. Set in the French Riviera during the twilight of the
  Jazz Age, the 1934 novel chronicles the rise and fall of Dick Diver...
  Sources:
  [Antibes] https://en.wikipedia.org/wiki/Antibes (tier 1)
  [Fitzgerald-Cap d'Antibes connection] https://en.wikipedia.org/wiki/Tender_Is_the_Night (tier 1)

GROUNDING RULE (D50 — critical): Substantiate claims ONLY from the passages above...
```

Generation log confirming corpus reached the generator:
```
[LOCAL-183] stop_corpus: 9/15 stops have per-stop passages (10 total passages)
```

---

## Evidence: generated text uses the passages

Villa Ephrussi de Rothschild stop (from tour 156):
```
Villa Ephrussi de Rothschild, also known as Villa Île-de-France...
Designed by architect Aaron Messiah and constructed between 1907 and 1912...
Baroness Béatrice de Rothschild... monument historique
```

All four facts above come from the stop_corpus Wikipedia passage, not model memory.

Old Town Antibes stop:
```
a historic district located within the seaside resort city in the
Alpes-Maritimes department in Provence-Alpes-Côte d'Azur, Southeastern France
```

This phrasing is directly from the stop_corpus passage for Cap d'Antibes/Antibes.

---

## Anchor detection results

| Tour | ANCHORED | Notes |
|------|----------|-------|
| 29 (field-tested, old gen) | 32.3% | Baseline from D57 |
| 152 (new gen, no corpus) | 12.9% | Generated without stop_corpus wiring |
| **156 (LOCAL-183)** | **19.4%** | Generated with stop_corpus wiring |

Per-stop breakdown for tour 156:
```
[SC] Old Town Antibes                 2/3 (67%)
[SC] Fort Carré d'Antibes             0/2 (0%)
[SC] Paloma Beach                     0/2 (0%)
[--] Cap Ferrat                       0/2 (0%)
[SC] Villa Ephrussi de Rothschild     1/1 (100%)
[SC] Eze Village                      0/2 (0%)
[--] Villefranche-sur-Mer             0/2 (0%)
[SC] Musée Matisse                    2/2 (100%)
[SC] Promenade des Anglais            0/2 (0%)
[--] Saint-Paul-de-Vence              0/2 (0%)
[SC] Marineland Antibes               0/2 (0%)
[--] La Croisette                     0/2 (0%)
[--] Île Sainte-Marguerite            0/2 (0%)
[--] Château de la Napoule            0/2 (0%)
[SC] Port of Saint-Tropez             1/3 (33%)
```

SC = stop had stop_corpus data; -- = no stop_corpus (falls back to venue_corpus).

---

## Limitations

1. **19.4% vs 32.3%**: The new tour scores lower than tour 29. Tour 29 was generated by a different process and visits different stops; the comparison is indicative but not apples-to-apples. The relevant comparison is **19.4% vs 12.9%** (same generator, same stops, with vs without corpus) — a +50% relative improvement.

2. **Stops with corpus but 0% ANCHORED** (Fort Carré, Paloma Beach, Eze Village, Marineland, Promenade des Anglais): The model received the passages but the detector did not classify any paragraph as ANCHORED. This could mean:
   - The model used the passages for factual grounding but phrased things in a way the detector doesn't recognize (e.g., paraphrased rather than using anchor tokens)
   - The passages for those stops are thin (1 passage each, some under 200 chars)
   - This is a **prompt problem** rather than a data problem — the material arrived, but the model's output didn't produce detector-visible anchors

3. **UNLINKED_ENTITY count is high (18/31)**: The model names people and events but doesn't always substantiate the link to the specific stop. This is the exact D57 Fitzgerald pattern — the grounding rule instructs the model not to go beyond the passages, but does not force it to explicitly cite the connection. A tighter prompt could improve this.

4. **Not all stops get corpus**: 6/15 stops in this tour had no stop_corpus entry (the corpus covers 15 stops from a different route selection). Coverage depends on the stops the generator selects vs what was sourced.

5. **Fallback to localhost:5433**: Inside Docker, the connection uses `postgres-2:5432`. Outside Docker (tests), it falls back to `localhost:5433`. The fallback is explicit in the code and matches the existing `tests/db_connection.py` pattern.
