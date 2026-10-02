# SUBMISSION_LOCAL-431.md

## Task: The story gate has been right and ignored; earn the right to turn it on

---

## 1. Per-stop story_count — MFA Unbound and Palais Lascaris

### MFA Unbound (from committed artifact `mfa_unbound_LOCAL430.txt`, live run)

| Stop | story_count | entities_ok | thesis_ok | verdict |
|------|-------------|-------------|-----------|---------|
| Le Lézard aux plumes d'or | 3 | True | True | ✓ PASS |
| Moses and Monotheism | 1 | True | True | ✗ FAIL |
| Au Soleil du Plafond | 2 | True | True | ✗ FAIL |

**Result: 1/3 stops pass.** Gate is correct — the two failing stops genuinely have
only 1–2 story sentences.

### MFA Unbound (from merged tour file `TOUR_MFA_UNBOUND_394_MERGED.txt`)

| Stop | story_count | entities_ok | thesis_ok | verdict |
|------|-------------|-------------|-----------|---------|
| Le Lézard aux plumes d'or | 1 | True | True | ✗ FAIL |
| Moses and Monotheism | 0 | True | False | ✗ FAIL |
| Au Soleil du Plafond | 0 | True | True | ✗ FAIL |

**Result: 0/3 stops pass.** The merged file differs from the `poi_list` descriptions
the gate checks at runtime (post-assembly rewrites strip some story content).

### Palais Lascaris (from `Palais_Lascaris__Nice__France_museum_tour_20260811_141344.txt`)

| Stop | story_count | entities_ok | thesis_ok | verdict |
|------|-------------|-------------|-----------|---------|
| Harpe by Naderman (1780) | 3 | True | True | ✓ PASS |
| Sacqueboute ténor by Schnitzer (1581) | 0 | True | True | ✗ FAIL |
| Guitar by Torres (1884) | 0 | True | True | ✗ FAIL |
| Basse de violon by Testore (1696) | 0 | True | True | ✗ FAIL |

**Result: 1/4 stops pass** (with the thesis fix for venue_purpose applied).

---

## 2. Diagnosis: WHY the thin stops are thin

**Root cause: the LLM generates evaluative/atmospheric prose instead of story
sentences, even when the prompt explicitly demands stories and the snippet material
supports them.**

Evidence from the committed MFA run:

- **Stop 2 (Moses and Monotheism)**: Beats assigned = `Dalí, Freud, Torf`. The model
  produced "Dalí's signature surrealistic style shines through" — names Dalí but uses
  no story verb. It wrote "invites you to unravel the layers of symbolism" — no person,
  no action. Only one sentence qualified: "In 1939, Sigmund Freud published Moses and
  Monotheism through The Hogarth Press" (person + `published` = story verb).

- **Stop 3 (Au Soleil du Plafond)**: Beats = `Juan Gris, Pierre Reverdy`. The model
  wrote "this work transcends the physical boundaries" (`_NON_STORY_MARKERS` match on
  "transcends") and "invites you to consider" (non-story). Two sentences qualified:
  the Tériade commission and the lithograph outcome.

- **Palais Stops 2–4**: Zero story sentences. Sentences mention "Anton Schnitzer",
  "Antonio de Torres", "Paolo Antonio Testore" but never pair them with a story verb
  (commissioned, founded, established, donated, etc.). All sentences describe the
  instruments atmospherically: "serves as a window to the musical traditions",
  "connects us to a time when music played a central role".

**The pattern:** The prompt's STORY REQUIREMENT section (at line ~2096) is clear and
gives correct examples. The beat injection (LOCAL-383) names the people. But the LLM
sometimes satisfies the beat check (surname present) without constructing a story
sentence (surname + verb + consequence). It falls back to contemplative prose when
snippet material is thin (Stop 2 had only 2/5 tier1/tier2 snippets).

**This is NOT a classifier problem.** The classifier correctly identifies:
- ✗ "Dalí's surrealistic style shines through" → no story verb
- ✗ "transcends the physical boundaries" → non-story marker
- ✓ "Sigmund Freud published Moses and Monotheism through The Hogarth Press" → verb + person + action

---

## 3. Fix: story sentence retry during generation

