# SUBMISSION LOCAL-906F: wave 53 leftovers (offline, $0)

Branch `LOCAL-906F-wave53-leftovers`, from `subscribed` 9b365b24. No live run and no paid call (`env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`). Every lookup is mocked or absent.

## What changed

| Item | Where | Behaviour |
|---|---|---|
| 1 superlative forms | `leftovers_906c.py` (`_SCOPE_RX`, `_POSS_RX`, `scoped_claim(include_hedged)`, `check_claim`, `prefer_supported`) | "in all of / across all of / in the whole of / anywhere in X", "of all ... in X", "X's largest", `the world's longest`. Hedged "one of the largest/most ... in X" is scope-checked: it needs evidence for the same or a wider area ("in the world" needs world-scope evidence, "one of the largest" with no area does not back it). Hedged evidence never backs an unhedged "the largest". Logs `[LOCAL-906C] Stop N: superlative scope unsupported: "<80>"`. The within-stop dedupe (`drop_within_stop_duplicates`, 906B/891) already calls `prefer_supported`; the 552 pair was kept because the real-name "in all of X" was not a scoped claim at all. |
| 2 person pronoun, no referent | `leftovers_906f.repair_person_pronoun` | his/her/he/she/him with no person named earlier in the stop or earlier in the sentence: one unambiguous cue name from the stop's later sentences, else from the evidence, replaces the first pronoun ("After <Person A>'s death ..."). Otherwise the sentence is dropped. Both logged `[LOCAL-906F]`. A role noun ("the monk", "the abbot") counts as a referent. |
| 3 blocked claim stays blocked | `generate_tour_text.py` (phase 5.16), `key_fact_coverage.py`, `signature_story.py`, `delivery_bodies_905.py`, `leftovers_906f.strip_blocked` | See "Re-insertion path" below. |
| 4 cross-stop consistency | `leftovers_906f.resolve_cross_stop` | Same object = same title tokens, or "the statue"/"this pagoda" resolving to a linked stop. Different year/builder: supported one stays; both supported: one stays + "Sources differ on the date: 1958 or 1963." (builder: "Sources differ on the builder: A or B."); neither: both dropped. A begun-year next to a completed-year is not a conflict. No evidence map handed in: nothing is judged. Log `[LOCAL-906F] cross-stop conflict on '<object>': ...`. |
| 5 promo | `leftovers_906f.drop_promo` | "You can take a half-day/full-day/guided tour ...", "book ...", "tickets cost ...", "tour operators offer ...", "prices start at ...". Kept only when the stop is a ticketed venue (title/Type) AND every figure in the sentence is in the stop's evidence. |
| 6a orphan compound | `leftovers_906f.fix_orphan_compounds` | "a -long cable car" -> "a cable car". |
| 6b no "The <Proper Name>" | `leftovers_906c.definite_name` used by `repair_pronoun_opener` | A bare placeholder, or capitalised words with no common-noun head, get no article. |
| 6c lead / duplicate name | `leftovers_906f.drop_encyclopedia_leads`, `fix_duplicate_names` | "<X> is a mountain located ..." dropped when another sentence says where (and >= 2 sentences stay). "<Mountain> Mount", "Nui Ba Mount", "Mount Mount" lose the repeated head (body prose only, never headers). |

Wiring: `leftovers_906c.final_pass` (every path, via `ensure_bodies`), the head of `ensure_bodies` (so a stop the removals empty is refilled by the 905 floor), and `route_leftovers_906.drop_unsupported_claims` (route path via `finalize_898`). All steps are idempotent and never raise.

## Re-insertion path of the blocked 1887 claim (item 3)

Found by reading the code and bisecting on a fixture (`test_item3_bisect_...`), not from the live log, which is not in this worktree.

1. LOCAL-229 (phase 5.16 in `generate_tour_text.py`) dropped the sentence group from `poi_list[...]['description']` but recorded nothing anywhere.
2. The later 889 key-fact pass (`key_fact_coverage.finalize_tour -> finalize_stop`) rebuilds "dated event / years" facts from the stop's own article evidence and checks `is_denied`. The deny-set only learns from the grounding gate and the deterministic drops, so a 229 block was invisible to it and the evidence sentence went back in. The 880 signature regeneration (`signature_story.regenerate_body_with_story`) never consulted the deny-set at all.
3. Also, `key_fact_coverage._DENY` was a process-wide dict that nothing reset: one job's blocked claims leaked into the next.

Fix: 229 now records every contradicted sentence with the new HARD source `229-contradicted`; `_DENY` is job-scoped (`route_content_896._ScopedDict`); the signature regeneration strips denied sentences; the 905 refill never uses a denied sentence; and `strip_blocked` re-checks every stop at delivery, so any other path is caught too. I could not run phase 5.16 itself offline (needs the corpus and `claim_check`), so the 229 hook is covered by reading plus the deny-set tests, not an end-to-end run.

## Behaviour changes to know about

- A hedged "one of the largest ... in <area>" with no supporting evidence is now dropped. The 906C test that expected "na" for it now expects "bad".
- Not found: the origin of "taking a -long cable car". I did not locate which number cut leaves the hyphen (`cap_unsupported_numbers` does not match "3-km-long"). The cleanup runs at delivery whatever the cause.
- The "<Name> Mount" duplicate: I could not see the original name, so the fix covers a placeholder/native head word repeated by Mount/Lake/River/Pagoda/Island and a repeated capitalised word. Headers are not rewritten.

## Tests

- New: `tests/test_local906f_wave53_leftovers.py` (74 tests, fixtures `tests/fixtures/local906f_552.txt`, `local906f_551.txt`). One group per item, both replays, idempotence.
- Task suite (`test_local906*`, `89[6-9]`, `90*`, `894*`, `87*`, `88[0-9]*`, `89[0-3]*`, `test_lead905*`, `test_local791*`, with `test_local88_tour_pollution.py` deselected): 1802 passed, 4 skipped, 0 failed after the one 906C expectation update.
- `-k "ground or conclusion or pin or itinerary or snap or pool or d533 or derepetition"`: 706 passed; 4 failed, all in the listed pre-existing set (`test_local378...case_sensitive` x2, `test_local666...no_pin_and_no_archive_is_v1`, `test_spine_quality_gate...real_generation`).

## Not done / unproven

Nothing was run live, so the wave-53 cloud result is unproven until the next field test. Item 6b's cause in the wild (the "The <Mountain>" repair) is fixed in the pronoun repair only.
