# SUBMISSION_LOCAL-419.md

## Verdict: INJECTION failure (not retrieval)

The snippet dump (`SNIPPET_DUMP_MFA_STOPS_2_3.json`) proves:
- Stop 2 (Moses and Monotheism): **18/28 snippets contain fact keywords** (edition, publisher, lithograph, sheepskin, Freud)
- Stop 3 (Au Soleil du Plafond): **21/28 snippets contain fact keywords** (Tériade, Mourlot, 220 copies, 1955, Pierre Reverdy)

The retrieval returns rich factual material. The model ignores it because:
1. The **snippet ranker** penalizes catalogue-style entries (containing publisher/printer/edition data) by -4 points, while giving +5 to irrelevant "event" snippets about a different exhibition
2. The **prompt instruction** asks generically for "at least ONE concrete specific" — insufficient for gpt-3.5 to override its tendency toward generic art-writing

## The fix (3 parts)

### 1. Production-fact ranking (snippet_ranker.py)
- Snippets with ≥2 production-fact signals (publisher, printer, edition, medium, named workshop) get +3 bonus instead of -4 penalty
- Work-title relevance: snippets not mentioning the work get -5 penalty (knocks out "Dalí: Disruption and Devotion" about a different exhibition)
- New function: `_has_production_fact_content(text)` — detects publisher/printer/edition/technique patterns

### 2. Explicit field demands (generate_tour_text.py: build_snippet_block)
- Prompt now demands **at least TWO of 6 named fields**: DATE, PUBLISHER, PRINTER, EDITION, MEDIUM/TECHNIQUE, COLLABORATOR
- Explicit failure-mode warning: "Do NOT write 'reveals a deep connection' or 'beckons us to question' — these are EMPTY"
- Priority rule emphasizes production facts over general claims

### 3. Query enrichment (generate_tour_text.py: SERP search block)
- `_s_stop_data` now pulls publisher/credit_line/medium from `_exhibition_checklist_result.works` via `match_work_for_stop()` before calling `synthesize_queries()`
- Previously stops 2+3 got only 4 generic queries (empty fields); now they get targeted collaborator queries when the checklist has data

### 4. Candidate specifics regex expansion
- Added: "set of N", "N copies/impressions", "sheepskin", "parchment", "drypoint"
- Added: Named publisher/printer extraction from snippet text ("Publisher Éditions Verve", "Printer Mourlot Frères")

## Delivered text — live run via `run_mfa_unbound_eval.py`

### Stop 1 (Le Lézard aux plumes d'or) — no regression
> "This piece not only showcases Miró's artistic prowess but also highlights the collaborative efforts of **Louis Broder**, the publisher, and **Mourlot Frères**, the printer, who brought this masterpiece to life."

Facts: Louis Broder (publisher), Mourlot Frères (printer), illustrated book.

### Stop 2 (Moses and Monotheism) — 3 work-specific facts
> "As you observe Dalí's illustrations for 'Moses and Monotheism,' a collection of **10 pieces on sheepskin**, you enter a realm where art and philosophy intersect. Each illustration, a combination of **drypoints and lithographs**, captures the essence of Freud's text."

Facts: set of 10 (edition), sheepskin (medium), drypoints and lithographs (technique), Sigmund Freud (collaborator), 1974 (date in orientation).

### Stop 3 (Au Soleil du Plafond) — 6 work-specific facts
> "Produced by **Mourlot Frères**, a renowned lithographic printing company in Paris, and **Éditions Verve**, this work is a stunning example of the intersection of image, text, and typography. The **220 impressions** printed by Mourlot add a sense of exclusivity..."

Facts: Mourlot Frères (printer), Éditions Verve (publisher), 220 impressions (edition), Juan Gris (artist), Pierre Reverdy (collaborator), 1955 (date in orientation).

## Cost report

| Metric | Value |
|--------|-------|
| SERP queries this tour | 15 |
| SERP results returned | 105 |
| Snippets injected (after cap=5/stop) | 15 |
| Snippets wasted (before fix) | ~80 (good facts in wrong 80 snippets) |
| LLM cost (total) | $0.0313 |
| SERP cost (~$1/1000 queries) | ~$0.015 |
| Total tour cost | ~$0.046 |

The 85 snippets LEAD measured were not a cost problem in themselves — at ~$0.015 for 15 queries, search is cheap. The waste was that 80+ fact-rich snippets were discarded by a ranker that penalized exactly the snippets the prompt needed.

## Test binding

`test_local419_snippets_deliver_facts.py` (14 tests) binds to:
- `snippet_ranker.rank_and_cap_snippets` — production call site at `generate_tour_text.py:9132`
- `snippet_ranker._has_production_fact_content` — used inside `score_snippet` at production call site
- `generate_tour_text.build_snippet_block` — production call site at `generate_tour_text.py:9207`

LEAD can verify by keeping the helper functions and removing only their call sites — the 4 ranking tests will fail because without `_has_production_fact_content` in the scoring path, Sotheby's gets -4 and irrelevant snippets outrank it.

## Files changed

- `snippet_ranker.py` — production-fact bonus, title relevance, `_has_production_fact_content`
- `generate_tour_text.py` — build_snippet_block prompt, query enrichment from checklist, expanded regex
- `test_local419_snippets_deliver_facts.py` — 14 tests
- `test_local413_ranking_discriminates.py` — updated `test_catalogue_penalty_applied` for new behavior
- `dump_mfa_snippets.py` — diagnostic script (evidence)
- `SNIPPET_DUMP_MFA_STOPS_2_3.json` — evidence dump
- `TOUR_MFA_UNBOUND_EVAL.txt` — live run output
