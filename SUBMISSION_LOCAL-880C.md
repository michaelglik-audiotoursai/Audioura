# SUBMISSION — LOCAL-880C

**Branch:** `LOCAL-880C-number-removal-grammar`
**Base:** subscribed (`a11e20a9`) — `git merge-base --is-ancestor a11e20a9 HEAD` exits 0.

Two defects left by LOCAL-880B:

1. Removing an unsourced number left a broken sentence — `submission_artifacts/local880b/saigon_tour.txt`, Stop 1: *"Its two bell towers rise meters high…"* (the `58` was dropped, the unit stranded).
2. `signature_story._GENERIC_VENUE` hard-coded a proof tour's city/country/demonym — `vietnamese, vietnam, saigon, chi, minh` (D769).

---

## 1. An unsourced number never leaves a broken sentence; matching is tolerant

`spoken_text_hygiene.audit_seating_capacity` (the LOCAL-880 §9 scrub):

- **No orphan unit.** When the rule drops a measured magnitude it now removes the whole measurement phrase (number **and** unit), not just the number:
  - `"rise 58 meters high"` → `"rise high"` (the comparative survives, the number+unit go);
  - `"a 500-seat venue"` → `"a venue"`;
  - a dangling measurement verb left with nothing descriptive (`"The tower stands 95 metres."`) has the verb clause dropped too — never a bare `meters`/`seats`/`km`/`feet`/`tons`/`storeys`.
  - the verbal seating form (`"seated 500 guests"`) keeps its verb (`"seated guests"`) instead of collapsing to `"venue"`.
  A `\x00MAG\x00` sentinel marks the removed phrase so the post-pass can mop up a dangling verb.

- **Matching is unit- and spelling-tolerant.** `_nums_in` now accepts a space, a hyphen, or no separator between the number and its unit, and the unit list already carries both spellings. So evidence `"reaching to a height of 58 metres"`, `"the 58-metre bell towers"`, or `"58 m tall"` all KEEP a body that says `"58 meters high"`. (Previously `"58-metre"` was not recognised.)

### Why the Saigon cathedral's 58 m was judged unsourced

It was **not** a spelling/matching failure at the leaf — it was that the evidence handed to §9 was incomplete. §9 read only the thin-facts map; the `58 metres` the narrator used came from the **injected reference-material snippets** (`_DIRECT_SNIPPETS_PER_STOP`), which were not in that map. Fix in `generate_tour_text.py`: fold each stop's snippet title+text into the per-stop evidence the §9 and former-use scrubs read. A figure the narrator legitimately took from a published snippet is now recognised as sourced — in any city, no hard-coding. Proven offline end-to-end: with the snippet folded in (spelling `metres` vs body `meters`), §9 reports `kept='58'`.

### Two upstream de-dup passes that dropped the sourced sentence

The 58 m sentence could also be deleted *before* §9 by a de-duplication pass that preferred the vaguer telling:

- **LOCAL-286 prolog↔body dedup** (`generate_tour_text.py`): a body sentence that overlaps the prolog preview is no longer dropped when it carries a concrete magnitude figure — the body is where the sourced detail belongs; the preview may restate it. (§9 still removes the figure later if it is genuinely unsourced, now without an orphan unit.)
- **D533 within-stop fact repeat** (`derepetition_guard.strip_repeated_facts`): when the later telling carries a sourced magnitude and the earlier, kept telling does not, the two are swapped so the number-bearing sentence is kept.

Both use a small local `_carries_magnitude_number` helper (kept in `derepetition_guard` to avoid an import cycle).

## 2. No hard-coded place words in `signature_story._GENERIC_VENUE`

