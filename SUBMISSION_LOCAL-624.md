# SUBMISSION — LOCAL-624: Narration splices on new venues

**Branch:** `LOCAL-624-narration-splices`
**Base:** `subscribed` @ `a674cde` (verified ancestor of HEAD)
**Agent:** Mac Mini Kiro

Two narration splices shipped on the 2026-10-08 LOCAL-623 field tours. On
Statens Museum for Kunst (tour **470**):

- **Stop 1**, *In a Roman Osteria* by Carl Bloch — the **artist** was given an
  appositive that describes the **work**:
  - "…commissioned **Carl Bloch, an oil-on-canvas painting by Bloch,** to create a painting…"
  - "**Bloch, an intensified version of Marstrand's painting,** reached a pivotal moment in his career…"
- **Stop 2**, *View from the Artist's Window* — a sentence lost its object:
  - "…faithfully rendered in oil with the meticulous attention to detail **that characterized.**"

---

## 1. Root cause — PROVEN by replay, not assumed

The suspect was `unglossed_reference_gate.py` Stage 3 ("corpus first"). I proved
it with a deterministic replay (`scratch/replay_624.py`, plus inline
reproductions), never by assumption.

### Appositive type-mismatch (Stop 1)
1. `_is_well_known("Carl Bloch")` → **False**. On the bare sentence
   "commissioned Carl Bloch to create a painting", Stage 1
   (`detect_unglossed_references`) **flags "Carl Bloch" as a person needing a
   gloss** — confirmed.
2. Stage 3a (`_search_corpus_for_fact`) for the person "Carl Bloch" returns the
   **painting's own record** from the stop corpus — "*In a Roman Osteria is an
   oil-on-canvas painting by Carl Bloch, created in 1866.*" — because the
   artist's name appears inside the work's record as "…by Carl Bloch".
   Confirmed.
3. Stage 4 composes that into the appositive "an oil-on-canvas painting by
   Bloch"; `_insert_composed_gloss` reproduces the delivered splice **verbatim**:
   "commissioned Carl Bloch, an oil-on-canvas painting by Bloch, to create a
   painting…". Confirmed.
4. The five mechanical guards (`_guard_spliced_sentence`, `_guard_doubled_name`,
   `_guard_trailing_preposition`, `_guard_length`, `_guard_host_duplication`)
   **all pass** this garbage — none check that the gloss's **type** matches the
   entity's type. That is the gap.

The stop's `artist` exempt (`_is_exempt`) *would* have spared Bloch had it been
populated/matched for this stop; it wasn't. So the fix is **structural**, not a
reliance on the exempt list.

### Truncated clause (Stop 2)
The gate's own **degrade** path produced it. The original read "…that
characterized **the Danish Golden Age**." The gate flagged "the Danish Golden
Age" as an unglossed reference and `_excise_governed_construction` removed it
*together with its article*, leaving the transitive verb "characterized"
governing nothing → "…that characterized." The degrade well-formedness guards
(`_degrade_sentence_is_wellformed`, `validate_degrade_output`,
`validate_and_repair_full_text`) **all pass** it — none test the **end** of the
clause. Confirmed by replay: `_degrade_reference_in_text(…, "Danish Golden
Age")` yields exactly "…that characterized."

---

## 2. The fixes (all in `unglossed_reference_gate.py`)

### Deliverable 1 — a gloss must match the entity's type
- `_search_corpus_for_fact(entity, passages, category=…)` — for a **person**
  entity it now **rejects** a corpus sentence that is about a **work** (the
  person appears only as "…by/after X"), so the painting's record is never
  handed to the person. Falls through to model/degrade instead.
- `validate_gloss(gloss, host, entity, category=…)` — a backstop guard that
  catches the mismatch from **any** source (corpus, model, compose): it fails
  with reason `type_mismatch_work_for_person` when the entity is a person and
  the gloss **describes a work**.
