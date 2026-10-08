# SUBMISSION — LOCAL-634: Prose integrity

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-634-prose-integrity`
**Base:** `subscribed` @ `f543b2f` (verified: `git merge-base --is-ancestor f543b2f HEAD` → exit 0)
**Runs in parallel with LOCAL-633 (D638).** Owned files only: `stop_editor.py`,
`cross_stop_reference_guard.py`, the shortfall/selection path for the Courtauld,
and the gloss/role code. Did **not** edit `practical_facts_gate.py`,
`about_museum_stop.py` or any hours/admission injection.

---

## Summary of the six defects and the fixes

| # | Defect (Bench R1) | Fix | File(s) |
|---|---|---|---|
| 1 | Dropped words — 505 "…at the outbreak of was at a crossroads"; 495 "This painting w. Velázquez…" | Editor now DETECTS the two dropped-word shapes, REJECTS an edit that still contains one, and REPAIRS deterministically as a last resort | `stop_editor.py` |
| 2 | Callback to an unseen work — 505 "Picasso and Braque, whose works you have already seen" (no Braque stop) | Drop a callback that claims the listener saw an artist/title NOT delivered in this tour | `cross_stop_reference_guard.py` + wiring |
| 3 | Title line rewritten — 488/505/506 "Step-by-step audio guided tour of the … is a museum tour." | Restore the canonical header line; header + field lines never edited | `title_line_guard.py` (new) + wiring |
| 4 | Invented role — 495 "John Arrowsmith, a notable 19th-century cartographer" (buyer was the art dealer namesake) | A gloss for a person in a provenance sentence must come from the stop's own record; otherwise degrade (never namesake-gloss) | `unglossed_reference_gate.py` |
| 5 | Courtauld 2 of 3 | Reserve now captured on the GPT-fill branch so replacement-until-N can refill; **partial — see "Courtauld" below** | `generate_tour_text.py` |
| 6 | Borghese 506 dangling opener | Text-level dangling-opener guard on the normal delivery path | `dangling_demonstrative_gate.py` + wiring |

---

## 1. Dropped words (`stop_editor.py`)

The deterministic splice/removal passes that run before the LOCAL-628 editor can
delete a word mid-sentence. Two concrete shapes in Bench R1:

* **Dangling preposition before a verb** — a removed head noun: `the outbreak of
  **[WAR]** was` → "the outbreak of was". Detected by a preposition/article
  immediately followed by a finite verb.
* **Truncated word fragment** — `painting w. Velázquez` ("w." is a dropped word).
  Detected as a lone 1–2 letter token + period that is NOT an abbreviation
  (`St.`, `Mt.`, …) and NOT a real initial (a single uppercase letter followed by
  a capitalised surname: `J. Arrowsmith` is kept).

Changes:
* `detect_dropped_word(text)` — returns the first dropped-word defect or `None`.
* `validate_edit(...)` — **REJECTS** an edit whose body still contains a
  dropped-word pattern (the editor was asked to repair these; keeping one is a
  failed edit), so the original — or the deterministic repair — ships instead.
* `repair_dropped_words(text)` — conservative deterministic repair: removes an
  orphan fragment in place; drops a sentence whose unrecoverable hole cannot be
  filled without inventing the missing word. Adds no word/number/name.
* `edit_stop(...)` — applies the deterministic repair as a last resort on both
  the rejected-edit and empty-LLM paths, so a hole never ships even when the LLM
  edit is rejected or the editor is effectively off. `_reassemble_block` extracted.

**Tests:** `test_local628_stop_editor.py::TestDroppedWord` (9 new) + the 14
existing editor tests — **23 pass**.

## 2. Callback to an unseen work (`cross_stop_reference_guard.py`)

D636 keeps real callbacks ("a couple per tour, for continuity"), but a callback
may name only artists/works actually delivered as stops. 505 shipped "Picasso and
Braque, whose works you have already seen" with no Braque stop. The existing
`strip_phantom_references` caught only title phrases ("such as X", quoted titles),
and `limit_thematic_bridges` budgets by phrasing only — neither checked whether a
named **artist** was delivered.

Added `strip_unseen_callbacks` (stop units) and `strip_unseen_callbacks_in_text`
(delivered text): a sentence that CLAIMS prior viewing ("you have already seen",
"you saw earlier", "whose works you have already seen") AND names an artist/title
whose words are not among the delivered stop titles is dropped; a callback naming
only delivered artists/works is kept. Wired into the delivery-text guard chain
(`generate_tour_text._apply_delivery_hours_guard`) and the two pool-assembly guard
blocks (`stop_pool_assembly.py`).

**Tests:** `test_local627_cross_stop_bridges.py::TestUnseenCallback` (5 new) +
the phantom-reference regression — **18 pass**.

## 3. Title line rewritten (`title_line_guard.py` — new)

488/505/506 opened with the header line turned into a spoken sentence:
"Step-by-step audio guided tour of the Museo Reina Sofía in Madrid, Spain, is a
museum tour." The header and field lines are structure, never narration.
`restore_title_line(text)` deterministically detects that spoken shape on the
tour's first line and restores the canonical
`Step-by-Step Audio Guided Tour: {venue}, {city} - {Category} Tour`. Only the
first line is ever touched; all field lines preserved. Wired FIRST in the
delivery guard chain so every later guard sees the canonical header.

**Verified in production:** the live Courtauld run logged
`[LOCAL-634] restored the canonical title/header line (a pass had rewritten it
into a spoken sentence)` and the delivered first line is the canonical header.
The `title_line_rewritten` detector PASSES on tour 508.

**Tests:** `test_local634_title_line.py` (6) — pass. Includes a `stop_editor`
test proving the banner and field lines survive an edit pass.

## 4. Invented role / provenance namesake gloss (`unglossed_reference_gate.py`)

495 shipped "John Arrowsmith, a notable 19th-century cartographer, purchased it"
— the buyer was John Arrowsmith the **art dealer**, not the cartographer. The
biographical gloss came from the corpus/model path in `supply_glosses`, which
bound the name to a NAMESAKE because the person appears only as a **provenance
agent** (a buyer), not among the stop's own documented sources. The LOCAL-627
namesake guard binds snippets to the delivered WORK's artist; it does not cover a
provenance person.

Added `_is_provenance_sentence(sentence)` (gift / bequest / purchase /
acquisition / sale / commission / collection-entry) and, in `supply_glosses`, a
guard that **DEGRADES** (drops the bare name, keeps the provenance action) any
reference that sits in a provenance sentence and has no documented role from the
stop's own record (stage 2b). `provenance=True` refs (LOCAL-494, Boris Fridman)
are untouched — they are already glossed from the record.

**Tests:** `test_local634_provenance_namesake.py` (6) + 145 gate regression tests
— pass.

## 5. Borghese dangling opener (`dangling_demonstrative_gate.py`)

The unit-level `strip_dangling_openers` runs only on the POOL path. The normal
delivery path emits assembled TEXT, where the stop editor and the late
recap/callback removals can strip a demonstrative's antecedent and leave a stop
body opening on an unresolved "This/That/These + noun" (Borghese 506). Added
`strip_dangling_openers_in_text(tour_text)` — the same opener detection
(setting-noun and generic-subject exemptions, antecedent search) applied to
delivered text. Wired into the delivery guard chain AFTER the recap/callback
guards. The `dangling_opener` detector PASSES on tour 508.

**Tests:** `test_local627_dangling_opener.py::TestStripDanglingOpenersInText`
(4 new) + the 6 existing — **10 pass**.

## 6. Courtauld 2 of 3 — PARTIAL, with the root cause pinned by the live run

The `[LOCAL-632] shortfall` log line for job `d077c3d1` is **not present in this
worktree** (the generator logs are local-only artifacts). I made one safe,
source-level improvement from code analysis — `_museum_verified_reserve` was
captured ONLY on the deterministic-bypass branch (documented ≥ N); I now also
capture it on both "documented < N" GPT-fill branches, so `reconcile_to_n` always
has verified works to refill from.

**The live run (below) then pinpointed the real cause**, which my pre-description
reconcile cannot reach: for the Courtauld, all three stops (Cézanne, Seurat,
Manet) were selected AND had descriptions generated (log:
`Generating description for Stop 3: Manet's A Bar at the Folies-Bergère`), but the
Manet stop was dropped in a **late assembly/gate pass AFTER description
generation** — after `reconcile_to_n` runs (pre-description, ~line 13610). The
scorer then saw `2/3 stops`. A correct fix is a **post-assembly reconcile** that
re-inserts a generated-then-dropped stop (or re-pulls from the reserve and
re-narrates). That path is deep shared delivery/conclusion code co-owned with the
LOCAL-633 concern surface; I did not change it blindly without the exact drop
point. The `stop_count` detector therefore still FAILS on tour 508; this is the
one remaining defect and it is documented honestly rather than papered over.

