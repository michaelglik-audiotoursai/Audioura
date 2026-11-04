# SUBMISSION — LOCAL-864: museum claim gate, stop-identity bleed, catalog wins

Branch `LOCAL-864-museum-claim-gate`, based on `subscribed` e0cc5f43
(`git merge-base --is-ancestor e0cc5f43 HEAD` → 0).

## Verdict (read first)

| PASS criterion | Live evidence | Final code |
|---|---|---|
| Zero undisclosed UNSOURCED claims (log vs text) | **PASS** in all 3 live runs (Asian ×2, Orsay ×1) | PASS (replay) |
| No stop narrating another museum's work | **FAIL** in live Asian run 2: stop 3 still describes Miró's canvas, stop 4 Corot's *Bacchante* | PASS for stops 1–4 and 6 in the offline replay; **stop 5 still open** (see "Not fixed") |
| Two Buddhas carry their catalog culture + date | **FAIL** live: the catalog step never ran (no venue URL on that path) | PASS (replay): 19th-c. Burmese, and Chinese dated 338 |

**The final code was NOT run live.** The task budget is spent (see Budget). Everything
in the "Final code" column comes from an offline replay. That replay runs the final gate over
the live run-2 delivered text, using the museum's real catalog label blocks
(`submission_artifacts/local864/replay_final_gate.py`, no network, no LLM).
A live 6+6 run on the final code is the remaining verification step.

## 1. Why UNSOURCED claims shipped (root causes)

1. **The prompts taught the fabrication.** The museum story prompts in `generate_tour_text.py`
   (the STORY INSTRUCTION block and FINAL STORY SHAPE) and `story_pass.py` used the real MFA Miró case as
   few-shot examples, with concrete names: "Louis Broder commissioned this work from Miró…",
   "Boris Fridman donated this work to the MFA…", "Mourlot's atelier on Rue de Chabrol",
   "Tériade", "Freud". The model copied them into unrelated stops: Broder print editions at
   Orsay, Fridman at the Asian Art Museum, and "a critical mass" (copied verbatim from the example).
   Replaced with `[SLOT]` shapes plus "fill only from the reference material". Test:
   `test_story_prompts_carry_no_real_example_names`.
2. **The gate that should drop them was partial and early.** LOCAL-423 (`verify_stop_claims`, PHASE 5)
   strips only the one sentence that contains the extracted span ("Louis Broder commissioned
   limited"). Every other sentence about the same invented agent survived ("Boris Fridman, who
   collected these editions…", "He donated this statue…"). Later phases (the D511 credit-line loop,
   the LOCAL-474 retries) rewrote stop text after the strip, and nothing re-checked the
   delivered text.
3. **Fix:** new `museum_claim_gate.py`, wired as the last body filter on the delivered museum
   text (after LOCAL-623/626, in `generate_tour_text.py`). Per sentence:
   * flagged span, or any person named in a flagged span → drop;
   * a named agent or dated event that no source for the stop contains → drop. The sources are
     the stop's snippets, the catalog record (including its credit line) and the stop's
     credit/artist fields;
   * D760: a sentence that discloses the claim ("It is sometimes said…", "reportedly", …) is kept;
   * pronoun and back-reference sentences left dangling by a drop ("He donated…", "This decision…",
     "the two statues…", "this pairing") go with it;
   * structural lines (Directions, Continue to, Coordinates) are never touched.

## 2. Stop-identity bleed

* **Snippet scoping (before narration).** A snippet that is another museum's collection record,
  whose title shares only generic words with the stop, is refused. Its work is remembered as
  foreign. Examples: Harvard's *Head of a Buddha, Gandharan style* and a Rochester "Asian Art"
  page for "Head of a Buddha"; a chitra.art Shikibu page for "Landscape of the four seasons".
  `GENERIC_TITLE_WORDS` covers head, landscape, portrait, Buddha, figure, statue, …
* **`accept_stop_match`**: a work matches a stop only when it is this venue's (accession number or
  a URL on the venue's domain, and not labelled as held elsewhere) and its title matches beyond
  generic words. "Head of a Buddha" ≠ "Head of a Catalan Peasant".
* **Delivered-text rules:**
  * A named maker credited with the work must be in this venue's record for the stop: the SPARQL
    venue-works creator, the catalog, or the stop artist. Failing that, he must be bound to this
    work by a snippet whose title is this work. Mere mention in the evidence pool is not enough;
    that is exactly how Corot got in.
  * The foreign maker's work title is banned from the rest of the stop ("Catalan Peasant",
    "Bacchante").
  * "held by the Metropolitan Museum / integrated into the Scottish National Gallery's collection"
    → drop.
  * A work at another named place ("the Amida Buddha statue at the Byōdō-in temple") → drop.
  * If, after that, nothing left names this stop's own object, the leftovers are the other work
    without its name. The body is replaced by the catalog statement or one honest line: "This is
    *X*, in the Asian Art Museum collection. The sources this tour found describe a different
    work, so we say no more about it than that." The stop is never emptied (D577).

