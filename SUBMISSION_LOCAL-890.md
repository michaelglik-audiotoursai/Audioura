# SUBMISSION LOCAL-890 — coverage pass takes key facts only from the stop's OWN article

**Status: the three injection defects are fixed and proven live. Two items are NOT proven: Opera 1944 (found live, fixed offline after the run, not re-run) and the Cathedral (no English own article in this run, so nothing to inject).** Branch `LOCAL-890-coverage-own-article`, base `219648b1`.

## What changed (`key_fact_coverage.py`, generic, no venue named)
1. **Own article only.** `own_article()` picks the article whose TITLE or lead SUBJECT/kind noun carries a distinctive token of the stop's name, and which passes `title_covers_name`. No such article (a street, a bar, a café, a snippet-only or city-article-only bundle) means no key facts, K = 0, nothing injected. The old fallback ("first article, else the whole blob") is gone. Key facts, the floor top-up and the event candidate all read `own_prose_sentences()`.
2. **The event must be about the stop** (`about_stop`): it names the stop / its article title / "the building, theatre, cathedral…", or has a pronoun subject ("It was…"). "…renamed **it** Kennedy Square" (stop only as pronoun object) is refused.
3. **Splice.**
   - Injection only goes through `_replace_block_body`, so it never touches `Coordinates`/`Type`/`Specific Examples`/`Orientation`/`Directions`.
   - `repair_header_splices()` moves a body sentence that is glued onto a header line to its own paragraph (the City Hall defect).
   - `strip_title_prefix()` cuts "Book Street On …". A sentence with a glued stop name that is not about the stop is dropped and put in the deny-set.
4. **Placement.**
   - A rewritten or injected dated sentence goes to its chronological slot, never before the "You stand before…" opener.
   - `standalone_sentence()` makes the injection read naturally. It is deterministic when it can be ("It was also the site of…" → "The <stop> was the site of…", connectives stripped). A connective/pronoun/demonstrative opener ("However, in 1881, these wharves…") gets ONE mini rephrase call with the previous article sentence as context. The result is checked mechanically (same numbers, no new name, no "also", not garbled) and then gated, and it fails closed.
   - `is_preview()` drops "As you move on, a nearby museum…" and "From here, the tour can continue toward…".
5. **Orphan openers after refill/coverage** (`orphan_opener`): the 888 dangling-demonstrative rule plus a first-sentence rule for a definite abstract noun that nothing introduces ("The connection supported…"). A cleft ("It was not until 1959 that a new statue…") is not flagged.
6. **Garble guard** (`garbled`): unbalanced brackets, a fragment opener, a doubled word, "the same <noun> <participle>". A garbled evidence sentence is never injected, and a garbled body sentence is dropped. Using the evidence sentence verbatim does not help for the Kennedy case, because the evidence sentence is itself the garbled one (a parenthesis strip plus a split at "F." left "Kennedy) honoring the same name assassinated U.S."). It is dropped instead.
7. **`Specific Examples`** (`ground_header_items`): an item stays only if all its content words sit in ONE evidence sentence. Otherwise it is dropped, and a stop with no items loses the line.
8. **Found live, fixed after the run:** the event choice prefers a physical event to the building (bombed, damaged, tank) over a political "After the Fall of…" aftermath (see Opera below).

