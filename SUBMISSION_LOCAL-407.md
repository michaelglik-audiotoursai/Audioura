# SUBMISSION_LOCAL-407.md

## Problem

LOCAL-406 fixed the query root cause — snippets now contain facts *about the work*
for the first time. But the prose ignores these facts. The snippets say "15 colour
lithographs", "Japan paper", "numbered 24/50", "Miró's poem" — and the delivered
text says "Miró's collaboration with Broder resulted in a work that had no
precedent." The story material was fetched and then unused.

Additionally, stop 3 (Au Soleil du Plafond by **Juan Gris**) lost its artist name
entirely — a regression from LOCAL-405.

## Root cause

1. **Snippet facts unused**: The LOCAL-402 prompt says "write ONE grounded story
   about a named person" — which is satisfied by "Broder published this book" even
   though the snippets contain far richer material (edition numbers, paper types,
   literary form). The prompt doesn't distinguish *concrete specifics* from *general
   claims* and doesn't instruct the model to prefer the former.

2. **Artist lost**: The snippet injection block (LOCAL-402) has no artist-attribution
   enforcement. The `build_story_beat_prompt_block` has it, but only fires when
   story beats are present. When only snippets are available (no cached elements),
   the artist name competes with collaborator names for space, and the model drops it.

## Fix

### Defect 1: Extract and prioritise candidate specifics

The snippet injection block now:
1. **Extracts candidate specifics** from snippet text using targeted regexes:
   - Edition numbers (`signed and numbered 24/50`)
   - Named materials (`on Japan paper`)
   - Plate/lithograph counts (`15 colour lithographs`)
   - Literary forms (`based on … poem`)
   - Catalogue references (`1967, no. 515`)
2. **Lists them explicitly** in the prompt as "CANDIDATE SPECIFICS"
3. **States a priority rule**: "A concrete detail ALWAYS beats a general claim"
4. **Bans the identity form** explicitly: "'X and Y worked together' is NOT a story"

### Defect 2: Artist attribution in snippet block

The snippet injection block now includes an ARTIST ATTRIBUTION section that:
- Names the artist and surname
- States the surname MUST appear in the text
- Clarifies collaborators are IN ADDITION TO the artist, never instead of

### Both-sides logging

After each stop's description is generated, the code logs:
- How many candidate specifics were **offered** (extracted from snippets)
- Which were **used** (found in the delivered text)
- Which were **ignored**
- Whether the artist surname is present or absent

This is the same discipline that found every other failure this week (D337).

## Files changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | Rewrote LOCAL-402 snippet injection block: extract candidate specifics, priority rule, identity-form ban, artist attribution enforcement, both-sides logging |
| `test_local407_use_the_specifics.py` | 15 unit tests: extraction regexes, prompt structure, both-sides logging wiring, real generation path (D307), revert detection (D296) |
| `run_local407_acceptance.py` | Acceptance runner: MFA 8-stop with specifics verification + Palais control |

## Tests

**15 unit tests** (all pass):
- `TestCandidateSpecificsExtraction` (8 tests): regex coverage for edition, material,
  lithograph count, literary form, catalogue ref, combined corpus, empty, biography
- `TestPromptBlockStructure` (3 tests): CANDIDATE SPECIFICS section, identity form ban,
  artist attribution
- `TestBothSidesLogging` (1 test): logging code presence
- `TestRealGenerationPath` (2 tests, D307): snippet dict → specifics extraction on
  real path; artist enforcement for Gris
- `TestRevertDetection` (1 test, D296): reverting extraction regexes → test fails

**Red-on-revert count: 5** — reverting the extraction logic empties the candidate
specifics list, which breaks:
1. `test_combined_mfa_snippets` (expects ≥3 specifics)
2. `test_snippet_dict_produces_specifics_on_real_path` (expects ≥3 from MFA corpus)
3. `test_specifics_extraction_not_empty_for_rich_snippets` (explicit revert test)
4. `test_prompt_contains_candidate_specifics_section` (string in source)
5. `test_artist_attribution_in_snippet_block` (string in source)

## Acceptance criteria mapping

| Criterion | How verified |
|-----------|-------------|
| Miró, Broder, Mourlot, Fridman in stop 1 | `verify_mfa()` checks each name in stop 1 text |
| Dalí and Freud in stop 2 | `verify_mfa()` checks each name in stop 2 text |
| Gris and Reverdy in stop 3 | `verify_mfa()` checks each name in stop 3 text |
| ≥2 concrete specifics from snippets | `EXPECTED_SPECIFICS` dict checked against delivered text |
| Every stop ≥1 person-action sentence | Regex scan per stop |
| Zero impossible relations | Coherence rejection log count |
| Zero-check clear | Name list vs delivered text |
| `with publisher` = 0 | Substring check |
| 3 stops declared == actual | Stop count from split |
| Palais 4/4, dates intact | Control verification |
| framing=venue_purpose | Keyword check in control |
| Live base score reported | `tour_rubric_scorer` on Palais output |
