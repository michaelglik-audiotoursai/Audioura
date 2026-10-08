# SUBMISSION — LOCAL-620: Story-type balance and per-listener tuning (D634)

**Branch:** `LOCAL-620-story-types-prefs` (from `subscribed` @ `b920b5f`, LOCAL-619B merged)
**Ruling:** Michael, D634 (2026-10-07) — *"I would not dismiss outright museum and
donor sentences in favour of the exhibit, and let some be used to determine the
user preferences. I complained because these were the only stories in that museum
and very little about the paintings themselves."* Plus: stop likes/dislikes should
tune the next tour's story types.

The old LOCAL-617 behaviour was a **hard cap** — at most one institutional
sentence per stop, the own-acquisition one, everything else dropped. That silenced
the real collector/museum **stories** Michael wants kept. This ticket replaces the
cap with a **balance policy**, keeps real collector stories as a legitimate type,
tags every delivered segment with its class, and tunes generation to a listener's
learned preferences.

---

## 1. Story types → preference classes (the mapping)

`story_type_classes.py` is the single bridge between the two taxonomies already in
the codebase — the LOCAL-617 per-sentence story TYPE
(`work_first_evidence.classify_sentence` → work / artist / reception / emotion /
institutional / other) and the three swipe-engine preference CLASSES
(`three_class_retrieval` + `stop_metrics` + `user_class_prefs`: details / historic
/ social). No third vocabulary was invented.

| Story type (LOCAL-617) | Preference class | Why |
|---|---|---|
| `work` | **details** | what the object physically is / shows — material, technique, composition, colour, the depicted figures |
| `artist` | **historic** | the maker's life placed in time (the moment of making) |
| `reception` | **social** | what a named critic/historian/contemporary said |
| `emotion` | **social** | the felt, human reading |
| `institutional` → **real collector/museum story** | **historic** or **social** | a named person + motive/consequence. Social when the point is the collector/patron and their motive; historic when it is the chain of ownership / when it entered the collection |
| `institutional` → **boilerplate** | *(filtered — no class)* | renovation budgets, square metres, opening hours, bare founding date, mission prose — not a story, never a preference signal |
| `other` | *(no class)* | carries no preference signal |

The split of `institutional` is the heart of D634: a collector/donor sentence that
is a **real story** (`is_real_collector_story` — a named person AND a motive or a
consequence) counts as a legitimate type; pure boilerplate
(`is_boilerplate_institutional`) stays filtered. A **bare transfer of title**
("acquired by the museum in 1905") is neither — it carries no signal.

Entry points: `map_story_type_to_class`, `classify_sentence_class`,
`classify_segment_class`, `paragraph_class_distribution`, `stop_class_vector`.
Pure, deterministic, unit-tested.

---

## 2. Balance policy (replaces the hard cap)

`story_balance.py`. On the delivered stop body and on the evidence snippets:

* **the work and its meaning lead** — every work/artist/reception/emotion sentence
  is kept, never dropped;
* **real collector/museum stories are kept**, up to **~25%** of a stop's
  sentences, and **more when the work's own evidence is thin** (relaxed to up to
  half — a true collector story is better than nothing);
* **pure boilerplate and bare transfers of title are dropped**;
* **a stop is never emptied** (D577): if trimming would leave nothing, the body is
  returned unchanged (then the collector stories *are* the stop).

`ensure_tour_class_coverage` reports, across the tour, whether every class
(details/historic/social) appears in at least one stop **when the evidence
allows** — so preferences can be learned for all three. It measures; it never
fabricates a class a stop's evidence does not contain.

Wired into both generation call sites in `generate_tour_text.py` in place of the
LOCAL-617 filters (`balance_snippets_work_first` for evidence,
`balance_tour_text_work_first` for the delivered body). The legacy
`work_first_evidence` functions are **left intact** so the LOCAL-617 tests still
pass unchanged.

---

## 3. Every delivered segment is tagged with its class

