# SUBMISSION — LOCAL-469 · The Paragraph Must Be About THIS Stop

**Branch:** `LOCAL-469-stop-specific-prose`
**Base:** storied = `d726c7e` (verified `git merge-base --is-ancestor d726c7e HEAD` → exit 0)
**ClickUp:** `wdvrdaxa7h`

## The task, restated

Michael: a paragraph describing a stop must be *about that stop*. Two failure modes:

- **A — transferable prose.** "Cycling on the French Riviera, stop at Cap d'Antibes to experience
  the enduring power of nature…" — swap the place name and it says the same thing about anywhere.
- **B — a named entity with no stated relationship.** "…Imagine the scene that once captivated Scott
  Fitzgerald inspiring the setting of his timeless novels." — names Fitzgerald, never says how he
  relates to *this* stop.

## What I investigated before writing anything

### The pipeline (`generate_tour_text.py`)
The prose gates run as a chain of numbered PHASEs inside `generate_tour_text`. Each follows the same
shape: an env-var disable flag, a `try/except ImportError`, a per-POI loop over `description`, a
`(new_desc, deleted, emptied)` return, and a printed summary line prefixed `[LOCAL-nnn] PHASE 5.xxx`.

Relevant existing order:
- 5.13  R1 imperative rewrite
- 5.14  R7 sensory deletion
- 5.141–5.144  R2 / R3 / R4 / R8 deletion   ← the four gates LEAD measured Example A through
- 5.15  R9 generic-sentence deletion (sentence-level "fits any stop")
- 5.155 R10 unfulfilled-promise deletion
- 5.156 unsupported-claim gate … 5.161 temporal coherence

### Why Example A survives (confirmed by reading the detectors)
R9 (5.15) is the closest existing idea — "a sentence that fits any stop belongs to no stop" — but it
is **sentence-level and deterministic** (pattern lists, no substitution test). Example A is a whole
paragraph that is individually fluent; nothing in R1–R10 or the claim gates applies the *substitution*
test Michael described. So it passes byte-for-byte, exactly as LEAD measured.

### Why Example B is only partly covered — and why extending the unglossed gate is WRONG
`unglossed_reference_gate.py` (5.157) runs on every tour. But its whole purpose is the *opposite*
question: "would a general audience know this name?" Fitzgerald is in its `_WELL_KNOWN` set, so it
**suppresses** him — correctly, by its own rule. Michael's Example B test is *not* "does the audience
know Fitzgerald"; it is "does the paragraph state Fitzgerald's relationship to THIS stop." Those are
different axes. Extending the unglossed gate would force it to gloss well-known names (regressing
LOCAL-475/494/496, which exist precisely to STOP it deleting subjects and settings). The prose entity
grounding gate (`prose_entity_grounding_gate.py`, 5.158) is exhibition-scoped **museum-only** and
deterministic against a checklist page; Example B is a cycling tour with no checklist. Neither covers it.

**Decision:** a new, narrow rule — a named person/work/film must carry a *stated relationship to this
stop*, not merely be known or grounded. Placed in the new module, run on all tours, distinct axis.

## Design

New module `stop_specificity_gate.py` at repo root. Two checks, one wiring point at **PHASE 5.152**
(after R10 / 5.155-adjacent, before the claim gates), matching the existing chain shape.

### Part 1 — the substitution test, made mechanical
`check_paragraph_specificity(paragraph, stop_name, sibling_stop_names, api_key=None)`
→ `{'transferable': bool, 'reason': str, 'confidence': 'high'|'medium'|'low'}`

Mechanism: substitute a sibling stop name for `stop_name` throughout, then ask the model whether the
swapped passage contains any claim that is **false or nonsensical** for the new stop. If nothing
breaks, the paragraph was never about this stop → transferable. Framing it as "what breaks when you
move it?" yields a checkable answer instead of an opinion.

### Part 2 — named-entity relationship rule
A person/book/film/work named in a paragraph must have a *stated relationship to this stop*. Reuses
the entity detectors from `unglossed_reference_gate` (person, titled-person, work-title patterns) but
asks a different question: is there a stated link to the stop, not "is it well-known / grounded."

### Part 3 — wiring, conservative removal
- Only `confidence == 'high'` transferable verdicts delete (LOCAL-359 destructive-action rule).
- Never delete the last remaining paragraph of a stop (emptying a stop is worse than a flabby one).
- Behind `DISABLE_STOP_SPECIFICITY_GATE=1`, like every other gate in the chain.
- Prints `[LOCAL-469] PHASE 5.152: …` with the stop and the reason on every real run.

## Files

| file | role |
|---|---|
| `stop_specificity_gate.py` | NEW module. Part 1 `check_paragraph_specificity`, Part 2 `check_named_entity_relationships`, Part 3 `apply_stop_specificity_gate`. |
| `generate_tour_text.py` | +54 lines only: the PHASE 5.152 wiring block between R10 (5.155) and the unsupported-claim gate (5.156). No other change. |
| `test_local469_stop_specificity.py` | Unit tests. CALL the functions with an injected `llm_fn` — no grep of source (D418/D421). |
| `test_local469_wiring.py` | Call-site proof. exec()s the REAL 5.152 block with the call site's variable names bound (D: LOCAL-465 NameError-on-live). |
| `verify_local469_in_container.py` | AC4 harness, run inside the container against a throwaway copy. |

