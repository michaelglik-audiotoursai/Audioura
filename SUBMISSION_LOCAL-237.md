##### READY FOR REVIEW

# SUBMISSION_LOCAL-237: Subject Validate Expand Routine

**Branch:** `kiro/local237-subject-validate-expand`
**Task:** Implement Michael's gather → validate → expand → remove routine
**Date:** 2026-08-05

---

## Files Created

| File | Purpose |
|------|---------|
| `subject_validate_expand.py` | Core routine: 4-stage pipeline (gather, validate, expand, remove) |
| `run_subject_routine_riviera.py` | Runner for Michael's 5 reviewed paragraphs |
| `run_subject_routine_corpus.py` | Corpus-wide runner with cost accounting |

No files modified. No containers rebuilt. No edits to `claim_check.py`,
`external_claim_verify.py`, `style_validator_detector.py`, `DECISIONS.md`,
`CLAUDE.md`, or `.continuous_dev/*`.

---

## Design

Behind `DISABLE_SUBJECT_ROUTINE=1`.

### Stage 1: GATHER (deterministic, $0.00)

Pattern-matches sentences that make a promise without delivering:
- "each crack and crevice holding a story" → UNNAMED_STORY
- "a harmonious symphony of past and present" → METAPHORICAL_LINK  
- "a testament to the enduring allure" → VAGUE_LEGACY
- "inviting you to ponder the enduring legacy" → INVITATION_TO_DISCOVER
- "steeped in history" → ABSTRACT_HISTORY

Skips sentences that ARE delivering (contain dates, proper-noun predicates,
quoted titles, measurements).

### Stage 2: VALIDATE (reuses `external_claim_verify` search path)

Search order:
1. `stop_corpus` — passages for this specific stop
2. `venue_corpus` — broader venue material  
3. External via `_serp_search()` + `_fetch_page_text()` (same as D106)

### Stage 3: EXPAND

Two methods:
1. **Deterministic** — extract a factual sentence from source that delivers
   the promise (must contain date/number/predicate). Zero cost.
2. **LLM-bounded** — gpt-4o-mini rewrite, strictly bounded to source text only.
   Novel-token guard rejects expansions that introduce >30% unsourced content.
   Source-relevance gate prevents replacing history promises with transport info.

Every expansion carries: quoted source sentence, URL, trust tier, method.

### Stage 4: REMOVE

Delete only the promise sentence. Does not touch surrounding material (LOCAL-192 lesson).

### Guards

- No expansion on stops failing LOCAL-236 existence check (D127).
- Source-relevance gate: source domain must match promise domain.
- Novel-token guard: LLM expansion rejected if >30% tokens not in source.

---

## Riviera 5-Paragraph Results

```
Paragraph 1 (Orientation): 0 promises (navigation — correctly skipped)
Paragraph 2 (Prolog):      1 promise  → 1 EXPANDED (Picasso Museum, 1966, deterministic from external, tier 3)
Paragraph 3 (Description): 1 promise  → 1 EXPANDED (Monet series painting, deterministic from stop_corpus, tier 1)
Paragraph 4 (Orientation): 0 promises (correctly skipped)
Paragraph 5 (Description): 7 promises → 1 EXPANDED, 6 DELETED
```

### Paragraph 5 detail (Michael's primary complaint paragraph)

| # | Promise sentence | Subject | Outcome | Reason |
|---|---|---|---|---|
| 1 | "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story." | stone walls | DELETED | Source found but no factual expansion deliverable |
| 2 | "The gentle rustle of the Mediterranean breeze mingles with the distant chime of church bells, creating a harmonious symphony of past and present." | Mediterranean | DELETED | Source found but irrelevant to the promise |
| 3 | "As you pause to admire the intricate ironwork adorning centuries-old doors, the connection between past and present becomes tangible…" | (unresolved) | DELETED | No external source found |
| 4 | "This stop on the French Riviera cycling tour offers a profound glimpse into the enduring spirit of a village steeped in history." | French Riviera | EXPANDED | Replaced with Eze location fact from corpus (tier 1) |
| 5 | "The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life…" | Eze Village | DELETED | Source irrelevant to heritage promise |
| 6 | "The hillsides hold a multitude of tales from a bygone era." | hillsides | DELETED | Source found but no factual expansion deliverable |
| 7 | "As you cycle onward, remember Eze Village, a testament to the enduring allure…" | Eze Village | DELETED | Source irrelevant to heritage promise |