`icon_evaluator.py` now tags each delivered paragraph **deterministically** from
its sentences (story type → preference class via `story_type_classes`), and the
stop-level `class_dist` is the i-con-weighted distribution of those deterministic
per-paragraph classes. Each paragraph also carries a `story_class` tag. These are
what get persisted to `stop_metrics.class_details/historic/social` (the existing
columns) and the `paragraphs` jsonb — so the app's swipes/likes map to the right
class. The LLM `class_dist` is retained only as a fallback for a paragraph with no
deterministic signal. Grounded in the delivered text; cannot drift at runtime.

---

## 4. Per-listener tuning at generation

`story_prefs.py`, behind env **`STORY_PREFS`** (default **on** locally;
`STORY_PREFS=0` disables and generation behaves exactly as before).

When `user_class_prefs` exists for the user, `load_user_class_weights` turns the
learned vector into **exploration-floored class weights**: every class keeps at
least **10%** (`MIN_EXPLORATION`), the preferred class gets more, and **no class is
ever excluded** — the same bias-not-filter rule as
`swipe_preference_service.bias_stop_ordering`. `narration_pref_addendum` appends a
short block to the per-stop narration contract that nudges toward the preferred
classes while reminding the model to keep every class and never invent to fill a
quota. Cold start / no prefs / disabled → balanced default, no addendum.

Wired into the museum narration-contract injection in `generate_tour_text.py`
(loaded once per tour).

---

## 5. Carry-overs found while reviewing LOCAL-619B

* **6a — Institutional theme (Lille, tour 463).** When the SQ-S6b discovered theme
  reads institutional (`work_first_evidence.is_institutional_theme`, now extended
  to catch renovation/building/museum-technique framings like *"evolution of
  museum techniques and renovations"*), it is **discarded** so the deterministic
  common-element thread is used for the conclusion. (`generate_tour_text.py`
  `_concl_theme` guard + regex extension in `work_first_evidence.py`.)
* **6b — Unclosed quote.** `tour_conclusion.balance_quotes` closes an unbalanced
  example quote and puts the sentence's period **after** the closing quote (the
  live `Dürer's "Ritter, Tod und Teufel.` defect). Applied in `build_conclusion`;
  idempotent; handles straight and curly quotes.