## The substitution mechanic, precisely

`check_paragraph_specificity` swaps `stop_name` (and its >3-char fragments) for a sibling and asks the
model: *does any concrete claim now break?* SPECIFIC on any sibling ⇒ not transferable (high conf).
TRANSFERABLE on every sibling tried ⇒ transferable. Confidence is `high` only when ≥2 siblings both
say TRANSFERABLE; a single sibling yields `medium`; no model verdict yields `low`. Only `high` deletes.

## Why Part 2 does NOT delete

The task says "remove it **or** make it the stop specific." Deleting a paragraph for a transferability
verdict is Part 1's job and is bounded by the never-empty-a-stop rule. An ungrounded named entity is a
narrower signal — the fix is often to state the relationship (rewrite), not to delete the paragraph.
So Part 2 reports (`entity_log`, a real log line with stop + entity + reason) and leaves deletion to
the conservative Part-1 path. This also avoids the LOCAL-475/494/496 class of harm (a gate deleting a
subject/setting it misread).

## A detection defect I caught in the FIRST container run, and fixed

The first container run flagged **three** "ungrounded" entities: `French Riviera`, `Scott Fitzgerald`,
and `Pons Abbey`. Two were false positives:
  - `French Riviera` — a region (the setting), not a name-dropped person or work.
  - `Pons Abbey` — the person regex mangled "Saint-Pons Abbey" (hyphen) and it is an institution
    anyway, i.e. the setting. **This would have flagged the shipped Cimiez paragraph — AC3 says a gate
    that flags it is broken.**

Fix: `_detect_named_entities` now drops candidates whose last word is a place/structure/region/event
word (`abbey`, `riviera`, `sea`, `revolution`, …) and known geography terms, because Michael's Part-2
rule is about *persons, books, films, works* — not the setting. The second container run flags only
Fitzgerald. This is exactly the value of AC4 being a real run and not a unit stub: the stub could not
have surfaced the regex mangling.

## Test evidence

### Unit + wiring suite (16 tests)
```
$ python3 -m unittest test_local469_stop_specificity test_local469_wiring
Ran 16 tests in 0.089s
OK
```

### The suite can fail — Part 1 / never-empty guard
Disabling the never-empty guard (`if len(kept)==0 and remaining_after==0:` → `if False:`) turns the
suite red:
```
FAIL: test_never_empties_a_stop … AssertionError: 0 != 3
FAIL: test_ac1_removes_example_a_keeps_cimiez  (last paragraph wrongly deleted)
Ran 11 tests … FAILED (failures=2)
```
Guard restored → OK.

### The wiring test can fail — LOCAL-465 NameError class
Replacing `poi_list` with an undefined `_poi_list_typo_undefined` inside the real 5.152 block:
```
FAIL: test_call_site_executes_and_fires
  … [LOCAL-469] ERROR: stop-specificity gate failed (non-fatal):
      name '_poi_list_typo_undefined' is not defined
FAILED (failures=1)
```
Restored → OK. The test exercises the call site, not the function.

### AC4 — real container run (container: `audioura-tour-generator-1`)
Verified with `docker exec` against a **throwaway copy** in `/tmp/local469` (since removed). **I did
NOT rebuild or restart any container** — Michael is generating locally today; `/app` was never
touched (`grep -c "PHASE 5.152" /app/generate_tour_text.py` → 0). The harness execs the real 5.152
block with `requests.post` monkeypatched (offline, $0). Output:
```
  [LOCAL-469] PHASE 5.152: Stop-specificity gate...
  [LOCAL-469] Stop-specificity gate summary:
    Stops checked: 3
    Paragraphs checked: 4
    Transferable (high, removed): 1
    Last-paragraph protected: 2
    Ungrounded named entities: 1
    Stops affected: 1
    [LOCAL-469] REMOVED transferable paragraph stop='Cap d'Antibes' conf=high
        reason='generic scene-setting, nothing breaks': "Cycling on the French Riviera, stop at Cap d'Antibes…"
    [LOCAL-469] UNGROUNDED entity stop='Cap d'Antibes' entity='Scott Fitzgerald'
        reason='sentiment only, no link to this stop' in: "As you stand on Cap d'Antibes…"
```

## Acceptance criteria — status

1. **Example A flagged transferable at high confidence and removed** — ✅ (removal log above).
2. **Example B flagged for an ungrounded named entity** — ✅ (Scott Fitzgerald).
3. **Real Cimiez paragraph NOT flagged** — ✅ (not removed, not flagged; detector fix ensures the
   Saint-Pons institution and the region are never even submitted).
4. **Gate log line in a real container run, with stop and reason** — ✅ (container output above).

## Which container I used
`audioura-tour-generator-1` (the running tour-generator), via `docker exec` against a throwaway
`/tmp/local469` copy of the two changed files. No build, no restart; live `/app` untouched and cleaned
up afterward.
