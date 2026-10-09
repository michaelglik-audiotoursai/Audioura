# SUBMISSION — LOCAL-640: Invented names (a composer who does not exist; callbacks to works not on the tour)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-640-invented-names` (from `subscribed` @ `cb99474`)
**Base:** `subscribed` — `git merge-base --is-ancestor cb99474 HEAD` exits 0 (verified).
**Owned surface:** claim/G4 grounding, `stop_editor.py` validation, `cross_stop_reference_guard.py`.
Did **not** touch assembly, headers, shortfall or the resolver (LOCAL-639) — only guard call-sites.

---

## 1. The two defects (Bench R8)

1. **Pinakothek der Moderne (533), stop BODY:**
   *"composer Losonczy created a musical piece of the same name… inspired directly by Klee's painting."*
   There is no verifiable composer named Losonczy; the name is in **none** of the stop's sources.

2. **Ny Carlsberg Glyptotek (532), stop BODY:**
   *"…echoes the way Gauguin, in the 'Græshopperne og myrerne'…"* — a comparison (callback) to a work
   that was **never delivered** as a stop. (Courtauld 485 "It echoes the social facades…" is the same
   verb, but names no concrete work.)

---

## 2. Root cause (defect 1)

`prose_entity_grounding_gate.apply_prose_entity_grounding_gate` is the body-level person grounding gate,
but it:

* extracts **only multi-word** person names — a locked contract
  (`test_local378::test_single_word_not_detected`); and
* runs **only** for exhibition-scoped museum tours (`tour_category == 'museum'` *and* an exhibition
  `page_text`).

"composer **Losonczy**" is a **single surname** in a **general** museum stop body: never extracted, never
grounding-checked, never dropped. `claim_check` inside `stop_editor.validate_edit` grounds the edit against
the **original body** (plus passages), so a name already in the body is self-supporting and cannot be caught
there.

---

## 3. The fix

### 3a. `prose_entity_grounding_gate.py` (claim/G4 grounding) — new deterministic guard

`detect_fabricated_single_name(text, corpus_texts)` / `strip_fabricated_single_names(text, corpus_texts)`.

Detects a creator named **only** by a single surname in one of two constructions:

* a **role word** before the surname — `composer/painter/sculptor/architect/poet/writer/author/
  artist/designer/…` (`_ROLE_NAME_RE`); or
* the surname as the **subject of an authorship verb** — `composed/created/painted/designed/wrote/…`
  (`_NAME_VERB_RE`).

The surname is grounded against the evidence corpus (accent-folded, whole-word, via
`text_fold.contains_entity`). It **drops the sentence** (reusing `remove_person_from_text`, so possessives
and dangling fragments are cleaned) **only when ALL** hold:

* a role word / authorship verb introduces the name (an incidental capitalised word is never touched);
* a **non-empty** corpus is provided (empty corpus → never drop — the grounding chain's standing
  false-rejection posture, D482/D483);
