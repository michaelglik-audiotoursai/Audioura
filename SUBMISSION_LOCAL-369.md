# SUBMISSION_LOCAL-369.md

## Thread A — Exhibition prose feeds thread discovery

**Thread name discovered:** The exhibition's own framing text (e.g., "livres
d'artiste … unbound, both literally and in the creative minds that produced
them") feeds into `extract_story_elements_from_pages` → `discover_theme_threads`
for scoped exhibition requests.

**Source sentence from fixture:** `"Bold, experimental, extravagant, and unbound,
both literally and in the creative minds that produced them, livres d'artiste had
no precedent. At the turn of the 20th century, they revolutionized the book as
an art form."` (MFA fixture, line 1301 of
`tests/fixtures/mfa_picasso_exhibition.html`)

**Mechanism:** `ExhibitionChecklistResult.page_text` now stores the fetched
exhibition page text. When `_exhibition_scope is not None` and the result has
page_text, `generate_tour_text.py` wraps it as a synthetic page and feeds it
through the existing `extract_story_elements_from_pages` pipeline, merging any
new elements into `_story_elements` before thread discovery runs.

## Thread B — Credit line as structured field

**Field:** `credit_line` on each work dict returned by `prose_llm_extract_works`.
Already extracted (LOCAL-368); now propagated into the per-stop description
prompt.

**Gift statement reaching prose:** The per-stop description prompt receives:
```
PROVENANCE (museum-published credit line — you may state this fact):
  Gift of Boris Fridman
PROHIBITION: Do NOT infer or assert the donor's motive, wealth, financial condition,
or any biographical predicate not contained in retrieved text.
```

## Negative control — no unsourced biographical predicate

**Constructed case:** A work with `credit_line: "Gift of Boris Fridman"` is
matched to its stop. The prohibition in the prompt explicitly bans:
- Inferring motive ("donated because…")
- Inferring financial condition ("could no longer afford…", "left him poorer")
- Asserting wealth ("a wealthy collector")
- Asserting business ("his company")

**Test class:** `TestNoUnsourcedBiographicalPredicate` with:
- `test_prompt_prohibition_present`: Verifies the prohibition text exists in
  generate_tour_text.py source
- `test_forbidden_patterns_catch_fabricated_claims`: 6 fabricated sentences all
  caught by the regex patterns

## Red/Green evidence

**RED (production changes reverted via `git stash`):**
```
FAILED test_page_text_field_exists — AttributeError: page_text not on result
FAILED test_find_exhibition_checklist_stores_page_text — page_text empty
FAILED test_prompt_prohibition_present — 'Do NOT infer or assert' not in source
FAILED test_no_page_text_on_unscoped_result — AttributeError
```

**GREEN (production changes restored via `git stash pop`):**
```
12 passed, 0 failed
```

## Existing tests unchanged

- `tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds` — 2 passed
  (museum 8-stop ≥75.0, Palais ≥70.0)
- `tests/test_local357_forced_stops.py::TestMuseumBoundsProperty` — 2 passed
  (museum 8-stop ≥75.0, museum 4-stop ≥81.2)
- `tests/test_local368_prose_extraction.py` — 33 passed (no regression)

## Limitations

1. **Thread discovery depends on story_element_extractor quality.** If the LLM
   extraction from exhibition prose yields no scored elements (thin text,
   extraction failure), thread discovery degrades to mosaic mode — the existing
   behaviour, not a regression.

2. **Credit line injection requires title matching.** Uses the same
   `_normalize(poi_name)[:10]` prefix match as C5-1. If the exhibition checklist
   work title diverges significantly from the stop name as produced by the
   deterministic fill, the credit line won't match. This is conservative (fails
   closed: no provenance rather than wrong provenance).

3. **No selection layer built.** The credit line fact is tagged implicitly by its
   presence in the provenance injection block. The existing `class_social`
   classifier in `swipe_preference_service.py` can see it, but explicit tagging
   for personalization is out of scope per the spec.