- Removed `vietnamese, vietnam, saigon, chi, minh` (and the demonym `french`) from the static set. The static set now names no city, country or demonym (D769).
- Added `derive_generic_tokens(location, title)`: the place words that are generic **for this tour** — the folded tokens of the tour's location and the stop title, plus a demonym of each location token from a small general gazetteer (`vietnam→vietnamese`, `france→french`, …). A Paris tour yields `{paris, france, french, parisian, …}`; a Saigon tour `{saigon, vietnam, vietnamese, chi, minh, …}`.
- `story_key_tokens` and `body_tells_story` take an optional `generic_extra` set; the two internal callers (`regenerate_body_with_story`, `ensure_signature_in_tour`) derive it per stop and pass it. A Paris tour treats `french` as generic; a Saigon tour `vietnam` — and a genuinely distinctive token (Hugo, Hunchback, 1944, Allied bombing) still counts.

---

## Tests (offline, deterministic)

`tests/test_local880c_number_grammar_and_generic.py` — 11 tests, all pass:
- orphan-unit removal for height / seat-count / dangling-verb / verbal-seated forms;
- sourced height KEPT across `metres`/`meters`, `58-metre`, `58 m`;
- `_GENERIC_VENUE` names no proof-tour place; Paris↔`french`, Saigon↔`saigon/vietnam/vietnamese` derivation; distinctive tokens survive; a derived place word does not count as telling a story;
- the `_carries_magnitude_number` detector and the within-stop prefer-sourced swap.

No regressions in the suites that exercise the touched modules:
`test_local880_defect_scrubs` (20), `test_local880_signature_story` (7),
`test_local831_derepetition_stop_loss`, `test_local654_no_midclause_collision`,
`test_local623_stop_body_defects`, `test_local618_grammar_splice_lint`,
`test_d523_story_selection_and_hygiene` — all green.

## Live (own container, D753)

`run_local880c_live.py` + `docker-compose.local880c-proof.yml` (project `local880c`, own postgres on :55982; the shared audioura-* containers, the shared dev DB and the live DB are never touched). ONE 3-stop run of *"Notre-Dame Cathedral Basilica of Saigon, Saigon Central Post Office, Saigon Opera House, Ho Chi Minh City"*. Delivered text in `submission_artifacts/local880c/saigon_3stop_tour.txt`.

**Result (honest):**
- **PASS — no orphan unit** anywhere in the delivered narration (confirmed by scanning the artifact: the §1 grammar fix works end-to-end; a dropped `58` left `"its two bell towers reach high"`, not `"reach meters high"`).
- The 3 stops were delivered; no empty bodies.
- The **58 m-stated-as-sourced** criterion was **not** green in that run: the figure was dropped upstream (the LOCAL-286 prolog↔body dedup deleted the body sentence, and the §9 evidence map lacked the snippet). The three fixes that close this chain — snippet-evidence fold, LOCAL-286 magnitude guard, D533 prefer-sourced swap — were added **after** that run and are verified by the offline tests and a deterministic end-to-end simulation (§9 now reports `kept='58'` when the cathedral snippet is in evidence), but could **not** be re-validated with a fresh live run: the task's hard budget was already reached.

**Budget:** `TASK_BUDGET_ID=LOCAL-880C TASK_BUDGET_USD=0.12`. Metered spend reached **$0.1253** (an exploratory diagnostic run plus the proof run; the second run self-stopped at the cap on stop 3, LOCAL-827). The cap is a hard whole-task limit representing real spend, so no further paid run was made — the post-run fixes are proven offline rather than by re-burning budget. Run logs (`_local880c_meterlogs/`) are git-ignored and never committed.

## Files

- `spoken_text_hygiene.py` — §9 orphan-unit repair + separator/spelling-tolerant matching.
- `signature_story.py` — `_GENERIC_VENUE` de-hard-coded; `derive_generic_tokens`; `generic_extra` threaded through.
- `generate_tour_text.py` — fold per-stop snippets into §9/former-use evidence; LOCAL-286 magnitude guard.
- `derepetition_guard.py` — `_carries_magnitude_number`; within-stop prefer-sourced swap.
- `tests/test_local880c_number_grammar_and_generic.py` — new offline suite.
- `run_local880c_live.py`, `docker-compose.local880c-proof.yml` — the D753 proof harness.
- `.gitignore` — ignore `_local880c_meterlogs/`.
- `submission_artifacts/local880c/saigon_3stop_tour.txt` — delivered live text.