* **6c — Orphan paragraph (Städel, tour 462).** `drop_orphan_work_paragraphs`
  removes a one-sentence paragraph after the last stop that names a work **not**
  among the delivered stops (the stray *"Hieronymus Bosch's 'Ecce Homo' was
  created around 1476."*). A one-liner naming a **delivered** work is kept. Wired
  into `_split_tail`.

---

## 6. Tests

New `test_local620_story_types_prefs.py` — **27 passed**, pure/offline. Covers:
mapping (incl. real-collector-story vs boilerplate vs bare transfer); balance on
rich vs thin fixtures (collector stories fill when thin; boilerplate + transfer
dropped; never empties; coverage reported, gaps not faked); class tags written
(deterministic per-paragraph / per-stop vector); the prefs-weighted mix shifts
while every class keeps ≥10% (incl. a social-seeded persona and the `STORY_PREFS`
gate); and the three carry-overs (6a detect/spare, 6b close+idempotent, 6c
drop/keep-delivered).

Required regression set (exits):

```
test_local617_work_first ............ 47 passed
tests/test_local619_real_conclusion . 21 passed
test_local620_story_types_prefs ..... 27 passed
tests/test_local60* ................. 165 passed
tests/test_local61* ................. 164 passed
test_local618_* (4 files) ........... 33 passed
test_local590_* (3 files) ........... 42 passed
test_sq4_merge.py ................... ALL TESTS PASSED  (script via __main__)
```

---

## 7. Live, isolated, metered run

`run_local620_live.sh` → `run_local620_container.py`. Disposable container
`local620-gen` (`docker run --rm`; NEVER an `audioura-*` service; joins
`development_default` only to INSERT additive `is_test` rows and seed ONE unique
test user). Fresh tours (cache off). **Combined cost $0.9654 — cap $2.50.**

Two venues, each generated twice — PASS A no-prefs (cold start), PASS B as a
social-seeded test user (`local620_social_1791443698`, `pref_social=0.857`,
`swipe_count=10`):

| id | venue | pass | stops | prefs log | critique |
|---|---|---|---|---|---|
| 464 | McMullen Museum of Art | A no-prefs | 5 | `default/balanced (no user_id)` | **5.5/10** |
| 465 | McMullen Museum of Art | B social-seeded | 5 | `personalised … mix details 26% / historic 28% / social 46% (>=10% floor each)` | **4/10** |
| 466 | Musée des Beaux-Arts de Lille | A no-prefs | 3 | `default/balanced (no user_id)` | **4/10** |
| 467 | Musée des Beaux-Arts de Lille | B social-seeded | 4 | `personalised … 26 / 28 / 46 (>=10% floor each)` | **5.5/10** |

**Class mix per stop** was printed for all four (see
`submission_artifacts/local620/class_mix_per_stop.txt`), e.g. Lille PASS B:

```
Stop 1  details 1.00 / historic 0.00 / social 0.00  (details)
Stop 2  details 0.57 / historic 0.14 / social 0.29  (details)
Stop 3  details 0.25 / historic 0.25 / social 0.50  (social)
Stop 4  details 0.67 / historic 0.00 / social 0.33  (details)
tour coverage: present=[details,historic,social] missing=[] covered=True
```

Coverage was honestly reported, not faked: McMullen PASS A came back
`missing=['historic']` (`covered=False`) — the harness reports the gap rather than
inventing a historic sentence.

### What the independent critic confirmed (D634 intent realised)

The real collector/provenance **stories** the hard cap used to silence now survive
and read as welcome story (the critic flags only dry filler, not these):

* **El Greco's wartime evacuation** (Lille) — a named provenance story kept;
* **Maurice Masson, the collector** (Lille) — a named collector + motive +
  consequence kept;
* **Alex Matter's 2002 hoard** (McMullen *Pollock Matters*) — a named-person
  discovery story kept.

All four conclusions shipped with **balanced quotes** (6b in the wild — El Greco's
and Caravaggio's titles closed with the period after), **no institutional theme**,
the **restaurant offer last**, and the **count correct**.

### Residual defects — honestly out of scope

The critic (demanding, as intended) also found defects LOCAL-620 does **not** own
and did not fix:

* **Cross-stop story / motif repetition.** The balance policy *keeps* collector
  stories but does not dedupe them across stops, so Masson recurs (Lille Stops 1,
  2, conclusion) and a "museum transformation" motif recurs (Lille 467 Stops
  1–3). Cross-stop story/motif dedup is a separate concern (S27/D533 territory).
* **Unspoken hours/admission; "check the website" / "weren't published" fallback.**
  Pre-existing LOCAL-616/618 practical-facts behaviour.
* **Dropped-subject template sentences** ("In this painting, stands with dignified
  composure…"; "gifted to the museum and Michael N."). A pre-existing
  template-interpolation bug, not introduced here.
* **Lille PASS A critic-counted 4 stops vs delivered "3".** A glued-header /
  late-gate count defect (LOCAL-617/619 territory): `count_delivered_stops` saw 3,
  the critic read a glued header as a 4th. The conclusion count matched the
  delivered count; the discrepancy is the pre-existing glued-header issue, not a
  LOCAL-620 regression.

These are recorded rather than papered over. The LOCAL-620 deliverables — mapping,
balance policy, class tags, per-listener tuning, and the three carry-over fixes —
all worked in the live run.

---

## Files

New: `story_type_classes.py`, `story_balance.py`, `story_prefs.py`,
`test_local620_story_types_prefs.py`, `run_local620_container.py`,
`run_local620_live.sh`, `submission_artifacts/local620/*`.

Changed: `generate_tour_text.py` (balance wiring at both call sites; prefs addendum;
6a theme guard), `icon_evaluator.py` (deterministic class tags),
`tour_conclusion.py` (6b `balance_quotes`, 6c `drop_orphan_work_paragraphs`),
`work_first_evidence.py` (extended `_INSTITUTIONAL_THEME_RE` for 6a).

Not edited (per process): DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md,
.continuous_dev/STATUS.md.