---

## Tests (task 9) — all exit 0

```
test_local60* / 61* / 62*  (root + tests/)   674 passed   exit 0
test_local6[23]*           (root + tests/)   291 passed   exit 0
test_local590_*                               42 passed   exit 0
python3 test_sq4_merge.py                     ALL TESTS PASSED   exit 0
```

(The `test_local6[23]*` and `test_local62*` batches include the new
`test_local634_*` files and the modified `test_local627_*`/`test_local628_*`/
`test_local632_*` suites.)

---

## Live run (task 10) — OWN disposable container, cap $1.30, reserve gate

* Built image `local634-gen-img` from this branch via `Dockerfile.generator`;
  ran disposable container **`local634-gen`** (`docker run --rm --name local634-gen
  -p 5099:5000 --network development_default`). **Never** `docker compose -p
  audioura`; **never** touched an `audioura-*` container; image removed on exit.
* Cache OFF, pool OFF (fresh), `STOP_EDITOR=1`. Combined hard cap **$1.30** with
  the reserve gate (start a tour only if spend + $0.90 ≤ $1.30).

**Rows (additive is_test only, no DELETE):**

| | audio_tours total | is_test |
|---|---|---|
| before | 313 | 250 |
| after  | 315 | 252 |

The +2 is my row **508** (Courtauld) plus LOCAL-633's parallel row **509**
(Uffizi). My run wrote exactly one additive `is_test` row (508).