---

## Villa Eilenroc Comparison

Michael supplied 6 facts for his rewrite. This routine's external search found:

| Fact | Found | Source |
|------|-------|--------|
| Charles Garnier (architect) | ✓ | External search: antibes tourism site |
| 1867 (year built) | ✓ | External search: ville-antibes.fr |
| Hugh-Hope Loudon (commissioner) | ✓ | External search: travel blog |
| Eilenroc = Cornelie reversed (name origin) | ✗ | Search returned passage mentioning Cornelie but token matching too strict |
| Beaumonts in 1927 (later owners) | ✗ | Not in top search results |
| Fitzgerald (literary connection) | ✓ | stop_corpus (tier 1) |

**Findable: 4/6 (67%)**

Note: "Cornelie" IS in the search results (the 1867 passage says "its name is
an anagram of his wife's name - Cornelie") but the combined subject "Eilenroc
Cornelie" requires both tokens to appear together. A single-word search for
"Cornelie" would have found it. This is a retrieval precision gap, not a web
availability gap.

---

## Corpus-Wide Metrics

### GATHER (deterministic, $0.00)
- Tours processed: 84 (those with `tour_content`)
- Paragraphs: 862
- **Promises detected: 110**
- Promises per paragraph: 0.13
- Promises per tour: 1.3

### FULL PIPELINE (Nice list, 7 tours)
- Promises: 11
- **Expanded: 2 (18%)**
- **Deleted: 9 (82%)**
- Total cost: $0.0100
- Cost per paragraph: $0.0000
- Cost per tour: $0.0014

### Cost accounting
- Riviera 5-paragraph run: $0.0070
- Corpus-wide (7 Nice tours): $0.0100
- **Total spend: $0.0170** (ceiling: $0.45)
- Cost per paragraph: ~$0.0014 (1 Serper query per promise)
- Cost per tour: ~$0.0084 (estimated 6 paragraphs)

---

## The Honest Finding

**Expansion rate is 18%.** The routine mostly deletes.

This is the D123 problem expressed as a number: 25 of 29 tours have no venue
corpus, and the thin corpus that exists (1–7 passages) rarely contains material
that can replace a broken promise with delivered content.

The routine is correct — it refuses to expand from parametric memory (D127:
Chikanobu), and when no source exists, deletion is the only safe action. But
Michael's instruction was "either tell us the story or get rid of the sentence,"
and with current corpus coverage, "get rid of the sentence" is the branch that
fires 82% of the time.

**What would change this:** venue corpus depth. The Villa Eilenroc comparison
shows that 4/6 facts ARE on the public web — the gap is retrieval, not
availability. Richer stop_corpus (fetched at generation time, not after) would
flip the ratio.

---

## Verification

```
audio_tours count: 138 (unchanged)
Nice list: [1, 12, 14, 17, 24, 29, 152]
No container rebuilt
git status --short: 3 new files only
DISABLE_SUBJECT_ROUTINE=1 disables all stages
Every expansion carries quoted source + tier
No expansion on stops failing existence check
```

---

## Limitations

1. **Subject extraction for unresolved subjects.** When a sentence has no proper
   noun (e.g., "the connection between past and present"), the subject defaults
   to "(unresolved)" and external search is unfocused.

2. **Token-overlap matching threshold (0.6)** means multi-word subjects where one
   word doesn't appear in the passage will miss. The "Eilenroc Cornelie" case.

3. **Deterministic expansion quality.** When the corpus passage IS factual but
   about a different aspect (e.g., Eze's geographic location vs. Eze's history),
   the expansion delivers a fact but not the RIGHT fact for the promise's domain.

4. **LLM expansion is conservative.** The novel-token guard and source-relevance
   gate reject many potential expansions. This is the safe direction (D127) but
   means the 18% rate understates what an unconstrained LLM could produce — at
   the cost of fabrication risk.

5. **No cross-sentence context.** Each promise is validated independently. A
   sentence promising "stories" about Eze might be fulfilled by the PRECEDING
   sentence about 200 BC settlers, but this routine doesn't check inter-sentence
   delivery within the same paragraph.
