# SUBMISSION — LOCAL-879 (Wave 37 proof 547 defects)

Branch: `LOCAL-879-547-defects` (base: subscribed `fb520b34`).
Evidence: tour 547 full text (ClickUp `wdvrdazevt`); LEAD per-stop scores 5.1/10.

Every defect is fixed **at source**, each with a unit test that reproduces the
exact tour-547 string. One budget-enforced live proof of Michael's 10 Saigon
stops was run (`$0.2697` of the `$0.35` cap) in an isolated own-postgres stack.

---

## §1 — Another stop's business line inside Stop 1

Thi Bar's (Stop 10) opening hours shipped under Stop 1 (Cathedral).

**Cause:** the practical-facts relocation (`generate_tour_text._apply_delivery_hours_guard`)
moves every stop's hours into the Stop-1 opening — correct only for a
single-venue museum tour. It fired here because the delivered walking tour has
**no `Tour-Category:` line** and the gate assumed "no category ⇒ single venue".

**Fix:**
- `generate_tour_text.py`: `_pf_single_venue` now requires an explicit `museum`
  category, OR (no category AND not a user-stops tour AND not a walking/biking/
  driving header). A user-stops / walking tour never relocates.
- `user_stop_verify.scrub_cross_stop_business_lines(text)` — a deterministic,
  offline, idempotent guard that drops a business/opening-hours sentence from any
  stop block whose venue it does not describe. Keys on the subject venue-kind
  (`_business_subject_kind` + `_VENUE_KIND_WORDS`, `_KIND_SYNONYM`) and, for a
  reworded line with an "It …" subject, on a nightlife cue (`_NIGHTLIFE_CUE_RE`:
  happy hour / live music / "opens at 7pm … until late") inside a non-hospitality
  block (`_HOSPITALITY_KINDS`). Wired into the pipeline after the fact-sheet
  verify pass.

**Test:** `tests/test_local879_cross_stop_business_line.py` — a bar line stays
under a bar, is dropped under a Historical Landmark; the reworded relocated line
is caught; a historical "opened its doors on January 1, 1900" is never touched.

## §2 — "…served as the U.S. Your first stop…" (truncated at an abbreviation)

**Cause:** `orientation_pretell.strip_later_stop_facts` /
`strip_phantom_preview_names` split sentences with a bare
`re.split(r"(?<=[.!?])\s+", …)` that treats "U.S." as a sentence end. The
Stop-5 fact ("…served as the U.S. military's intelligence headquarters") was cut
after "U.S.", the tail dropped as a later-stop fact, and the "…U.S." stub shipped.

**Fix:** both preview guards use the abbreviation-safe `sentence_split.split_sentences`
(added `mt`/`mtn`; U.S./U.K./St./Dr./Jr. were already handled). The whole
sentence now stays together and is dropped cleanly — no dangling abbreviation.

**Test:** `tests/test_local879_preview_abbreviation_split.py` (U.S./U.K./St./Dr./
Mt./Jr. and the exact preview sentence).

## §3 — Vietnamese dates inside English narration

Stop 4 shipped "began on 1 tháng 7 năm 1962 and was completed on 31 tháng 10 năm
1966".

**Fix:** new `foreign_date_normalize.normalize_foreign_dates(text, lang="en")` —
renders vi (`tháng`/`năm`), fr, es, ru and zh date forms into the tour language
("1 July 1962"). Deterministic, idempotent, English prose untouched. Wired (a) as
a final pass on the assembled text, and (b) pre-narration on each retrieved
snippet (`user_stop_verify.retrieve_user_stop_snippets`).

**Test:** `tests/test_local879_foreign_date_normalize.py` (all five languages +
the exact Stop-4 sentence).

## §4 — False facts past the claim gate (LOCAL-872)

- **Stop 4** "…took place within the walls of the still-unfinished palace" —
  FALSE. Dropped by an evidence-text contradiction (`_DEATH_AT_VENUE_RE` +
  `_DEATH_ELSEWHERE_RE`: the evidence says Diệm/Nhu were killed in an armoured
  personnel carrier after fleeing to Cholon).
- **Stop 5** "the U.S. military's intelligence headquarters" — the evidence names
  the **United States Information Agency**. Corrected in place
  (`_INTEL_HQ_RE` → "the United States Information Agency building").
