# LOCAL-874 — Place-kind taxonomy (D767)

Branch `LOCAL-874-place-kinds`, from subscribed 768f8c55 (merge-base check passes).

## Done
- `place_kinds.py` (single source of truth): `classify(name, type_label, places_category, wikidata_instance_of, language)` -> `{group, subtype, confidence}`.
  Groups: religious, royal, performance, maritime, civic, peaks, depression, water (Michael's typology), plus `other_documented` (park/museum/library/post office…, so nothing the old `_DOCUMENTED_KINDS` covered regresses), `street_area`, `business`, `both`, `landmark_unknown`.
  Words in en / vi (with and without diacritics) / fr / es / it / de / ru. Order: Wikidata P31 (labels or a few certain QIDs) -> Places category -> name -> type label. A business word in the name wins ("Palace Bar"). Unknown -> `landmark_unknown`, never business.
  Matching: Vietnamese/Romance words are noun-first (head of the name only, so "Hồ Chí Minh City…" or "Phu Quoc" don't trip lake/temple); English last-word-wins before " of "; German suffix; Russian stem.
- `user_stop_enrichment.classify_stop_kind` is now a thin wrapper returning `business | landmark | street_area | both`. The business enrichment path runs for `business` and `both`; `landmark`/`street_area` keep the existing story path (log line `[LOCAL-874] <title>: kind=… group=… subtype=…`; the report carries group, subtype, research angles).
- LOCAL-872 claim gate (generate_tour_text): only `business` is skipped; unknown, street_area and both go through the gate. Narration and verifier "documented" tests treat `landmark`/`both` as documented.
- Business list kept exactly (`BUSINESS_WORDS` = old `_BUSINESS_KINDS` minus street/walking/nightlife/market/gallery/venue/music/live) plus Vietnamese equivalents. Parametrised test proves EVERY word in a realistic name classifies business and takes the business path; a test also asserts the list equals the covered set.
- street/walking/nightlife -> `street_area`; market/gallery -> `both` when famous (landmark table or a short famous-market list incl. Ben Thanh), else business; venue/music/live ignored.
- Research angles per group (`ANGLES`, `research_angles`, `query_hints`), per Michael's table; `street_area` angles include name origin, history, known-for, 2–4 places ALONG it, best time.
- Tests: `tests/test_local874_place_kinds.py` (132 + parametrised business words, all passing). Two old assertions that encoded "street = business" were updated (862, 870 tests). Existing 862/870/872 suites pass; failures in the wider `local8*` run (postgres-2 host, meter wiring, lease, resume…) are DB/infra and unrelated.

## Offline classification of Michael's 10 stops (saved LOCAL-867 preview)
Cathedral religious/church · Post Office other_documented/historic · Book Street street_area · Independence Palace royal/palace · War Remnants other_documented/museum · Opera House performance/opera_house · City Hall other_documented/historic · Café Apartments business/cafe · Bạch Đằng Pier **maritime/pier** (landmark path) · Thi Bar business/bar. Crazy street / Book Street street_area, An Spa / Thi Bar business, Ben Thanh Market both (unit tests).

## NOT done / caveats
- **The metered live run ($0.40) was NOT executed**: no live PASS evidence for "no stop thinner than the 872C run" or the Bạch Đằng landmark log line from a real run; only unit tests and the offline classification above. 
- The dedicated street_area pipeline (Wikipedia en+vi source gathering, LOCAL-873 escalation, midpoint pin, "walk/ride along" directions) is NOT built: street_area currently keeps the existing story path, with the angles available via `place_kinds.research_angles`. The angles are not yet injected into the search queries/writer prompt of the landmark path in generate_tour_text.
- `both`: the business details are gathered; the landmark story merge is not separately implemented.
- Pin-snap uses no kind lists (landmark_reference only), so nothing to wire there.
