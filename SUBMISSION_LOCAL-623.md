# SUBMISSION — LOCAL-623: stop-body defects on NEW venues

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-623-stop-body-defects` (from `subscribed` @ `0dcfe2a`)
**Base verified:** `git merge-base --is-ancestor 0dcfe2a HEAD` → exit 0 (branched from HEAD, never `origin/*`).

## What this fixes

Museum Folkwang (Essen) tour **468** — a venue we had never generated — scored **3/10**.
The conclusion was already correct (LEAD @ 0dcfe2a); every remaining defect was in the
stop bodies. All five are fixed **at the source**, each with a test on the real 468 text
or its inputs. The canary text/critique I worked from:
`.continuous_dev/calib/critique/tour_468.txt` + `critique_468.md` (in the main repo).

### 1. Same-title / wrong-artist bleed → `same_title_bleed_guard.py` (NEW)
Stop 1 was Honoré Daumier's unfinished *Ecce Homo*, but it also narrated **Lovis Corinth's
1925 *Ecce Homo*** — a different work, by a different artist, in a different museum — pulled
in by a bare-title web search and never bound to the stop's own artist.

The fix binds each stop to its `{title, artist}` and drops any sentence that:
- attributes the stop's **title** to a different hand ("Lovis Corinth painted Ecce Homo…"),
- names a **wrong artist's creation**, or
- **dangles on the wrong artist** just removed ("…he chose to represent himself…", "…that
  Corinth developed late in his career").

A sentence whose only named maker is the stop's own artist is never touched; it never
empties a stop (D577). Wired in `generate_tour_text.py` for museum tours, after the
story-balance pass, keyed on `poi_list` `name`/`artist`. Verified: drops the three Corinth
sentences, keeps all Daumier content.

### 2. Museum preamble in Stop 1 + recurring motif → `about_museum_stop.py`, `museum_motif_guard.py` (NEW)
Two problems, both per **D634**:

- **Founding/merger/building boilerplate** ("established in 1922 by merging … founded in
  1906", "the new building designed by David Chipperfield Architects") landed in Stop 1's
  opening (About) section. `about_museum_stop.is_forbidden_museum_boilerplate` +
  `filter_museum_boilerplate` now drop a **merger of predecessor institutions**, the
  **building / architecture / renovation**, and a **bare founding date with no named
  founder** from the About narration — while **keeping a real founder/collector story**
  (a named person: the Griffin's "founded in 1992 by the photographer Arthur Griffin,
  dedicated to promoting photography" survives, as D634 requires). Applied in
  `_compose_about_narration`; falls back to the pre-filter body rather than ship an empty
  About (D577).
- **The museum-endurance motif recurred** across stops ("The museum story of preservation
  and renewal …", "concealment and revelation", "broader patterns that have shaped the
  collection"). `museum_motif_guard.filter_tour_text_museum_motif` drops that abstract
  refrain from every **stop body** (the Stop-1 About section — where the museum's real
  story belongs — is exempt). Wired for museum tours in `generate_tour_text.py`.

74 About tests pass unchanged.

### 3. Garbage address → `about_museum_stop.py` + `stop_pool_assembly.py`
`Address: 1922 by way, Essen, Germany` — a narrative year + preposition mis-parsed as a
street. The address regex is `re.IGNORECASE`, so its "Capitalised street word" requirement
was void: "acquired in 1922 **by way** of…" matched as house-number `1922` + street `by` +
suffix `way`.

New pure predicate `is_valid_street_address` rejects a **four-digit-year house number**
(1500–2099) and a street-name run whose only words are **lowercase function words** ("by",
"of", "in") with no genuine Capitalised name. It is applied:
- at the **source** — `extract_venue_address` now walks every candidate and takes the first
  that validates (so the narrative "1922 by way" is skipped, and a real address later in the
  text is still found);
- at the **render boundary** — `_render_stop_block` omits the `Address:` line entirely when
  the slot does not hold a valid street address (the task's fallback-or-omit rule).

Real addresses pass ("67 Shore Road, Winchester, MA 01890", "10½ Beacon Street",
"Barer Str. 27"); "1922 by way" is rejected.

### 4. Citation leftover in narration → `about_museum_stop.py` + `spoken_text_hygiene.py`
"…can be added for €1, **as published by the museum in October 2026**." — a provenance tail
a listener hears aloud. Two-part fix:
- **Source:** `_compose_visiting_sentences` no longer appends the month-stamp signal to the
  spoken hours/admission sentence. Provenance (domain **and** date) is text-view-only, the
  same way D617 moved the source domain out of speech. The `AboutStop.as_of` field still
  exists for the text view.
- **Belt-and-braces:** new `spoken_text_hygiene.strip_citation_tails` (+ `CITATION_TAIL_RE`,
  `AS_OF_TAIL_RE`), wired into `clean_spoken_text` (the pipeline's final spoken pass), strips
  any residual "as published/listed/stated by the museum in <month> <year>" / "as of <month>
  <year>" tail from any path (pooled stops, etc.), keeping the fact. Tolerates domain dots
  ("griffinmuseum.org"); no false positive on "praised by critics **as a masterpiece**".

One prior test (`test_local614_no_spoken_source_domain`, two assertions) required the spoken
month stamp — that LOCAL-614-item-4 decision is **superseded** by this ticket's ruling, so
those two assertions were updated to assert the stamp is **not** spoken (the facts still are).

### 5. Dropped possessives / subjects → `unglossed_reference_gate.py`
"Corot scene", "the painting celebration" (should be "Corot's scene", "the painting's
celebration"). Root cause, confirmed on the real text: in
`_clean_degrade_artifacts` the orphan-possessive cleanup had two branches —
```
sentence = re.sub(r"(\s)'s\b", r'\1', sentence)   # straight: ORPHAN only (correct)
sentence = re.sub(r"\u2019s\b", '', sentence)      # curly:   strips ALL (bug)
```
The curly-apostrophe branch had **no "no word before it" guard**, so it removed **every**
curly `'s` in the whole sentence. Fixed to orphan-only, symmetric with the straight branch:
```
sentence = re.sub(r"(^|\s)'s\b", r'\1', sentence)
sentence = re.sub(r"(^|\s)\u2019s\b", r'\1', sentence)
```
A possessive bound to a real word now survives for both apostrophe styles; a dangling `'s`
(the real orphan, after an entity was excised) is still removed. 89 degrade/possessive tests
pass.

## Tests (item 6)

New: `test_local623_stop_body_defects.py` — one+ test per defect, grounded on the real tour
468 text/inputs (16 tests, all pass).

### Specified suite — each exit code

| Suite | Result | Exit |
|------|--------|------|
| `tests/test_local60* 61* 62*` | 350 passed | 0 |
| `tests/test_lead_double_conclusion.py` | 2 passed | 0 |
| `test_local617_work_first.py` | 47 passed | 0 |
| `test_local618_*.py` | 33 passed | 0 |
| `test_local620_story_types_prefs.py` | 27 passed | 0 |
| `test_local590_*` | 42 passed | 0 |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | 0 |
| `test_local623_stop_body_defects.py` (new) | 16 passed | 0 |

Pre-existing, unrelated: `tests/test_local359_scope_check_address` has 4 failures **on the
base commit 0dcfe2a** (verified by checkout). It is not in the specified suite and was not
touched by this ticket.

## Live run (item 7) — honest result

Own disposable container (`local623-gen` / `local623-gen-2`, `docker run --rm`, built from
`Dockerfile.generator` on this branch, `--network development_default`). It only INSERTs
`is_test` rows; it never touched any `audioura-*` container and used no stack generator
service. Tour cache OFF (fresh). Metered + hard-capped.

**Three venues never generated before** (verified `audio_tours` name count = 0 first):

| id | Venue | Stops | Delivered | Critique |
|----|-------|-------|-----------|----------|
| 469 | Musée d'Unterlinden, Colmar, France | 2 | ✓ | **3/10** |
| 470 | Statens Museum for Kunst, Copenhagen | 2 | ✓ | **3/10** |
| 471 | Alte Pinakothek, Munich, Germany | 2 | ✓ | **2/10** |

(The ticket's suggested Kunstmuseum Basel and Ateneum had already been generated — 9 and 1
prior rows — so they are not fresh. Mauritshuis **failed venue resolution** — the resolver
matched the wrong Wikidata entity `Q17324051` with 0 works, a resolver bug unrelated to this
ticket — so it was replaced with Alte Pinakothek.)

**Row counts:** before 274 → after 277 (+3 additive `is_test` only; no DELETE).
**Combined cost:** **$0.852** (run 1 $0.3598, run 2 $0.4921) — under the $1.50 cap.

### Every venue is under 6/10 — why, honestly

The LOCAL-623 fixes **work**: all five target defects are **absent** in all three fresh tours
(verified by grep on the delivered spoken text and by reading each critique):
- addresses are clean (`Bredgade 14, 1260 København`, `Barer Str. 27`) or correctly
  **omitted** rather than garbage (Unterlinden), with no four-digit-year house numbers;
- no "as published by the museum …" citation leftover;
- no same-title / wrong-artist bleed;
- no recurring museum-endurance motif;
- no dropped possessives.

The sub-6 scores are driven by **different, pre-existing defects that are outside this
ticket's scope** — the critic's top findings on these three tours:

1. **A recap/conclusion glued inside Stop 2's body** — "Together, these stops… That's 2
   stops in all." (all three; criteria 5/6). This is conclusion-placement on the fresh
   2-stop path, LOCAL-619's territory, not one of the five LOCAL-623 stop-body defects.
2. **Garbage opening-hours formatting** — "Museum Information: 00–18; 00–20; 00–17; 00–19"
   (Alte Pinakothek; criterion 3/8): midnight-start ranges, no day labels, no admission
   price. A practical-facts formatting bug, separate from the five.
3. **Stop 2 is a room/building, not an artwork** — Alte Pinakothek's "Kabinett 1-2" with
   von-Klenze building history (criterion 1): a stop-selection problem.
4. **A garbled appositive** — "Carl Bloch, an oil-on-canvas painting by Bloch" (SMK;
   criterion 8): a narration-template splice.
5. **Dry accession/funding filler leading Stop 1** and **2 stops unexplained** (criteria
   1/7).

So the canary's five stop-body defects are resolved, but a fresh 2-stop museum tour still
has independent problems that keep it under 6. I did not expand scope to those here; they are
distinct tickets (conclusion placement on the fresh path; practical-facts hours formatting;
stop-selection binding each stop to a work+artist). Flagging them honestly, as asked.

## Files

New: `same_title_bleed_guard.py`, `museum_motif_guard.py`,
`test_local623_stop_body_defects.py`, and the live-run artifacts
`run_local623_container.py`, `run_local623_one.py`, `run_local623_live.sh`.
Changed: `about_museum_stop.py`, `spoken_text_hygiene.py`,
`unglossed_reference_gate.py`, `stop_pool_assembly.py`, `generate_tour_text.py`,
`tests/test_local614_no_spoken_source_domain.py`.

Not touched: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, .continuous_dev/STATUS.md.
