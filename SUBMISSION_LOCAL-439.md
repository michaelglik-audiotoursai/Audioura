# SUBMISSION_LOCAL-439.md

## Task: LOCAL-439 — the gate judges stories, not sentences; a cheap LLM judges, not a verb list

### What changed

1. **Unit of evaluation is the STORY, not the sentence (D394).** The per-sentence tally
   (`story_count`) is removed. New per-stop requirement: at least one verified story-unit
   of ≥3 sentences. `classify_story_unit(text) -> dict` at module scope in `story_gate.py`.

2. **Classification is an AI question, not a verb list (D394 addendum).**
   `classify_story_unit(text)` calls gpt-4o-mini (temperature=0), one call per candidate
   story-unit, never per sentence. Verdict cached by SHA-256 of text. Regex pre-filter
   survives only for obvious non-prose (headings, empty strings).

3. **Interest scoring, additive with ranged axes (third addendum).**
   `score_story_interest(text) -> dict` at module scope. Trust 0–5 (from provenance
   weights, NOT asked of LLM), emotional content 0–4, new-information 0–3 (from same
   gpt-4o-mini call as classification), deduction 0–2. Wired into
   `story_selection.score_story_quality()`.

4. **Defects retired:**
   - `entities_blurred`: applies to STOP TEXT as a whole, not per story-unit. Donor
     names not demanded (a story dropping "Fridman" for concision is correct).
   - Exhibition thesis keyword list: removed. Exhibition framing is handled implicitly
     by the LLM rubric (a story about a livre d'artiste IS the thesis threading).
     venue_purpose framing retains the LOCAL-432 lighter check.

---

### Acceptance fixtures (live gpt-4o-mini verdicts, 2026-08-12)

#### Fixture 1: PASS — Michael's 3-sentence Miró story

```
Text: "In 1967, Joan Miró completed a full set of lithographs for Le Lézard, but the
entire edition was destroyed because a chemical reaction caused the inks to bleed into
the paper. Miró recreated the work on new plates, while printers spent years perfecting
the paper chemistry to prevent further degradation. The final 1971 masterpiece stands as
a symbol of artistic and printmaking resilience following the scrapped original attempt."

Result:
  is_story: True
  reason: "The text describes Joan Miró's actions in creating and recreating his work,
           presenting a clear arc of struggle with the chemical reaction and resolution
           with the final masterpiece."
  emotional_content: 3
  new_information: 2
  deduction: 0
  cost_usd: $0.000093
```

#### Fixture 2: FAIL — atmospheric filler (zero story-units)

```
Text: "The collection serves as a window to the musical traditions of 18th-century Nice.
It connects us to a time when music played a central role in both sacred and secular life.
It invites you to consider how these instruments shaped the cultural identity of the region."

Result:
  is_story: False
  reason: "The text does not contain a named person, real actions, or an arc; it is purely
           atmospheric and evaluative."
  emotional_content: 0
  new_information: 2
  deduction: 1
  cost_usd: $0.000082
```

#### Fixture 3: Deduction FIRES — telling visitors what to feel

```
Text: "This experimental work forces visitors to look closely at how art lives in the
margins. It proves to visitors that an 'unbound' artist's book is a living laboratory.
The unconventional binding technique challenges traditional bookmaking assumptions."

Result:
  is_story: False
  reason: "The text does not contain a named person, real actions, or an arc; it consists
           of evaluative statements about the artwork."
  emotional_content: 0
  new_information: 1
  deduction: 2 ← fires for "forces visitors to" and "proves to visitors that"
  cost_usd: $0.000082
```

#### Fixture 4: Deduction does NOT fire — characterizes the work

```
Text: (same as Fixture 1 — "The final 1971 masterpiece stands as a symbol of artistic
and printmaking resilience")

Result:
  deduction: 0 ← "stands as a symbol of resilience" characterizes the WORK, not the visitor
  from_cache: True (same text → cache hit, no re-ask)
```

---

### Neutralisation proof (red output per function)

```
Neutralised classify_story_unit → always True:
  classify_story_unit(atmospheric) = is_story:True
  Expected False by test, got True → test_classify_not_always_true FAILS ✓

Neutralised classify_story_unit → always False:
  classify_story_unit(miro) = is_story:False
  Expected True by test, got False → test_classify_not_always_false FAILS ✓

Neutralised verify_stop_story → always pass:
  verify_stop_story(atmospheric) = passed:True
  Expected False by test, got True → test_verify_not_always_pass FAILS ✓

Neutralised score_story_interest → constant scores:
  miro.emotional=2, atmospheric.emotional=2 (both same)
  → test_score_interest_not_constant FAILS ✓

Neutralised deduction → always 0:
  classify(deduction_text).deduction = 0
  Expected >0 by test, got 0 → test_deduction_not_always_zero FAILS ✓
```

---

### Live acceptance runs

**Gate mode:** `STORIED_MODE=true`, `L421_GATE_BLOCKS=false` (informational)
**Environment:** `DISABLE_TOUR_CACHE=1`

#### MFA Unbound (3 stops)

```
  ✗ The Daughters of Edward Darley Boit: story_units=0
  ✓ Abraham Sacrificing His Son Isaac: story_units=1
      interest: emotional=3, new_info=2, deduction=1, total=4
  ✗ Anne, Lady de la Pole: story_units=0

  Story gate: 1/3 stops passed
  Classification cost: $0.002795 (input=11,499 tokens, output=1,783 tokens)
```

#### Palais Lascaris (4 stops) — D385 variance

**Run 1:**
```
  Stops selected: Raquel (XVIe siècle), Basse de violon (Testore, 1696),
                  Guitar (Torres, 1884), Guitare baroque (Tesler, 1618)
  ✗ Raquel: story_units=0
  ✗ Basse de violon: story_units=0
  ✗ Guitar: story_units=0
  ✓ Guitare baroque: story_units=1
      interest: emotional=2, new_info=2, deduction=0, total=4

  Story gate: 1/4 stops passed
  Classification cost: $0.004080 (input=16,594 tokens, output=2,652 tokens)
  Dates found: 1618, 1696, 1802, 1884, 1942
  Expected dates present: 1696 (1/4)
  Missing: 1581, 1652, 1780
```

**Run 2 (rerun per D385 instructions):**
```
  Same stops selected (D385 variance — Phase 3 picks different stops)
  ✗ Raquel: story_units=0
  ✗ Basse de violon: story_units=0
  ✗ Guitar: story_units=0
  ✗ Guitare baroque: story_units=0

  Story gate: 0/4 stops passed
  Classification cost: $0.005465
  Dates found: 1600, 1618, 1650, 1696, 1802, 1884, 1904, 1942
  Expected dates present: 1696 (1/4)
  Missing: 1581, 1652, 1780
```

**Palais control (D302/D326):** Phase 3 selected different stops in both runs. The
expected stops (Harpe 1780, Violes gambe 1652, Sacqueboute 1581, Basse violon 1696) were
not selected. Only the 1696 date appears (via Basse de violon by Testore). This is D385
variance in stop selection, not a regression from LOCAL-439 — the gate changes do not
affect Phase 3's stop picker.

---

### Classification cost

Per-tour classification cost (gpt-4o-mini, temperature=0):

| Tour | Input tokens | Output tokens | Cost |
|------|-------------|---------------|------|
| MFA Unbound (3 stops) | 11,499 | 1,783 | $0.002795 |
| Palais Lascaris (4 stops) | 16,594 | 2,652 | $0.004080 |

**Per-stop average:** ~$0.001/stop (well within budget for classification-only calls).

For reference: the acceptance fixture classification (3 calls) cost $0.000258 total.

---

### Test results

```
tests/test_local439_story_gate.py: 31 passed
tests/test_local438_story_selection.py: 19 passed (scores updated for new formula)
```

### LOCAL-431 test breakage (expected, D394)

3 tests in `test_local431_story_gate_enforcement.py` assert `story_count >= 3` — the
per-sentence tally that D394 explicitly removes ("removed, not patched"). Under D394,
`story_count` now means "number of story-units" (0 or 1 per stop). The stops PASS
correctly (the `assertTrue(result['passed'])` assertions succeed); only the follow-up
check of the old metric fails:

```
FAILED test_good_stop_passes_at_3: 1 not >= 3 (1 story-unit found, not 3 story-sentences)
FAILED test_mfa_tour_file_counts: total story_count across stops < expected
FAILED test_palais_tour_file_counts: same
```

These are the exact assertions D394 supersedes. The 12 other LOCAL-431 tests pass.
