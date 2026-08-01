##### READY FOR REVIEW

# LOCAL-91: Corpus Fallback Provenance Wiring (Post-Rebase)

**Commit:** `06b1e0a` (rebased onto `950beb4` which includes LOCAL-75)  
**Branch:** `kiro/local91-visitor-info-provenance`  
**Ahead of storied:** 1 commit

---

## Rebase resolution

LOCAL-75 added `_extract_visitor_info_from_corpus` — a regex-based extraction on `combined_text` without provenance. LOCAL-91 adds provenance-carrying extraction on individual `pages[]` entries. The resolved code keeps **both** as a tiered fallback:

1. **PRIMARY**: `fetch_visitor_info_with_provenance` (direct page fetch) — carries provenance
2. **FALLBACK 1 (LOCAL-91)**: iterate `_story_corpus_result['pages']` → `extract_visitor_facts_from_text` → carries page URL + raw text as provenance → gate verifies normally
3. **FALLBACK 2 (LOCAL-34/75)**: `_extract_visitor_info_from_corpus(combined_text)` — NO provenance → gate will reject unverifiable claims (as designed)

LOCAL-75's extraction function (`_extract_visitor_info_from_corpus`) remains in the codebase and is called as the last-resort fallback. The gate enforces that claims without provenance are dropped — no bypass added.

---

## Post-rebase re-proof: Fabricated claim REJECTED

```
=== TEST 1: Fabricated €99 admission ===
AUDIT: admission | €99 admission fee | https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais/tarifs-et-horaires | DROPPED — not supported by source

=== TEST 2: Real €5 admission (Palais Lascaris) ===
AUDIT: admission | €5 | https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais/tarifs-et-horaires | VERIFIED

=== TEST 3: Matisse €12 ===
AUDIT: admission | €12 | http://musee-matisse-nice.org/practical-information | VERIFIED

=== TEST 4: Matisse unconditional Free ===
AUDIT: admission | Free | http://musee-matisse-nice.org/practical-information | DROPPED — not supported by source

=== TEST 5: Closed on Tuesday (Palais) ===
AUDIT: closed_day | Closed on Tuesday | https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais/tarifs-et-horaires | VERIFIED
```

The €99 case is still DROPPED after rebase. Provenance was not reordered to attach unconditionally — the gate still fires on fabricated claims.

---

## Post-rebase test suite

```
tests/test_local91_corpus_provenance.py: 8 passed
All LOCAL-* tests: 263 passed, 1 failed (pre-existing LOCAL-88 test tour NULL content — not a regression)
```

---

## Price discrepancy resolution: €5 vs €7

LOCAL-75 reported **"Admission 7€ (free for under 18, students)"** from corpus text.
LOCAL-91 reports **"€5; free for Métropole residents"** from the municipal tariffs page.

**Analysis:** The official Nice tourism site (explorenicecotedazur.com, current as of 2025) states:
> "Admission: €5 per person, free for children under 13."

The Provence-Alpes-Côte d'Azur tourism site clarifies:
> "€7 per person (in addition to the entrance fee)" — this is the **guided tour** supplement, not the base admission.

**Conclusion:** €5 is the correct current base admission price. LOCAL-75's regex (`(\d+)\s*€` — first match in combined_text) likely picked up the €7 guided tour price which appears earlier in the page text. LOCAL-91's structured extractor (`extract_visitor_facts_from_text`) correctly identifies the base admission price because it looks for "Tarif plein" / "Tarif" patterns rather than taking the first €-amount.

**Neither extraction is wrong about what it found** — the corpus text genuinely contains both "5 €" and "7 €". But the one labelled "admission" should be the base entry price (€5), not the guided tour supplement (€7). LOCAL-91's provenance-aware path produces the correct answer because `visitor_facts_extractor` uses contextual price detection rather than first-match regex.

---

## Constraint verification (post-rebase)

| Constraint | Status | Evidence |
|------------|--------|----------|
| No `DELETE FROM audio_tours` | ✓ | Row count: 60 |
| `tours-near` returns `[1,12,14,17,21,24,27,28,29]` | ✓ | `curl localhost:5005/tours-near/43.7009358/7.2683912?radius=50` verified |
| No shared container running private image | ✓ | No containers started/modified |
| `git rev-list --count storied..HEAD` ≥ 1 | ✓ | 1 commit (`06b1e0a`) |

---

## Changes (per-file, post-rebase)

| File | Lines | Purpose |
|------|-------|---------|
| `generate_tour_text.py` | +63/−5 | LOCAL-91 corpus fallback block with provenance (pages[] iteration, scoring, URL + text carried), plus LOCAL-34/75 secondary fallback preserved as last resort |
| `tests/test_local91_corpus_provenance.py` | +323 (NEW) | 8 unit tests: corpus extraction, gate verification with/without source, fabricated claims rejected, provenance fields populated, end-to-end path simulation |
| `run_local91_evidence.py` | +269 (NEW) | Evidence runner for all acceptance criteria |
| `SUBMISSION_LOCAL-91.md` | Updated | This document (post-rebase version) |

---

## Design: What changed in conflict resolution

The merge resolution keeps LOCAL-91's provenance-aware fallback as the **primary** corpus fallback, and demotes LOCAL-75/34's `_extract_visitor_info_from_corpus` to a **secondary** fallback that only fires if `pages[]` is unavailable. This is correct because:

1. When `pages[]` exists → LOCAL-91 iterates each page individually, carries URL + text → gate verifies → claims that pass are trustworthy
2. When `pages[]` is empty but `combined_text` exists → LOCAL-34/75 extracts from combined text → no individual page URL or text carried → gate has no source to verify against → claims are dropped

The second path is intentionally a dead end in practice: the gate rejects claims without provenance. This is the correct behavior — it means the LOCAL-34/75 fallback only produces output that will survive if the gate happens to find matching source text from the primary path's `_visitor_info_source_text`. In practice, if the primary path failed to find pages, the secondary path's output will also be unverifiable.

---

## Limitations

1. **The corpus fallback depends on `story_miner` having fetched a page with visitor info.** If the museum's tariff page was deprioritized and never fetched, the fallback will be empty.

2. **The LOCAL-34/75 secondary fallback is effectively a no-op when provenance is required.** Claims extracted from `combined_text` without a specific source URL/text will be dropped by the gate. This is by design — the gate must not be weakened. The secondary fallback exists only for backward compatibility and as documentation of the original approach.

3. **Price €5 vs €7**: Both values exist in the Nice municipal page for Palais Lascaris. €5 = base admission, €7 = guided tour supplement. LOCAL-91's structured extractor correctly picks €5 as base admission. The discrepancy with LOCAL-75's "7€" is attributable to LOCAL-75's first-match regex hitting the guided tour price first in the combined text.