- `_gloss_describes_a_work()` is **type-precise, not keyword-crude**. It fires
  only when the appositive **is** a work — its head noun is a work form
  ("an oil-on-canvas painting", "a bronze sculpture"), or it opens "a version/
  copy of …", or "a &lt;work&gt; by &lt;someone&gt;". A **person-role noun**
  anywhere ("master", "figure", "painter", "pioneer", "merchant", …) vetoes it,
  so legitimate artist glosses — "a master of landscape painting", "a prominent
  figure in the Hudson River School of painting" — are **never** blocked.
- The stop's **own title and artist are never glossed**: `apply_unglossed_
  reference_gate` now folds `stop_name` and the stop record's
  `artist/title/name/creator/collaborator/writer` into the exempt set
  structurally (belt-and-braces with the type guard).

### Deliverable 2 — no truncated clauses
Fixed **at source** and with a **final net**. New guards:
- `_DEGRADE_GUARD_DANGLING_RELATIVE` — a relative pronoun + a **transitive-only**
  verb at the period ("that characterized.", "which revealed.", "that shaped.").
  The verb set is **closed and transitive-only** so legitimate complete relative
  clauses survive ("modern guitars that followed.", "the artist who painted the
  ceiling.").
- `_DEGRADE_GUARD_LONE_TRAILING_VERB` — a lone verb between a comma and the
  period ("In this painting, stands .").
- `_DEGRADE_GUARD_STRANDED_BARE_OBJECT` — an acquire/create/trade verb welded
  onto a **determiner-less countable work-noun** ("…to obtain painting." — found
  in the live run, see §5). Mass-noun ("religious painting.") and determined
  ("to obtain a van Gogh painting.") uses survive.

These are wired into `_degrade_sentence_is_wellformed` (so the degrade **drops
the sentence at source** instead of emitting the truncation) and into
`validate_degrade_output` (reported as guard `truncated_clause`).
`validate_and_repair_full_text` remains the final net that drops any such
sentence from **all** sources.

### Deliverable 3 — a further class found by the scan
`validate_and_repair_full_text` now **repairs** an empty / half-empty
interpolated parenthetical ("(État / )", "( / )", "()") by excising it, rather
than dropping the whole sentence — keeping the real funding story. Legitimate
parentheticals (dates, "(open daily…)") are preserved.

---

## 3. Scan — every splice found

Scanned 469/470/471, the **Kunsthaus/Orsay/Thyssen** tours in `audio_tours`
(ids 443–460), and the older on-disk texts (`scratch/scan_splices_624.py`).

| Tour | Venue | Class | Quote | Status |
|------|-------|-------|-------|--------|
| 470 | Statens Museum for Kunst | A person-as-work | "Carl Bloch, an oil-on-canvas painting by Bloch" | fixed (guard) |
| 470 | Statens Museum for Kunst | A person-as-work | "Bloch, an intensified version of Marstrand's painting" | fixed (guard) |
| 470 | Statens Museum for Kunst | B truncated clause | "…that characterized." | fixed (guard, source+net) |
| **454** | **Kunsthaus Zürich** | A person-as-work | "van Ruisdael, the 1665 Baroque landscape painting" | **same class, earlier tour** — fixed (guard), regression-tested |
| 469 | Musée d'Unterlinden | C empty field | "…pour les Musées **(État / )**, and private donors" | fixed (repair) |

- **471 (Alte Pinakothek): clean.** All other Orsay/Thyssen DB tours: clean of
  these classes.
- `enhanced_tour_content.txt` (an old demo file, out of scope) also carries a
  Class-C empty artist field; noted, not shipped by current generation.

The 454 van Ruisdael case is the **same person-glossed-as-work class** in an
earlier Kunsthaus tour — the type-match guard rejects it, and it is a regression
test.

---

## 4. Tests — each exit code

`test_local624_narration_splices.py` (17 tests): the exact 470 sentences for
both deliverables, the 454 van Ruisdael regression, the 469 empty-field repair,
the live-found "to obtain painting." case, and precision cases (role-phrase
glosses pass, legitimate relative clauses survive, legitimate parentheticals
preserved).

Required suite — each run with exit code:

| Suite | Result | Exit |
|-------|--------|------|
| root `test_local60*/61*/62*` (605, 607, 617, 618×4, 620, 623, 624) | 176 passed | **0** |
| `tests/` `test_local60*/61*/62*` (37 files, 600…622) | 350 passed | **0** |
| `tests/test_lead_double_conclusion.py` + `test_local590_{assembly,orchestrator,pool_store}` | 44 passed | **0** |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | **0** |
| `test_local624_narration_splices.py` (direct + pytest) | 17 passed | **0** |

---

## 5. Live acceptance — own disposable container, 2 stops each, cap $1.00

The suggested venues (**Kunsthalle Bremen**, **Musée des Beaux-Arts de Rouen**)
already exist in `audio_tours` (Bremen id 407; Rouen ids 434/439/442), so per the
"NEVER generated before" rule I used **four** venues verified at count 0.

Build: `run_local624_live.sh` builds `Dockerfile.generator` from the branch tree
(baking the fixes), runs a **disposable** container `local624-gen` (`--rm`,
never an `audioura-*` container) on `development_default`, tour cache OFF, metered
and hard-capped. The live stack's generator service was **not** used. Image and
container removed at the end. Postgres `development-postgres-2-1` was read/insert
only.

| Run (image commit) | Venue | id | Stops | Splice A/B/C | critique.sh | cost |
|--------------------|-------|----|-------|--------------|-------------|------|
| 024211a | Wallraf-Richartz Museum, Cologne | 473 | 2 | **CLEAN / CLEAN / CLEAN** | 3/10 | — |
| 024211a | Nationalmuseum, Stockholm | 475 | 2 | **CLEAN / CLEAN / CLEAN** | 5.5/10 | $0.3808 (run) |
| 2d92a79 | Lenbachhaus, Munich | 478 | 2 | **CLEAN / CLEAN / CLEAN** | 3/10 | — |
| 2d92a79 | Groeningemuseum, Bruges | 480 | 2 | **CLEAN / CLEAN / CLEAN** | 3/10 | $0.3736 (run) |

**Combined cost $0.7544 < $1.00 cap.** `grep` of the delivered spoken text for
appositive person-as-work, dangling/stranded clauses, and empty fields found
**none** on any of the four tours.

The critique scores are honest and are driven entirely by **out-of-scope,
pre-existing** defects owned by other tickets: the labeled "Museum Information:"
block (criterion 3), the 2-stop brevity (criterion 7), institutional
filler/recap-as-conclusion (criteria 1/5/6). **No critique flagged the LOCAL-624
appositive or truncation classes.** (Tour 480's one criterion-8 flag was a
garbled *name*, "Marcel Broodt" → Broodthaers — a different class, out of scope.)

**Extra defect caught live:** tour 473 (built from the first image) shipped
"…to obtain painting." — the degrade had stripped the determiner off the object
("to obtain the Fischer painting" → "to obtain painting"), the **same excision
class** as "that characterized." in a new shape. I added
`_DEGRADE_GUARD_STRANDED_BARE_OBJECT`, re-ran two more fresh venues with the
fixed image (478, 480), and confirmed all classes clean.

**Row accounting:** `audio_tours` — 4 additive `is_test=t` rows written (473,
475, 478, 480). **No deletes.** (Run-1 before=277; run-2 before=282, after=286 —
the extra deltas are concurrent unrelated activity on the shared DB; my four rows
are the only ones I wrote.)

---

## 6. Commits

| SHA | What |
|-----|------|
| 9aa4a65 | deliverables 1+2: type-match gloss guard + truncated-clause safety check |
| 4db5dae | tests with the exact 470 sentences |
| 9b4d6e8 | scan (469/471 + Kunsthaus/Orsay/Thyssen); precision hardening; Class-C empty-parenthetical repair |
| 024211a | isolated live-run harness (own container, fresh venues, $1 cap) |
| 2d92a79 | catch stranded bare object found live (tour 473) |
| 4c90531 | record both live acceptance runs in the harness |

Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
`.continuous_dev/STATUS.md`.