**Tour 1 — The Courtauld Gallery, London (3 stops), id = 508:** DELIVERED 2/3
stops, tour cost ≈ $0.85.
* `detectors.py 508 3`: **only `stop_count` FAILS** (2 vs 3).
  `dropped_word`, `callback_to_unseen`, `title_line_rewritten`,
  `dangling_opener` **all PASS**.
* Title line delivered: `Step-by-Step Audio Guided Tour: Courtauld Gallery,
  London, UK - Museum Tour` (canonical — my title-line guard fired in production).
* `critique.sh 508 3`: 4/10. The two High issues are (a) a mangled admission price
  string `"…17:15). 00; Children…"` — this is the **hours/admission injection,
  LOCAL-633's territory and off-limits for this ticket**; and (b) the stop-count
  2-of-3 (defect 6 above).

**Tour 2 — Museo Reina Sofía (3 stops):** correctly **SKIPPED by the reserve
gate** — after the first tour, spend $0.84 + reserve $0.90 > $1.30 cap. The gate
worked as designed; the combined spend stayed under $1.30 (metered total
$0.8239, all providers combined). Running the second tour would have breached the
cap, so only one of the two tours ran.

Live artifacts: `tours/local634_live/local634_live.log`,
`tours/local634_live/detectors_508.txt`.

---

## Detector status on the delivered Courtauld tour (508)

| detector | result |
|---|---|
| dropped_word | PASS |
| callback_to_unseen | PASS |
| title_line_rewritten | PASS |
| dangling_opener | PASS |
| stop_count | **FAIL** (2 vs 3 — late-assembly stop drop, documented above) |

Four of the five required detectors pass on a real fresh tour. The fifth
(`stop_count`) requires the post-assembly reconcile described in defect 6.

---

## Commits (each step committed; branch pushed)

1. stop_editor dropped-word reject + repair
2. tests for dropped-word detection/rejection/repair
3. unseen-work callback guard + wiring + tests
4. text-level dangling-opener guard + wiring + tests
5. provenance-sentence namesake gloss guard + tests
6. title-line guard (restore canonical header) + wiring + tests
7. reserve-capture on the GPT-fill museum branches + Courtauld test
8. isolated live-run harness (Courtauld + Reina Sofía, cap $1.30)

Verify: `git rev-list --count origin/subscribed..HEAD` ≥ 1.
Push: `git push origin LOCAL-634-prose-integrity`.
