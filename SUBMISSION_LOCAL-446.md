# LOCAL-446: LLM as Wikimedia Substitute — Measurement Report

**Date:** 2026-08-12
**Entities tested:** 40 (15 well-known venues, 15 long-tail works/objects, 10 French-language)
**Models tested:** gpt-4o-mini, gpt-4o
**Branch:** LOCAL-446-llm-wikimedia-substitute

## Answer to Michael's Question

> "Can an LLM return faster or more reliable information when Wikimedia is failing?"

**No.** Neither faster nor more reliable.

- **Not faster.** Wikimedia (healthy) responds in ~108ms median. GPT-4o-mini takes ~1861ms, GPT-4o takes ~1922ms. The LLM is 17× slower than healthy Wikimedia.
- **Not more reliable.** Both models hallucinate Wikidata QIDs at near-100% rate, fabricate official website URLs, and misclassify entity types. The confident-and-wrong rate (asserting falsehoods without hedging) is 25–35%, which is catastrophic for a factual pipeline.
- **Not usable under any guard.** D373 requires that LLM output never be asserted without corroboration from a fetched source. Since the LLM substitute is only needed *when that fetched source is unavailable*, the corroboration requirement cannot be met by design. The dead-host breaker (LOCAL-445) already makes failure fast; there is no shape in which parametric memory fills the gap safely.

---

## Ground Truth Coverage

Harvested live from Wikimedia (2026-08-12, all calls successful):

- Entities with Wikidata QID: 34/40
- Entities with Wikipedia extract: 25/40
- Entities with P856 website: 27/40
- 6 entities had no Wikidata match (very obscure or non-notable)
- 15 entities had no Wikipedia article (French local landmarks)

---

## Model: gpt-4o-mini

### Speed

| Metric | LLM | Wikimedia (healthy) |
|--------|-----|---------------------|
| Median | 1861ms | 108ms |
| P90 | 3466ms | 122ms |
| Min/Max | 1313ms / 4913ms | 98ms / 134ms |

### Accuracy per Field

| Field | Correct | Wrong | Abstained | Accuracy (excl. abstain) |
|-------|---------|-------|-----------|--------------------------|
| qid | 0 | 34 | 6 | **0%** |
| label | 26 | 8 | 6 | 76% |
| wikipedia_extract | 23 | 2 | 15 | 92% |
| official_website | 12 | 9 | 19 | 57% |
| instance_of | 19 | 15 | 6 | 56% |
| country | 33 | 0 | 7 | **100%** |
| city | 27 | 6 | 7 | 82% |

### Confident-and-Wrong: 74 instances

The model never abstains on QIDs — it fabricates plausible-looking Q-numbers with total confidence for every single entity. This alone disqualifies it.

### Cost: $0.00012 per call ($0.005 total for 40 entities)

### Strict Mode Delta

Adding "only answer if you would bet money" to the system prompt produced +2 additional abstentions across 140 field-comparisons. **The strict instruction had negligible effect** — the model does not distinguish what it knows from what it fabricates.

---

## Model: gpt-4o

### Speed

| Metric | LLM | Wikimedia (healthy) |
|--------|-----|---------------------|
| Median | 1922ms | 108ms |
| P90 | 2462ms | 122ms |
| Min/Max | 854ms / 3993ms | 98ms / 134ms |

### Accuracy per Field

| Field | Correct | Wrong | Abstained | Accuracy (excl. abstain) |
|-------|---------|-------|-----------|--------------------------|
| qid | 6 | 28 | 6 | **18%** |
| label | 29 | 5 | 6 | 85% |
| wikipedia_extract | 24 | 0 | 16 | **100%** |
| official_website | 15 | 2 | 23 | 88% |
| instance_of | 22 | 12 | 6 | 65% |
| country | 33 | 0 | 7 | **100%** |
| city | 27 | 6 | 7 | 82% |

### Confident-and-Wrong: 53 instances

GPT-4o is better than 4o-mini on extracts (100% accuracy when it answers) and websites (88%), but still fabricates QIDs and misclassifies entity types. Crucially, it does NOT abstain when wrong — the "only answer if certain" instruction shifted only 4 additional abstentions.

### Cost: $0.00242 per call ($0.097 total for 40 entities) — 20× more expensive than 4o-mini