## Offline replay on the LEAD 889 text (`tests/test_local890_coverage_own_article.py::test_replay_on_the_lead_889_text`)
Input: `tests/fixtures/local890_lead889_saigon.txt` (LEAD's 219648b1 text). Evidence: the 889 recorded articles plus the real Wikipedia text of the neighbouring *Paris Commune Square* and of *Bạch Đằng Quay* (`local890_recorded.json`). The Book Street and Thi Bar bundles reproduce the snippet text. The 889 run did not persist its bundles, so this is a stand-in. The closing paragraph is not part of the pass (appended later).
- Book Street: the Tet/Loan sentence is gone. Thi Bar: the 30 April flags sentence is gone. No "Book Street On…" or "Thi Bar On…".
- City Hall: the header is split from the body, and "The building before you was designed by … Gardè" stays in the body (1898, 1909 present).
- Palace: the "As you move on" preview is dropped. "The Independence Palace was the site of the Fall of Saigon on 30 April 1975…" sits after 31 October 1966.
- Pier: no "The connection…" opener, and "In 1881, the wharves north of the arroyo Chinois were transformed into the River port." is restored from its own article (recorded-style rephrase stub).
- Cathedral: the garbled Kennedy sentence is gone, and the square article's events are not used.
- Gains kept: the Opera 1944 event and Olivier, the Post Office's Foulhoux and 1886–1891, no "intelligence headquarters".
- 25 new tests, plus the 889 suite (36) unchanged. **This is an offline replay, not a live measurement.**

## Live run (1 full tour, cloud snapshot, `-p local890`, port 55990, `LOCAL_SNAPSHOT_TAG=890`, code 3efbfda7)
**Meter: $0.3835 over 368 rows** (meter ok). Ledger `LOCAL-890` = **$0.3835 of $0.50**. The finishing pass itself cost $0.0035. The run is a fresh generation, so it is not the same text as LEAD's. No re-run (budget rule).

| Checklist item | Result |
|---|---|
| no foreign event in Book Street or Thi Bar | **PASS** (Book Street 0/0, Thi Bar 0/0; no Tet, no 30 April flags) |
| no glued stop-name prefix | **PASS** |
| no injection into header lines | **PASS** (the City Hall header is clean; `final moved N` was not needed) |
| audit (gpt-4.1) 0 unsupported | **PASS (0)** |
| 10/10 stops, every stop ≥ 4 sentences | PASS |
| every stop ≥ 5 sentences | FAIL (War Remnants Museum 4, Café 4; same as 889) |
| Palace states 30 April 1975 plainly | PASS ("The Independence Palace was the site of the Fall of Saigon on 30 April 1975…", restated by the new rule, after the 1966 sentence) |
| City Hall 1898 and 1909 | PASS |
| no "intelligence headquarters" | PASS |
| Pier "years" key fact (1881) | **PASS** (injected as a standalone sentence; no orphan opener) |
| ≤ 1 sensory sentence per stop | PASS |
| Opera House has 1944 | **FAIL** (see below) |
| no orphan openers | FAIL only on the Thi Bar closing line "this route" (a harness false positive on the closing paragraph, also failing in 889; not a stop-body defect) |
| every key fact present (k == K) | PASS (12/12) |

### Not proven / what the live run showed
- **Opera 1944 (FAIL).** The English article has "In 1944, the theatre was damaged by the Allied aerial attacks…", but the old event choice picked "After the Fall of Saigon in 1975, the Provisional Revolutionary Government started holding…" (higher `event_sentences` score). Fixed after the run (physical event preferred, tested). On the live article text taken from the run's cache it now yields the 1944 event, but **the fixed code was not re-run live**.
- **Cathedral K = 0.** In this run the bundle's English article was the neighbour *Paris Commune Square*, and the cathedral's own article was the **Vietnamese** one. `own_article` correctly refused the square (that is the Kennedy fix). The key-fact patterns are English-only, so nothing was injected. The Cathedral body is the narrator's: it leans on the square and carries a Diệm / Thích Quảng Đức passage that is not about the cathedral. It passed the grounding audit but is off-topic. Not addressed (not in scope; LEAD decision).
- **City Hall** shipped "From here, the tour can continue toward … Café Apartments 42" — a next-stop preview my first `is_preview` pattern missed. The pattern was extended after the run (tested), not re-run live.
- `Specific Examples` was dropped for 8 of 10 stops, because the narrator's generic items ("Stunning neo-Romanesque architecture", "boat tours") are not stated by the evidence; only the War Remnants Museum's two items survived. This is intended (item 6) and may be visible to LEAD as a thinner header.
- The garble guard is a cheap deterministic check (4 patterns), not a grammar check.

## Tests
`pytest tests/test_local87*.py tests/test_local88*.py tests/test_local890_coverage_own_article.py` (without `test_local88_tour_pollution.py`, which fails the same 4 tests on the untouched base: DB-data dependent): **655 passed, 4 skipped**. `run_cloud_parity_proof.py --selfcheck` PASS.

## Artifacts
`submission_artifacts/local890/saigon_warm.txt`, `saigon_warm_audit.json`, `saigon_warm_evidence.json` (the run's evidence bundle, which 889 did not persist). Run and meter logs are in `_local890_meterlogs/` (git-ignored, not committed). `docker-compose.local890-proof.yml` is the own proof stack (project `local890`, port 55990); it has been torn down.