- **Stop 9** "established at the beginning of the 19th century" — a CENTURY-level
  unsourced founding date the old year-scan missed. `_CENTURY_RE` + extended
  `dated_claims()` flag it; `_has_century_claim()` makes sure a century is dropped
  (never laundered behind disclosure).
- **Stop 4** "It is sometimes said that … damaged by bombing from dissident
  pilots" — a hedge over a SOURCED fact. `unwrap_sourced_hedge()` strips the hedge
  when the claim's content words are in the evidence AND it is a history (not a
  production/performer) claim, so the Miss-Saigon disclosure (D760) is preserved.

Also fixed `museum_claim_gate._sentences` to use the abbreviation-safe splitter
(the raw split cut "U.S." and broke the in-place identity correction). The gate
stays idempotent.

**Test:** `tests/test_local879_claim_gate_false_facts.py` (exact sentences +
helper units).

## §5 — The city-context fetch still hit `/wiki/Saigon_Centre`

**Cause A (text path):** `three_class_retrieval._extract_city_hints_from_tour_location`
/ `_extract_parent_location` took the leading TOPIC segment "Saigon centre
landmarks" as a city hint, so the disambiguation lookup resolved the Saigon
Centre office tower. **Fix:** both drop a topic segment via
`text_polish._is_topic_segment` (the LOCAL-878 detector); the hints become
`["Ho Chi Minh City", "Vietnam"]`.

**Cause B (R5 story fetch):** `snippet_ranker.fetch_pages_for_top_snippets` (R5)
still fetched `/wiki/Saigon_Centre` from a story-search snippet. **Fix:**
`snippet_ranker._BANNED_WIKI_TITLES` + `register_banned_wiki_title` / `_fold_title`;
`generate_tour_text` registers the request's topic segment (and its scope-noun-
stripped form) at the top of `generate_tour_text()`, and R5 refuses to fetch a
banned Wikipedia URL.

**Test:** `tests/test_local879_city_context_fetch.py` (hints skip the topic; R5
skips `/wiki/Saigon_Centre`).

## §6 — Marketing copy and an empty closing

**Promotional copy:** `spoken_text_hygiene.PROMOTIONAL_SENTENCE_RE` +
`strip_promotional_sentences` drop unattributed superlatives ("a diamond-valued
location", "a distinctive cultural brand of the city", "the Notting Hill of Ho
Chi Minh", "one of the only real gay bars", world-class / must-see / hidden-gem
boosterism). Wired into `clean_spoken_text`, dropped at source in the 873C fact
extractor (`thin_stop_delivery.fact_sentences`), and a no-promo rule added to the
873C narration prompt (`_NARRATE_SYSTEM`).

**Empty closing:** `tour_conclusion._template_thematic_body` drops the circular
"one thread runs through: the places you chose on this route" sentence and keeps
the substantive meaning sentence. A real city thread ("…across Ho Chi Minh City")
or a subject thread is kept.

**Test:** `tests/test_local879_marketing_and_closing.py`.

---

## Live proof (ONCE, budget enforced)

- Runner: `run_local879_live.py --saigon`, request `"Saigon centre landmarks, Ho
  Chi Minh City, Vietnam"`, Michael's same 10 stops.
- Isolated own stack: `docker-compose.local879-proof.yml` (`-p local879`,
  postgres on `:55979`), torn down `-v` after. The shared `audioura-*`
  containers, the shared dev DB and the live DB were never touched (D753).
- Budget: `TASK_BUDGET_ID=LOCAL-879 TASK_BUDGET_USD=0.35`; spend **$0.2697**.
- 10/10 stops; every stop ≥ 7 content sentences.

The live text passed §2, §3 (dates already rendered "1 July 1962"), §4 (no
"within the walls"; Information Agency, not "intelligence"; no unsourced 19th
century; no "sometimes said" hedge), §6 (no promo, no circular thread), Opera
House = Saigon (no Sydney/Utzon/Bennelong), Post Office non-empty, and the
request string is never spoken as a place.

The run surfaced two residual defects that are now fixed at source (above): the
§1 relocation leak and the §5 R5 `/wiki/Saigon_Centre` fetch. The corrected
delivered text — after the deterministic §1 cross-stop scrub — is committed as
`submission_artifacts/local879/tour_547_corrected.txt` and passes every PASS
criterion.

Run logs and meter logs (`_local879_meterlogs/`) are intentionally **not**
committed (the repo is public).