## 3. The museum's catalog record wins

The Asian Art Museum's object pages (`collections.asianart.org/collection/<slug>/`) are not
eMuseum, so `object_record.find_object_record` never found them (log: `[D501] no object record`
for every stop). New `parse_label_block` reads the wall-label block by what each line is
(date / place / material / credit+accession), not by position:

* `Buddha dated 338` → China; Hebei province · Later Zhao kingdom (319–351) · Bronze with gilding · B60B1034
* `Crowned and bejeweled Buddha image (and throne)` → Approx. 1860–1880 · Myanmar (Burma); Mandalay area ·
  Wood and iron, with lacquer, gilding, mirrored glass · 2006.27.17

The record URL is found among venue-domain URLs in any stop's snippets or in the run's page cache.
The record title must contain every content word of the stop title, so "Seated crowned and
bejeweled Buddha" does not take the "Crowned … image and throne" record.

`reconcile_with_catalog` overrides a search hit's date, culture and material with the record's.
A sentence giving the object a culture, dynasty, century, material or "national treasure" status
that the record contradicts is dropped. When the narration omits the record's culture and date,
it is stated:

> The museum's catalog records this as a Chinese work dated 338, Later Zhao kingdom (319–351), in bronze with gilding.

The venue URL now falls back to the D1v2 / venue-entity `official_url`, because `_museum_site_url`
was empty on the Asian Art path. That is why the catalog step logged nothing in live run 2.

## 4. Tests

`tests/test_local864_museum_claim_gate.py`: 31 tests, all built from the exact cases. They use
blind texts t4425 / t6291 / t9872, the label-block markup copied from collections.asianart.org,
and the sentences delivered in live runs 1 and 2. `python3 -m pytest tests/test_local864_museum_claim_gate.py` → 31 passed.

Regression: the story/prompt/verifier/bleed test files, with live-network tests deselected, give
10 failed / 955 passed. The same 10 fail on the base without this change (test_local413 ×3,
test_local391 beat-retry, test_local422, test_local424 ×2, test_local431 ×3). No new failures.

## Live runs (own process, host mode: no DB, no shared containers, cheap arm)

`run_local864_live.py`. TASK_BUDGET_ID=LOCAL-864, TASK_BUDGET_USD=1.20, NARRATION_MODEL=gpt-4.1-mini,
RESEARCH_BACKEND=serper, DATABASE_URL unset (never writes any DB).

| run | code | $ | result |
|---|---|---|---|
| Asian run 1 | gate v1 (no catalog / maker binding yet) | 0.383 | UNSOURCED 10 in log, 0 undisclosed in text. Miró, Corot, "blue stone" still present |
| Orsay run 1 | gate v1, old prompts (same process) | 0.420 | UNSOURCED 7 in log (Broder, Fridman, Vollard, Durand-Ruel, 1889), 0 in text |
| Asian run 2 | prompts fixed, maker/held/elsewhere rules, catalog wiring (venue URL missing) | 0.404 | UNSOURCED 4, 0 undisclosed. Miró/Corot partly removed, survivors remain; catalog not applied |

Checker: `submission_artifacts/local864/check_unsourced_vs_text.py <log> <text>`.

## Budget — over by $0.007, plus one unmetered live test

* Ledger `submission_artifacts/local864/meter_ledger.json`: 0.383 + 0.420 + 0.404 = **$1.207 of $1.20**.
  The run-2 pre-start check passed (0.80 + 0.39 estimate ≤ 1.20). Run 2 then cost $0.404, and the
  mid-run guard did not abort it. That should be looked at in `task_budget` / `LiveRunMeter`.
* The Orsay run was started by my background driver (`asian orsay`) without my intending it.
  It used the first-iteration code.
* **Unmetered spend:** while running regression tests I ran
  `tests/test_local391_required_beats.py::TestIntegrationRealPath::test_mfa_exhibition_beat_coverage`.
  It performs a real end-to-end MFA generation (gpt-4o, Gemini) outside the task meter. Its cost
  is not on the ledger and I cannot state it. Later regression runs deselect live tests and unset
  the API keys.

## Every claim the gate changed

### Live (in-run gate; full list: `submission_artifacts/local864/live_gate_changes.txt`)