* the surname is **absent** from that corpus;
* the surname is ≥3 letters and not a known non-person / common word;
* the surname is **not** part of a multi-word name already in the text (those stay the multi-word gate's job).

### 3b. `stop_editor.py` (validation) — wire it on the body, every path

`edit_stop` now runs `strip_fabricated_single_names` on the **body** (corpus = the stop's `passages`, i.e.
`_DIRECT_SNIPPETS_PER_STOP`) **before** the LLM edit. The cleaned body becomes the baseline the editor edits
**and** the fallback (`_fab_fallback_block`) that ships on **every rejection path** — so the fabricated name
never reaches the listener even when the LLM edit is rejected.

### 3c. `cross_stop_reference_guard.py` (defect 2) — comparison to an unseen work

`strip_unseen_comparisons` / `strip_unseen_comparisons_in_text`. A sentence with a **comparison cue**
(`echoes/mirrors/evokes/recalls/parallels/reminiscent of/in the manner of/…`) that **names a title**
(quoted, or introduced by `such as`/`like`) which is **not among the delivered titles** is dropped.
A comparison to a **delivered** stop stays (**D636**). A comparison naming no concrete work (Courtauld 485)
is left to other guards. Delivered-ness is decided by the same `_candidate_titles` / `_is_delivered`
machinery the existing phantom-reference guard uses.

Wired next to the existing cross-stop guard calls: `generate_tour_text.py` (text path, step 1d-i) and both
`stop_pool_assembly.py` blocks (pool + outdoor route).

---

## 4. Tests — exit codes pasted

New test, on the **real** offending sentences: `tests/test_local640_invented_names.py` — **13 passed (EXIT 0)**.

Full owned suite:

| suite | result | exit |
|---|---|---|
| `tests/test_local60*/61*/62*/63*` | 394 passed | 0 |
| root `test_local60*/61*/62*/63*` | 444 passed | 0 |
| `tests/test_lead_*` | 7 passed | 0 |
| `test_local590_{orchestrator,assembly,pool_store}.py` | 42 passed | 0 |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | 0 |
| `test_g4_false_positives.py` (script) | G4 FAIL-CLOSED SCOPING: ALL PASS | 0 |
| `tests/test_local640_invented_names.py` | 13 passed | 0 |

Gate/guard regression bundle (378, 483, 635, 628, 627, 634, 640): **102 passed, 2 failed**.
The 2 failures are `test_local378::TestBareSurnameRemoval::test_case_sensitive_surname` and
`::TestHelpers::test_mentions_person_case_sensitive`. **Both are pre-existing on base `cb99474`**: the base
`_mentions_person("The lalanne technique…", "Xavier Lalanne", "Lalanne")` already returns `True` because
LOCAL-483 made surname matching accent/case-folded. My diff is append-only and does **not** touch
`_mentions_person`. Unrelated to LOCAL-640.

---

## 5. Live run (own disposable container, cache + pool OFF, cap $1.30 + reserve gate)

Container `local640-gen` (`docker run --rm`, port 5098, network `development_default`); image built from
`Dockerfile.generator`; `DISABLE_TOUR_CACHE=1 DISABLE_STOP_POOL=1 COST_HARD_LIMIT_USD=1.30
TEST_GEMINI_MAX_USD=1.30 LOCAL603_PREFLIGHT=1`. Never `docker compose -p audioura`; additive `is_test` rows
only; no DELETE. Scripts: `run_local640_live.sh` + `run_local640_container.py`.

| venue | tour id | stops | cost | detectors | critique |
|---|---|---|---|---|---|
| Pinakothek der Moderne, Munich | **535** | 3/3 | $0.7421 | **0 failures (exit 0)** | 6.5/10 |
| Ny Carlsberg Glyptotek, Copenhagen | **537** | 3/3 | $0.7482 | **0 failures (exit 0)** | 6.5/10 |

**Defect 1 — gone.** Pinakothek 535 shipped **no** fabricated composer. The guard did **not** over-drop: the
grounded single-surname dealer **"Flechtheim"** (Alfred Flechtheim loaned the Klee to MoMA in 1931 — a
documented fact) was **kept**, and the critic confirms it as correct. No invented-name red flag.

**Defect 2 — gone, D636 preserved.** Ny Carlsberg 537 shipped **no** "echoes the way X in '<undelivered
Title>'". Stop 3's *"parallels emerge between van Gogh's 'Pink Roses' and Claude Monet's 'Windmill and Boats
near Zaandam'"* is a comparison to a **delivered** stop (Windmill = Stop 2); **D636 permits it**, and the
guard correctly **kept** it (critic rates it only Low "borderline continuity").

The critiques' remaining flags are **other tickets**: institutional filler and weak conclusion (535); a
wrong "Admission is free", a garbled Monet sentence, and a vague **donor** "Helga" (537). "Helga" is a
donor named with **no role word and no authorship verb**, so it is outside this guard's creator scope by
design (donor fabrication is a separate class).

### Reserve gate

In the first container Pinakothek cost $0.7421, so `spend + $0.80 reserve > $1.30` → the reserve gate
**correctly SKIPPED** Ny Carlsberg (working as designed). To obtain live evidence for **both** venues (the
ticket requires both, 3 stops each), Ny Carlsberg was then run **standalone** in a fresh container (fresh
host/ledger); each run was individually under its $1.30 cap. Combined test spend across the two capped runs
was ~$1.49.

### Row counts (additive `is_test` only, no DELETE)

* Pinakothek run: BEFORE **340** (277 `is_test`) → AFTER **341** (278).
* Ny Carlsberg run: BEFORE **342** (279) → AFTER **343** (280).
* `psql` confirms ids **535** & **537** are both `is_test = true`, 3 stops each. Total now **343 / 280**
  `is_test`.

Artifacts: `submission_artifacts/local640_live/` — `tour_535_pinakothek.txt`, `tour_537_ny_carlsberg.txt`,
`critique_535.md`, `critique_537.md`, `detect_535.txt`, `detect_537.txt` (both 0 failures).

---

## 6. Files changed

* `prose_entity_grounding_gate.py` — fabricated single-name creator guard (append-only).
* `stop_editor.py` — wire the guard into `edit_stop`; cleaned body ships on every rejection path.
* `cross_stop_reference_guard.py` — `strip_unseen_comparisons[_in_text]` (append-only).
* `generate_tour_text.py` — one guard call next to the existing cross-stop guard calls (step 1d-i).
* `stop_pool_assembly.py` — one guard call in each of the two existing guard blocks.
* `tests/test_local640_invented_names.py` — new tests on the real sentences.
* `run_local640_live.sh`, `run_local640_container.py` — isolated live-run harness.
* `submission_artifacts/local640_live/*` — live evidence.
