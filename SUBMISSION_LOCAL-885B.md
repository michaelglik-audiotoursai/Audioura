# LOCAL-885B — three LOCAL-882 cache tests after 884+885

Budget: $0 (offline only, no paid calls). Base f616e29f (ancestor check exit 0), branch LOCAL-885B-cache-tests.

## Verdicts (all three: STALE FIXTURE, code is right)
The fixtures were written before LOCAL-884 §3 and LOCAL-885 and are no longer valid current-version rows:
- `test_current_version_valid_row_is_a_hit`: row had no `full_text` (LOCAL-885: a same-version row without the key is re-fetched, by design) and no `coord` (884 §3: coord-less payload must share a strict distinctive token AND name the city; "City Hall" has no distinctive token). Added `full_text` + `coord`.
- `test_revalidate_payload_direct`: first case "Saigon Opera House" was coord-less with match_name "Opera House" (no distinctive token) -> rejected by 884 §3. Added `coord`. Other cases unchanged and pass.
- `test_put_then_get_roundtrip_stamps_current_version`: the art put had no `full_text`/`coord`; `fetch_article` stores both today (full_text via fetch_full_text, coord via `_pick`). Fixture now mirrors that. put->get of a row shaped like what current code writes IS a hit; I checked the put/get code paths (version stamped, TTL, SELECT/INSERT) and found no bug.
- Added `test_same_version_row_without_full_text_is_a_miss` documenting the 885 contract.

Not a bug but worth LEAD's attention: if the full-text fetch fails, the row is stored without `full_text` and is never a hit (re-fetched every run). Intended per 885 comments; costs repeat fetches.

## One real code bug found (outside the 3 tests)
`test_local875_local_language.py::test_local_wikipedia_evidence_offline_injected` also failed, introduced by LOCAL-884 §3 (fails at HEAD~2 too). The strict distinctive-token check in `_pick` rejected every coordinate-less TRUSTED (interlanguage-link) page, since a local-script title can never share a Latin token with the English stop name. Fix in `landmark_wikipedia_evidence._pick`: skip the 884 §3 strict-token test when `raw["trusted"]`. Non-trusted behaviour (Book Street / Notre-Dame leaks) unchanged.

## Results
Ran tests/test_local86x–88x + conclusion/actionable/title suites: 974 passed, 7 failed, 16 errors. The 16 errors are the pre-existing billing/entitlement ones. The 7 failures (test_local876 map_delivery x3, test_local88_tour_pollution x4) are DB-dependent, fail identically on the untouched base (876 passes when run alone, order-dependent), unrelated to cache/evidence. All test_local882/884/885 pass.