**What was done:**
- `generate_tour_text.py` ~line 10674: After beat retry, check `extract_story_sentences(description)`.
  If `story_count < 3`, retry with a prompt supplement that explicitly names the failure mode and
  shows the LLM what passes vs fails. Does NOT lower `min_story_sentences` (D376 binding).

- `story_gate.py` `check_thesis_threaded`: `venue_purpose` now passes thesis. The
  `_THESIS_KEYWORDS` are livre-d'artiste-specific and false-failed every non-exhibition
  museum. This does NOT weaken the story_count gate.

- Blocking wiring: `_l421_all_pass` wired into `_LAST_CLEAN_FAIL_EVIDENCE` through
  LOCAL-365's clean-fail path, gated by `L421_GATE_BLOCKS` env var (default: `false`/LOG_ONLY).
  LEAD flips to `true` when a live run passes all stops.

**What was NOT done:**
- `min_story_sentences` was not lowered (remains 3).
- The classifier was not loosened (no new verbs, no new patterns).
- The gate was not turned on (blocking). It cannot pass on current content.

---

## 4. Gate status: NOT YET, here is the gap

| Venue | Pass rate | Gap to blocking |
|-------|-----------|-----------------|
| MFA Unbound | 1/3 (33%) | 2 stops need 1–2 more story sentences each |
| Palais Lascaris | 1/4 (25%) | 3 stops have 0 story sentences (all evaluative) |

**The gate should not block today.** The story retry will improve pass rates on future
runs by giving the LLM a second chance with explicit structural demands. But I cannot
prove it works without a live run, and the task forbids lowering the bar.

**What makes the gate ready to block:**
1. A live MFA run after this merge shows 3/3 passing (the retry triggers for thin stops)
2. A live Palais run shows ≥ 3/4 passing
3. LEAD sets `L421_GATE_BLOCKS=true`

---

## 5. Neutralisation evidence (red output)

### Thesis fix neutralisation

```
=== NEUTRALISATION: venue_purpose pass-through removed ===
verify_stop_story(framing_case="venue_purpose"): passed=False
failures=["thesis_missing: no reference to exhibition's art form (livre d'artiste, artist's book, collaboration, printed work)"]

=== WITH FIX: venue_purpose pass-through active ===
verify_stop_story(framing_case="venue_purpose"): passed=True
failures=[]
```

Neutralising `if framing_case == 'venue_purpose': return True` in `check_thesis_threaded`
causes `test_revert_venue_purpose_breaks_palais` and `test_palais_with_stories_passes_gate`
to fail. Both pass with the fix active.

### Story retry neutralisation

```
Description story_count = 1
Condition: _l431_story_count < 3 → 1 < 3 = True

With retry ACTIVE (if _l431_story_count < 3): triggers retry, model gets second chance
With retry NEUTRALISED (if False and _l431_story_count < 3): skips retry

The gate at line ~11171 reports the same deficit either way:
  gate verdict: passed=False
  failures: ['story_count=1 < 3 minimum (need 2 more story sentences)']
```

The retry changes the generation behavior (gives the LLM a second attempt at story
sentences). Without the retry, the same descriptions that currently fail will continue
to be delivered with < 3 story sentences.

---

## 6. Palais control (D302/D326)

From `Palais_Lascaris__Nice__France_museum_tour_20260811_141344.txt`:

- **4/4 stops**: Harpe (1780), Sacqueboute ténor (1581), Guitar (1884), Basse de violon (1696)
- **Dates intact**: 1780, 1581, 1884, 1696 — all present in stop headers
- **Content lengths**: 2955, 1674, 1339, 1695 chars per stop
- **No content deleted** — the thesis fix only changes the gate's *verdict* on
  Palais stops (from "fail on thesis" to "fail on story_count only"), it does not
  alter any generated content

---

## 7. Test results

```
tests/test_local431_story_gate_enforcement.py: 15 passed
tests/test_local388_story_delivery.py: 19 passed  
tests/test_local383_story_beats.py: 28 passed
tests/test_local420_never_ship_stub.py: 11 passed
tests/test_local422_call_site_binding.py: 8 passed
tests/test_local429_prolog_ordering.py: 3 passed
tests/test_local430_wayback_staleness.py: 13 passed
Total: 97 passed, 0 failed
```
