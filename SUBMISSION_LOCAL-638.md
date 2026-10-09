# SUBMISSION — LOCAL-638: Michael's listening notes on Frick tour 523 (D640)

**Branch:** `LOCAL-638-listener-notes` (from `subscribed` @ `841b073`)
**Base:** subscribed — `git merge-base --is-ancestor 841b073 HEAD` exits 0.
**Scope owned:** the opening/About section, transitions, the narration and story-pass
prompts, the editor prompt. **Not touched:** `venue_resolver.py`, `story_miner` (LOCAL-637).

Michael listened to Frick tour 523 (stops 7/8/9), scored it 8/10, and gave four
notes; his words are the spec (STORIED_COMMUNICATION_04.MD, 2026-10-08 21:35). Each
note is implemented as a **deterministic final guarantee on the delivered text**
(so it holds on every path — fresh, pool, cache, by-reference) **plus** the
prompt-level change the note asks for, with a test, and verified live on a fresh
Frick tour.

---

## Note 1 — Location, price, open hours belong in the general description

> "Logical order is broken: it starts telling about the painting, then the museum
> information, how much it costs and when it is open, then goes back to the painting.
> Location, price, open hours should be part of the general description."

In 523 the composed practical-facts sentence (LOCAL-633) sat **inside Stop 1's
Orientation paragraph**. D633/D611 already say practical facts are spoken once, in
the Stop-1 opening section (before the first Orientation); the assembly path renders
them there by design. What was missing was a guarantee that no later pass could leave
a hours/price sentence inside an Orientation or a stop body.

**Code**
- `practical_facts_gate.relocate_practical_facts_to_opening(text)` — moves any spoken
  hours/admission sentence sitting at or after the first Orientation back into the
  Stop-1 opening-section prose (before the first Orientation). Never invents or drops
  a fact; idempotent.
- `practical_facts_gate.count_practical_facts_after_first_orientation(text)` — the
  detector (the number that must be 0).
- Wired as delivery guard **2c-ter** in `generate_tour_text._apply_delivery_hours_guard`.

**Test** `test_local638_practical_facts_opening.py` (10): a 523-defect fixture with
hours+admission inside Stop 1's Orientation → after the guard, **zero** practical
facts after the first Orientation sentence; the facts are present in the opening; the
Orientation keeps its own guidance; a clean tour is unchanged; idempotent.

**Live (tour 528):** the hours/admission sentences
("The museum is open daily except Tuesday. Admission is 30 dollars for adults.")
sit in Stop 1's opening prose, before any Orientation line. Detector = **0**.

---

## Note 2 — No unpaid teaser

> "It ends with 'unexpected details hint at the deeper stories beneath the calm'; I
> wish it says something about these deeper stories."

A stop must not end on an unpaid teaser ("deeper stories", "hint at", "more to
discover", "secrets", "beneath the calm", "waiting to be discovered") unless the stop
told that story. The editor must **deliver or drop**.

**Code**
- `stop_editor` **prompt**: a new instruction to deliver the teased story from the
  stop's own facts, or delete the teaser sentence — never leave an empty promise last.
- `stop_editor.ends_on_unpaid_teaser` / `drop_unpaid_teaser`: detector + deterministic
  trailing-teaser drop. A teaser that pays off in the same sentence (a year, a
  two-word proper name, or a cause/consequence) is kept.
- `edit_stop` drops a surviving teaser on every return path (accepted edit, rejected
  edit, empty LLM output) — removing a sentence introduces no new claim, so no
  claim_check re-validation is needed.
- `stop_editor.strip_unpaid_teaser_in_text`: conclusion-aware text-level guard for the
  cache/pool/by-reference paths (editor disabled there), wired as delivery guard **3a**.

**Test** `test_local638_no_unpaid_teaser.py` (13): detector, drop, prompt, text-level
guard, and both `edit_stop` paths; the exact 523 phrase is dropped; a paid consequence
is kept; idempotent.

**Live (tour 528):** no stop ends on a teaser. Detector = **0**. The independent
critique raised no teaser defect.

---

## Note 3 — Consequence of a pivotal decision, linked back to the work

> "It would have been 9 or 10 if it told the consequences of such a decision and how
> the painting reflects that." (More refused to acknowledge Henry VIII as head of the
> Church; the consequence — his execution in 1535 — is in any source.)