Asian run 1:
* s1 Orientation preview carrying "2013" national-treasure → dropped
* s2 "This statue, crafted during the Ly Dynasty, is recognized as a national treasure since 2013." → dropped
* s3 "…the same workshop, Mourlot's [Rue de Chabrol]…" (prompt-example Broder bleed) → dropped
* s3 "Directions: Proceed to Landscape…(Asian Art Museum B60D49+)" → dropped (**false positive**, fixed: structural lines are exempt and generic foreign titles like "Asian Art" are ignored)
* s5 "This gift enabled … The Heart of Zen … Six Persimmons" → dropped (unsourced; the logged reason "named agent" was a mislabel)

Orsay run 1:
* s2 "Fridman, a Russian collector specialized in livres d'artiste, assembled…" → dropped
* s2 "His gift brought the museum's holdings of collaborative printed works to a critical mass…" → dropped (the logged reason mislabelled "Van Gogh's" as the agent; possessive handling fixed)

Asian run 2:
* s1 "…in 2013 when the State recognized it as a national cultural artifact…" ×2 → dropped
* s1 "The 11th-century Amida Buddha statue of the Byodo-in temple…" → dropped
* s2 "The donor Avery Brundage gave this work to the museum…" → dropped (**false positive**: Brundage is the catalog credit; fixed, since catalog fields now source names)
* s3 "Joan Miró painted Head of a Catalan Peasant…", "Miró's approach here…", "At this moment in his life, Miró…" → dropped
* s4 "…by Jean-Baptiste Camille Corot between 1865 and 1870…", "Corot's technique…", "Havemeyer … commissioned Corot's paintings…" → dropped
* s5 "Michelin commissioned the statue's conservation efforts in the early 2000s…" → dropped
* s6 "Printer Matsuda then produced precise copies…", "Collector Tanaka gave this mandala…" → dropped. These names were invented by filling the new `[SLOT]` prompt shapes, and the gate caught them.
* snippet scoping refused: Rochester "Asian Art", Harvard 1998.315 Gandharan head, chitra.art Shikibu ×2, Denver "Arts of Asia" (Asian); artwiki/wahooart Cézanne *A Modern Olympia* (Orsay)

### Final code, replayed on Asian run 2 (`final_gate_replay_changes.txt`, output `asian_run2_final_gate_replay.txt`)

* s1: "carved from blue stone" ×3, "Ly Dynasty" ×2, "11th-century" (Byōdō-in comparison), "the two statues", "this pairing" → dropped. **Stated:** "…a Burmese work dated approx. 1860–1880, in wood and iron, with lacquer, gilding, and mirrored glass."
* s2: "carved from blue stone" ×2, "Ly Dynasty sculptors created this statue…" → dropped. **Stated:** "…a Chinese work dated 338, Later Zhao kingdom (319–351), in bronze with gilding."
* s3: "where Head of a Catalan Peasant hangs", oil-and-pencil canvas description, "peasant class in Catalonia", "Scottish National Gallery of Modern Art … their collection" → dropped. Body → honest line (no catalog record for this object was found).
* s4: "Corot created this work…", "The Metropolitan Museum of Art in New York now holds this painting…", the *Bacchante* description, "H.O. [Havemeyer]" → dropped. Body → honest line.

## Not fixed / known limits

* **Stop 5, "Seated crowned and bejeweled Buddha".** It still says "carved from blue stone", "the
  statue of Buddha Amitabha in the main hall", "nearly nine-foot". That is the Vietnamese Phật
  Tích Amitabha leaking across stops. The museum has no collection page for this object
  (`/collection/seated-crowned-and-bejeweled-buddha/` → 404; searchcollection.asianart.org returns
  403 to us), so there is no record to contradict it, and no foreign maker or place is named.
* Stop 2 Orientation "a nearly nine-foot tall figure" survives the replay. The label block has
  no dimensions (the museum's prose says ~16 in.).
* The honest-line fallback ships a stop with no story. That is the correct outcome when the only
  material is another museum's work. It shows that retrieval for generic titles needs the venue
  record first, which is follow-up work.
* Orsay was not re-run on the final code.

## Files

* `museum_claim_gate.py` (new): pure gate, no network, no LLM, no DB
* `generate_tour_text.py`: prompt examples → slots; LOCAL-410 snippet scoping; delivered-text
  claim gate + catalog fetch (≤2 GETs/stop, cache first) + venue-URL fallback
* `story_pass.py`: prompt example → slots
* `tests/test_local864_museum_claim_gate.py` (new)
* `run_local864_live.py` (new): budget-enforced harness
* `submission_artifacts/local864/`: delivered texts, final-gate replay, change lists, ledger,
  replay and checker scripts (no run logs)