### Strict Mode Delta

+4 abstentions over 140 comparisons. Again, negligible.

---

## Verbatim Confident-and-Wrong Examples

### 1. QID Hallucination (systemic, affects all entities)
- **Museum of Fine Arts, Boston**: GT `Q49133`, LLM said `Q188740` (4o) / `Q186202` (4o-mini)
- **Centre Pompidou**: GT `Q178065`, LLM said `Q193597` (4o) / `Q12345` (4o-mini)
- **Palais Lascaris**: GT `Q3360882`, LLM said `Q2076225` (4o) / `Q186066` (4o-mini)

### 2. Entity Type Misclassification
- **Palais Lascaris**: GT "palace", LLM said "museum" (4o) — it IS a museum now, but Wikidata classifies it as a palace
- **Centre Pompidou**: GT "cultural center", LLM said "art museum" — it contains a museum but is classified as a cultural center

### 3. Website Fabrication (4o-mini)
- Multiple entities received plausible-looking but incorrect URLs

### 4. City Errors
- Several entities located in Nice arrondissements got city wrong

---

## Analysis: Why QID Failure Is Fatal

The pipeline's `_search_entities` call returns `(qid, label)` tuples. The QID is the join key for all subsequent SPARQL queries (P856, P31, P131, coordinates). An LLM that fabricates QIDs does not produce "slightly wrong" data — it produces data about *a completely different entity*, and every downstream query chains from that wrong ID.

Even if we discarded QID and used only the text fields where the LLM performs well (extracts, country), we would need to verify those facts against a source — which brings us back to needing Wikimedia to be up.

---

## Long-Tail Performance (The Real Question)

The 15 long-tail entities (Paolo Antonio Testore, Fruitlands Museum, Fort du Mont Alban, etc.) are where the pipeline actually needs help:

| Model | Long-tail error rate |
|-------|---------------------|
| gpt-4o-mini | 35.2% (25/71 answered fields wrong) |
| gpt-4o | 27.1% (19/70 answered fields wrong) |

The long tail is where memory is thinnest and fabrication risk is highest — exactly as predicted by D373.

---

## Verdict

### 1. Is it faster than healthy Wikimedia?

**NO.** LLM is 17× slower. When Wikimedia is healthy, there is no speed advantage.

When Wikimedia is *down*, the LLM is faster than a timeout — but this is comparing "fast wrong answer" to "no answer at all." The dead-host breaker already makes the "no answer" path fast (immediate short-circuit), so the comparison is ~0ms (breaker) vs ~2000ms (LLM call that may be wrong).

### 2. Is it accurate enough on the long tail to substitute?

**NO.** 27–35% error rate on the long tail, with no reliable signal for when it's wrong. The model claims high confidence on fabricated data.

### 3. Under what guard, if any, would it be safe?

**No usable guard exists for this use case.** The D373 constraint requires corroboration from a fetched source. The LLM is only needed when that source is unavailable. This is a logical contradiction — you cannot corroborate parametric memory against the source that is down.

The "only answer if certain" system instruction (strict mode) produced negligible change in abstention rate (+2 to +4 fields out of 140), confirming that the model cannot distinguish its knowledge from its fabrications.

---

## What the sample cannot support

- 40 entities is sufficient to reject (error rates are far above any usable threshold), but insufficient to certify. If future models achieve <2% confident-wrong rate, a larger sample would be needed to confirm.
- Wikipedia extract comparison uses word-overlap heuristic. A semantic-similarity metric might credit more partial-credit answers, but would not change the QID/website/instance-of failures.
- Tested only OpenAI models. Anthropic Claude or Google Gemini might behave differently on structured recall, but the fundamental problem (parametric memory lacks verifiable provenance) applies regardless of provider.

---

## Recommendation

The answer to Michael's question is **no**. Close this measurement as complete. The dead-host breaker (LOCAL-445) already provides the correct behavior: when Wikimedia fails, the fact is marked as unavailable and the generation path proceeds without it. Attempting to fill that gap with LLM memory violates D373 and produces fabricated data at unacceptable rates.

If a future model demonstrates reliable abstention (refusing to answer rather than fabricating), the harness built here can be re-run to measure it. The fixture and comparison code are committed for that purpose.