When a stop narrates a pivotal decision or event (a refusal, a theft, a war, an exile,
a death sentence), the narration contract (LOCAL-617) and the story pass (LOCAL-490)
must ask for its **consequence** and the **link back to the work**, grounded in the
stop's sources (claim/G4 still validates).

**Code**
- `work_first_evidence.narration_contract_instruction` — new clause **(e)**: if the
  work depicts/commemorates a pivotal decision/event, state its consequence (the
  named outcome, the fate, the year) and how the work reflects/foreshadows it, ONLY
  from the reference material, never invented.
- `story_pass.build_story_prompt` — a pivotal-event block: when part 2 is a pivotal
  act, part 3 (the consequence) is not optional and not vague; name the outcome and
  link it to the object; consequence taken only from the sources.

**Test** `test_local638_pivotal_consequence.py` (7): both prompts carry the pivotal
vocabulary, the consequence + link-to-work requirement, and the source-only grounding;
the story prompt's existing story-only, source-bounded contract is intact.

**Thomas More — before and after**

Before (523, as Michael heard it): the portrait is described; the stop narrates that
More refused to recognise Henry VIII as head of the Church, and **stops there** — no
consequence, no link from that fate back to the painting.

After (live tour 528, Stop 1, verbatim):

> "Holbein painted More while navigating the intricate social and political landscape
> of Tudor England, at a time when More was residing in Chelsea, London. The portrait
> not only emphasizes More's prominence in society but also foreshadows the internal
> conflict he would face when his conscience clashed with his duty to the king,
> **leading to his eventual execution in 1535**. This juxtaposition of duty and
> conscience is subtly captured in the calm yet contemplative expression on More's
> face."

The consequence (execution in 1535) is stated, and it is linked back to the work (the
calm expression read against that fate) — grounded in the Frick's own material.

---

## Note 4 — Directions to the next exhibit on every stop but the last

> "The story stops abruptly and has no directions to the next exhibit." (In 523, Stop 2
> had no "Your final stop…" transition before Stop 3.)

Both base paths attach a transition for every stop except the last. A later pass (the
editor, a dedupe/era/opener guard, or the conclusion rebuild) can drop it. The fix is a
final guarantee that re-adds any missing hand-off.

**Code**
- `directions_guarantee.ensure_directions_between_stops(text, venue)` — appends a
  deterministic museum hand-off ("Your final stop in <venue>: <next>." for the
  penultimate stop, else "Continue to <next>.") to any non-last stop whose body carries
  no transition. Never touches the last stop or the conclusion/Sources tail; idempotent.
- `directions_guarantee.count_stops_missing_directions(text, venue)` — the detector.
- Wired as delivery guard **3b**, before the conclusion rebuild (so the conclusion sees
  finalized bodies), on every path.

**Test** `test_local638_directions_between_stops.py` (12): a 523-defect fixture (Stop 2
missing its hand-off) → after the guard, **zero** stops missing directions; the last
stop is never given one; existing hand-offs are preserved; a `Directions:`-labelled line
counts; clean tour unchanged; idempotent.

**Live (tour 528):** the delivery log shows
`[LOCAL-638 Note 4] added directions to 1 stop(s) that ended with no hand-off` — the
exact 523 defect, corrected on the live path. Final text: Stop 1 → "Continue through
The Frick Collection — next is Portrait of Comtesse d'Haussonville."; Stop 2 → "Your
final stop in The Frick Collection: Officer and Laughing Girl."; Stop 3 (last) has none.
Detector = **0**.

---

## Note 5 — Tests (each exit code)

```
python3 -m pytest test_local60*.py        -> 0   (38 passed)
python3 -m pytest test_local61*.py        -> 0   (80 passed)
python3 -m pytest test_local62*.py        -> 0   (178 passed)
python3 -m pytest test_local63*.py        -> 0   (130 passed, incl. 43 new LOCAL-638)
python3 -m pytest tests/test_local63*.py  -> 0   (16 passed)
python3 -m pytest tests/test_lead_*.py    -> 0   (5 passed)
python3 -m pytest test_local590_*.py      -> 0   (42 passed)
python3 test_sq4_merge.py                 -> 0   (ALL TESTS PASSED)

python3 -m pytest test_local638_*.py      -> 0   (43 passed)
```

