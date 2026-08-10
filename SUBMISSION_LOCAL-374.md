# SUBMISSION_LOCAL-374.md

## Summary

Rewrote the 3 mirror tests in `TestParagraphRegexPictureExclusion` plus
`test_no_concatenated_title_on_listing_page` to drive the real `_fetch_page`
through mocked `requests.get`, eliminating all inlined regex from the test file.
Deleted the permanently-green `test_picture_false_match_was_the_old_bug` and
replaced it with a test that asserts the *current* code does not produce the
concatenation. Also replaced the local `_extract_text_from_html` mirror in
`TestFixtureAndLiveAlignment` with calls to the real `_fetch_page`.

## What changed

- `tests/test_local373_live_extraction_gap.py` — full rewrite of mirror tests

## What did NOT change

- `exhibition_checklist.py` — zero production changes
- No `inspect.getsource`, no `import re`, no inlined regex anywhere in the test file

## Revert check

```
$ git checkout storied~2 -- exhibition_checklist.py
$ python3 -m pytest tests/test_local373_live_extraction_gap.py --tb=no -q

15 failed, 2 passed

FAILED ::TestParagraphRegexPictureExclusion::test_picture_tag_not_matched_as_paragraph
FAILED ::TestParagraphRegexPictureExclusion::test_picture_does_not_produce_concatenation
FAILED ::TestParagraphRegexPictureExclusion::test_pre_tag_not_matched
FAILED ::TestParagraphRegexPictureExclusion::test_path_svg_tag_not_matched
FAILED ::TestFetchPageDeduplication::test_duplicate_paragraphs_removed
FAILED ::TestFetchPageDeduplication::test_duplicate_list_items_removed
FAILED ::TestFetchPageDeduplication::test_duplicate_img_alts_removed
FAILED ::TestFooterBoundaryDetection::test_stops_at_street_address
FAILED ::TestFooterBoundaryDetection::test_stops_at_copyright
FAILED ::TestFooterBoundaryDetection::test_boundary_only_after_500_chars
FAILED ::TestFooterBoundaryDetection::test_all_rights_reserved_boundary
FAILED ::TestFixtureAndLiveAlignment::test_fixture_no_footer_nav_in_window
FAILED ::TestFixtureAndLiveAlignment::test_fixture_no_duplicate_credit_lines
FAILED ::TestFixtureAndLiveAlignment::test_fixture_window_under_5000_chars
FAILED ::TestFixtureAndLiveAlignment::test_no_concatenated_title_on_listing_page
```

```
$ git checkout storied -- exhibition_checklist.py
$ python3 -m pytest tests/test_local373_live_extraction_gap.py --tb=no -q

17 passed
```

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Revert turns ≥12 of 17 tests red | ✅ 15 red (was 8/16) |
| No `inspect.getsource` | ✅ |
| No inlined copy of production regex | ✅ (no `import re` in test file) |
| No production-code change | ✅ |

## The 2 tests that remain green on revert

1. `test_no_false_positive_on_early_address` — negative test asserting that an
   address in the *first* 500 chars does NOT trigger the footer boundary. This
   is correct behavior on both old and new code (the boundary guard is
   char-count-based, present in both versions).

2. `test_fixture_all_three_works_in_window` — asserts all three artwork names
   exist in the first 5000 chars of the fixture. This passes on old code because
   the works happen to appear early enough even without dedup/footer-removal.
   The test's value is confirming content presence, not detecting the regex bug.
