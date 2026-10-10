# SUBMISSION — LOCAL-660 — Boston walking v7 (Kiro 5): four delivery defects

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-660-walking-v7` (from `subscribed` @ `0e9f0bb8`)
**Base:** subscribed — `git merge-base --is-ancestor 0e9f0bb8 HEAD` → exit 0 (verified)

Tour 557 v7 (Kiro 5/10) shipped the Boston walking tour wrong four ways. Each is
fixed, tested offline, demonstrated on a fresh paid live run with per-defect
detectors, and confirmed by a Kiro listener-critique that rose from **5/10 → 8.5/10**.

Every fix is a **pure, deterministic, idempotent** delivery guard wired into the
`complete_tour` pass chain (each behind a `_l654ck(...)` dump point so
`LOCAL654_DUMP=1` isolates it), and a sibling guard on the final text path.

---

## The four defects, cause, and fix

### Defect 1 — Stop cut mid-sentence ("…the centuries gather and do not let")

**Cause.** `work_first_evidence.repair_truncated_tail` only inspects the **last
sentence of the whole tour** — the conclusion. On 557 the cut was inside the
**Stop 5 narration**, and the conclusion ("Together, these stops reveal…")
followed it, so the final-sentence repair never saw the broken stop. The shared
`_TRUNCATED_TAIL_RE` also had no entry for a bare trailing verb like `let`.

**Fix.** `work_first_evidence.repair_midsentence_truncation(tour_text)` — walks
**every stop body and the conclusion** and, for each prose paragraph whose final
sentence is a fragment (no terminal punctuation, or ends on a token that still
expects a complement), drops the fragment so the cut lands on the previous
sentence boundary. `_TRUNCATED_TAIL_RE` extended with bare verbs / modals /
auxiliaries / conjunctions / prepositions (`let`, `make`, `keep`, `do not`, …).
Field/label lines (`Directions:`, `Address:`…), stop headers and the conclusion
recap are preserved. Wired after `repair_truncated_tail`
(`_l654ck("LOCAL-660 midsentence_truncation")`).

Verified on 557: `…do not let` dropped; Stop 5 now ends on "…dialogue between
past and present."; 5 headers + 4 Directions + conclusion intact; 2nd pass = 0.

### Defect 2 — Garble "The victims were Boston Massacre." + the Massacre told twice

**Cause (garble).** The unglossed-reference **degrade** path excised a reference
phrase from between a copula and a bare entity, leaving `<subject> (was|were|is|
are) <bare ProperNoun>.` Every existing degrade guard passed it (it has a
subject, is > 15 chars, ends on a capitalised word, not a function word) — I
reproduced that `_degrade_sentence_is_wellformed("The victims were Boston
Massacre.")` returned `True`.

**Cause (double-told).** `derepetition_guard.check_cross_stop_fact_repetition`
only reported repeats across **different** stops and silently de-duplicated
within a stop, so the Massacre told twice in Stop 5 (the narration + an inserted
fact sentence) was never flagged.

**Fix.**
* `unglossed_reference_gate`: two degrade guards, **gated behind the degraded
  `entity`** so they fire only on a sentence the gate itself just mangled, never
  on a well-formed predicate nominative. **FIX A** `_degrade_copula_equates_
  entity` rejects `… (was|were|is|are) [the] <that exact entity>.` **FIX B**
  `_DEGRADE_GUARD_COPULA_BARE_ENTITY` rejects the broader copula-on-multi-word-
  bare-proper-noun shape. `_degrade_sentence_is_wellformed(sentence, entity='')`
  now takes the entity; `_degrade_reference_in_text` passes it. Kept legitimate:
  "The author was Shakespeare.", "He was President of the United States.", "The
  capital is Boston.", "Your first stop is Massachusetts State House."
* `derepetition_guard.check_cross_stop_fact_repetition(…, include_within_stop=
  True)` now also reports **within-stop** repeats (`first_stop == repeat_stop`,
  `within_stop: True`), so the existing D533 `strip_repeated_facts` removes the
  intra-stop second telling.

Verified: FIX A/B reject the garble and "The event was the Boston Tea Party.";
within-stop Massacre fixture collapses 2 → 1 telling (the inserted "On King
Street…" sentence dropped, the first telling kept).

### Defect 3 — Dangling pronoun ("His legacy is carved…" in Stop 3)

**Cause.** A LEAD fix (commit `0e9f0bb8`) relocated the sentence that introduced
George Francis Parkman out of Stop 3 and into Stop 1, leaving "His" in Stop 3
with no antecedent. `dangling_demonstrative_gate` handles *demonstratives*
(This/These/That/Those), not personal pronouns.

**Fix.** New module `dangling_pronoun_gate.py` (mirror of the demonstrative
gate). `strip_dangling_pronoun_openers_in_text(tour_text)` drops a narration
sentence that **opens** on He/His/Him/She/Her/Hers/They/Them/Their/Theirs when no
plausible antecedent appears earlier **in the same stop** (title + preceding
sentences). A gendered pronoun needs a *person* (title+name, or a multi-token
capitalised name — with place/style/event spans like "Greek Revival", "Boston
Massacre", "Beacon Street" rejected); a plural pronoun is also satisfied by a
plural common noun ("crowd", "soldiers"). Deletion, not rewriting (a rewrite
would have to assert a referent we do not know). Wired after the removal passes
in the `complete_tour` chain, and alongside the LOCAL-634 demonstrative guard on
the final text path.

Verified on 557: "His legacy is carved…" dropped; "His words did not erase…"
(Hutchinson named earlier) and "He drew over 20,000 people" (Obama named earlier)
both **kept**; 2nd pass = 0.

### Defect 4 — Directions pre-announce the end + echo the theme

**Cause.** The leg into Stop 2 (of 5) said "…marking the end of your walk
exploring Massachusetts politics and current affairs in Boston." The LLM
directions generator has no notion of which leg is last, and a directions line
is a navigation cue, not a place to restate the theme.

**Fix.** `directions_generator`:
* `sanitize_directions_leg(text, is_last_leg, next_name='')` — on a **non-final**
  leg strips end/final clauses (`_DIRECTIONS_END_RE`); on **every** leg strips a
  thematic `<walk/tour> exploring|dedicated to|celebrating|devoted to|focused on
  <theme>` echo (`_DIRECTIONS_THEME_ECHO_RE` — restricted to *thematic*
  connectors so spatial navigation like "walk through the park" / "walk down
  Congress Street" is never touched).
* `sanitize_directions_in_text(tour_text)` — every-path text guard that
  sanitizes each `Directions:` line **by position**; only the second-to-last
  stop's line (the leg into the last stop) may say the walk is ending.

Wired at the transition-assembly site (`is_last_leg = i == len(poi_list) - 2`)
and as a `complete_tour` text pass (`_l654ck("LOCAL-660 directions_final_theme")`).

Verified on 557: only the Stop 1→2 leg changed ("…end of your walk exploring…"
removed, now "…clock tower. It is roughly 400 meters away."); legs 2/3/4
untouched; a last-leg "your final stop" is allowed; idempotent.

---

## Files changed

| file | change |
|---|---|
| `work_first_evidence.py` | `repair_midsentence_truncation` + helpers; `_TRUNCATED_TAIL_RE` extended |
| `unglossed_reference_gate.py` | FIX A/FIX B copula-bare-entity degrade guards (entity-gated) |
| `derepetition_guard.py` | `check_cross_stop_fact_repetition(include_within_stop=True)` |
| `dangling_pronoun_gate.py` | **new** — dangling personal-pronoun opener gate |
| `directions_generator.py` | `sanitize_directions_leg`, `sanitize_directions_in_text` |
| `generate_tour_text.py` | wired all four guards (chain + final text path) |
| `tests/test_local660_walking_v7_defects.py` | **new** — 14 fixture tests |
| `run_local660_container.py`, `run_local660_live.sh` | **new** — isolated live harness |

---

## Tests (offline) — exit codes

New suite `tests/test_local660_walking_v7_defects.py` — **14 passed** (fixtures
reduced from tour 557 v7 for each defect: mid-sentence repair + idempotent +
complete-sentence-untouched; copula garble rejected in degrade / legit predicate
nominatives kept / within-stop Massacre detected and stripped; dangling His
dropped / resolved His kept / plural-with-common-noun kept / idempotent;
directions end+theme stripped on non-final leg / final allowed on last leg /
spatial "walk through" untouched / text-level by-position).

| suite | exit | result |
|---|---|---|
| `tests/test_local660_walking_v7_defects.py` | 0 | 14 passed |
| `tests/test_d533_cross_stop_facts.py` | 0 | ALL TESTS PASSED |
| `tests/test_d534_any_repetition.py` | 0 | ALL TESTS PASSED |
| `tests/test_local269_unglossed_reference_gate.py` | 0 | 28 passed |
| `tests/test_local318_dangling_demonstrative.py` | 0 | 16 passed |
| `test_local646_walking_regressions.py` | 0 | 13 passed |
| `test_local650_walking_route.py` | 0 | 30 passed, 3 skipped |
| `tests/test_local253_directions_mode_guard.py` | 0 | 14 passed |
| `test_local638_directions_between_stops.py` | 0 | 12 passed |
| `tests/test_local658_walking_v4.py` | 0 | 22 passed |
| `tests/test_local614_sentence_splitter_initials.py` | 0 | 6 passed |
| `tests/test_local654_no_midclause_collision.py` | 0 | 8 passed |
| **museum canary** `tests/test_local652_phantom_thread.py` | 0 | 12 passed |
| **museum canary** `tests/test_local611_canary.py` | 0 | 7 passed |
| `tests/test_local616_phantom_cross_reference.py` | 0 | 6 passed |
| `tests/test_local286_museum_prolog_and_dedup.py` | 0 | 31 passed |
| `tests/test_local615_paragraph_dedupe.py` | 0 | 7 passed |

**Pre-existing failures (NOT caused by this work — reproduce on base `0e9f0bb8`):**
`tests/test_local256_fragment_and_label.py::test_r7_does_not_fire_on_factual_sensory`
(1 failed / 27 passed) and
`tests/test_local271_r1_damage_and_exhortation.py::test_take_in_handler_no_double`.
Both live in `style_validator_detector` (R7 orientation / `_take_in_handler`),
which this work does not touch; both fail identically with the base checked out.

---

## Live run (own container; ONE paid tour; cap $1.00)

Built **`local660-gen-img`** from `Dockerfile.generator` on this branch and ran a
disposable container: `docker run --rm --name local660-gen -p 5120:5000
--network development_default`. It joined `development_default` **only** to INSERT
the delivered tour as one additive `is_test` row into `development-postgres-2-1`.
**Never** `docker compose -p audioura`; **never** an `audioura-*` container; tour
cache + stop pool **OFF** (fresh). `./run_local660_live.sh` → `run_local660_container.py`.
Image + container removed on exit.

* **Request:** "Walking tour in Boston dedicated to Massachusetts politics and
  current affairs, Boston, MA" — 5 stops, walking, fresh.
* **Outcome:** DELIVERED — `audio_tours` **id = 645** (`is_test = true`), 12 565
  chars, 5 stops.
* **`audio_tours` count:** BEFORE **442** → AFTER **443** (`is_test` 377 → 378).
  **Additive only. No DELETE.**
* **Spend (this task's run, `live_run_meter` TOTAL): $0.5664** — under the $1.00
  cap. openai $0.3091, gemini_grounding $0.2380, gemini_tokens $0.0183, serper
  $0.0010. (`paid_api_calls` for the container host records $0.4909; the
  gemini_grounding component is metered by `live_run_meter` into `cost_ledger`.)
  ONE paid tour only.

### Per-defect detectors on the delivered tour (all PASS)

```
[PASS] DEFECT1_midsentence:        midsentence_repair_would_fire=0
[PASS] DEFECT2_garble_double:      copula_garble=[]  within_stop_repeats=[]
[PASS] DEFECT3_dangling_pronoun:   dangling_pronoun_openers_would_drop=0
[PASS] DEFECT4_directions_end_theme: nonfinal_leg_violations=[]
[LOCAL-660] ALL FOUR DEFECTS GONE = True
```

### Kiro listener-critique (`.continuous_dev/calib/critique.sh 645 5`) — **8.5/10** (v7 was 5/10)

> "A strong, story-led civic walking tour. … Stories are distinct across stops,
> there is a genuine conclusion, and the restaurant offer is correctly placed as
> the final sentence."

The critique confirms the four v7 defects are gone. It flags three issues that
are **outside the scope of LOCAL-660's four named defects** and are
pre-existing/separate causes:

* **Stop 4 "…Attorney General James T."** — a cut *name* (ends on an initial
  "T.", which is a sentence terminator). This is a different cause from the
  Defect-1 mid-*clause* cut ("…do not let"): the sentence is grammatically
  terminated, and the right remedy is **name repair** (LOCAL-635 territory), not
  dropping the sentence — dropping it would lose real content ("Wendell Phillips
  in 1837 famously seized the stage to condemn Massachusetts Attorney General").
  My Defect-1 guard deliberately does not drop a sentence that ends in valid
  terminal punctuation, to avoid destroying good content.
* **Stop 5 leading `**`** — a stray markdown token leaking into the orientation
  (a markup-strip issue, not one of the four defects).
* **`(Reported by …)` source lists spoken** in the "In recent news" blocks
  (criterion 4) — this is the current-affairs news design (LOCAL-655), unchanged
  by this ticket.

Artifacts saved: `tours/local660_live/{tour_645.txt, critique_645.md,
local660_live.log}`.

---

## Process / safety

* Branched from `subscribed` @ `0e9f0bb8`; `git merge-base --is-ancestor
  0e9f0bb8 HEAD` → 0.
* Committed after each step; `git rev-list --count origin/subscribed..HEAD` ≥ 1
  at every step.
* **No DELETE** (the one new row is additive `is_test`). No GCloud.
* Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
* The news (State House Healey–Minogue debate; City Hall Wu/USPS) and the LEAD
  Parkman-bequest relocation were left untouched, as instructed.