Pre-existing caveat (not caused by LOCAL-638, not in the globs above):
`tests/test_local597_by_reference.py::...::test_empty_pool_refuses` fails only under
batched test-ordering; it passes in isolation and reproduces on the clean base
`841b073` (verified via `git stash`). It is a by_reference test-state/ordering issue.

---

## Note 6 — Live (own container, cache + pool off)

One fresh tour of **The Frick Collection, 3 stops**, in a disposable container
`local638-gen` (`docker run --rm`, spare port 5098, network `development_default`,
DB `development-postgres-2-1`), cache OFF + pool OFF, **HARD CAP $1.00** enforced by
`tests/live_run_meter.py` across all providers with a reserve gate. One tour only.

- **Tour id:** 528 (`is_test = true`). Delivered 3 stops, 5591 chars.
- **Cost:** meter TOTAL **$0.7357** (openai $0.5834 + gemini_grounding $0.0700 +
  gemini_tokens $0.0343 + serper $0.0480 + preflight $0.0454); ledger tour_total
  $0.7810 — both under the $1.00 cap.
- **Row counts (additive is_test only, no DELETE):** `audio_tours` **333 → 334**;
  is_test rows **270 → 271**.

**Detectors on the delivered spoken text (tour 528):**
```
Note 1  practical facts after first Orientation = 0     PASS
Note 2  stops ending on an unpaid teaser        = 0     PASS
Note 3  Thomas More consequence (execution 1535)= True  PASS
Note 4  stops missing directions                = 0     PASS
```

**Opening section (Stop 1 start):** leads with the work and artist, then the practical
facts in the general description — "…The cord in the upper right corner … denotes
More's deep spiritual convictions. **The museum is open daily except Tuesday. Admission
is 30 dollars for adults.**"

**End of each stop:**
- Stop 1 → "Directions: Continue through The Frick Collection — next is Portrait of
  Comtesse d'Haussonville."
- Stop 2 → "Your final stop in The Frick Collection: Officer and Laughing Girl." *(added
  by the Note-4 guard — Stop 2 had ended abruptly, as in 523)*
- Stop 3 (last) → ends on the thematic conclusion; no hand-off (correct).

**Thomas More stop in full:** see `submission_artifacts/local638_live/tour_528_full.txt`
(Stop 1 quoted under Note 3 above).

**critique.sh (independent kiro-cli listener review): 7/10.** It confirms the four
notes are resolved: narration leads with work+artist, **hours and admission are
spoken**, no teaser, the More consequence is present, no abrupt ending. The remaining
flagged defects are **out of scope** for LOCAL-638 and owned by other LOCALs — a
garbled Vermeer clause ("crafted. van Berckenrode.", sentence-stitch, LOCAL-635),
institutional-filler provenance (LOCAL-617/story-type), and a conclusion that omits
Vermeer (LOCAL-619).

Artifacts: `submission_artifacts/local638_live/` (full tour, spoken text, detectors,
critique) and `submission_artifacts/local638/test_exit_codes.txt`.

---

## Files changed

- `practical_facts_gate.py` — Note 1 relocate guarantee + detector.
- `directions_guarantee.py` *(new)* — Note 4 guarantee + detector.
- `stop_editor.py` — Note 2 prompt + teaser detector/drop + text-level guard.
- `work_first_evidence.py` — Note 3 narration-contract clause (e).
- `story_pass.py` — Note 3 pivotal-event consequence block.
- `generate_tour_text.py` — wiring of guards 2c-ter (Note 1), 3a (Note 2), 3b (Note 4)
  into the single delivery chokepoint `_apply_delivery_hours_guard`.
- Tests: `test_local638_practical_facts_opening.py`, `test_local638_no_unpaid_teaser.py`,
  `test_local638_pivotal_consequence.py`, `test_local638_directions_between_stops.py`.
- Harness: `run_local638_container.py`, `run_local638_live.sh`.
- Artifacts under `submission_artifacts/local638/` and `submission_artifacts/local638_live/`.

Per process: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md and
.continuous_dev/STATUS.md were not edited.
