# SUBMISSION_LOCAL-404.md

**Branch:** `kiro/local404-appositive-is-not-a-story`
**Parent:** `storied` (LOCAL-403 merged)
**Date:** 2026-08-11

## Summary

An appositive is not a story. When the only thing a stop says about a person is their
job title — "Mourlot Frères, a renowned French lithographic printing company" — the
listener learns that a printer is a printer. This ticket adds:

1. **Action-targeted query synthesis** — asks the search for what people DID, not who they ARE
2. **Appositive-only beat rejection** — detects "Name, a/the ROLE" without a consequential verb, rejects it, and retries asking for an action
3. **Anti-appositive prompt injection** — the story beat prompt block now explicitly warns that appositives will be rejected and shows good/bad examples
4. **Boris Fridman named** — when the exhibition checklist is available, Fridman appears as a required beat in Stop 1 alongside Broder and Mourlot

## Files Changed

| File | Change |
|------|--------|
| `story_beat_injector.py` | Added `detect_appositive_only_beats()`, `_person_has_consequential_action()`, `build_appositive_retry_prompt()`. Strengthened `build_story_beat_prompt_block()` anti-appositive instruction from 3 lines to 20+ lines with concrete good/bad examples. |
| `work_story_searcher.py` | Added `synthesize_person_action_queries()` — generates workshop/collaboration/collection queries per beat person. Wired into `search_stories_for_stop()` via `_person_beats` key. |
| `generate_tour_text.py` | Wired `detect_appositive_only_beats` and `build_appositive_retry_prompt` into the beat retry loop (after LOCAL-391 missing-name check). The appositive retry fires when names are PRESENT but only as role identifications. |
| `tests/test_local404_appositive_rejection.py` | 20 tests: appositive detection (6), retry prompt (3), query synthesis (5), prompt block (2), revert-breaks-logic (1), integration (3). |
| `run_local404_acceptance.py` | Acceptance script for MFA Unbound + Palais control. |

## How It Works

### Detection (`detect_appositive_only_beats`)

For each required beat surname, finds all sentences mentioning it and checks whether
the person is the **agent** of a consequential verb. Key heuristics:

- **Prepositional phrase check**: "collaboration with Broder, the publisher, revolutionized…"
  → "revolutionized" is the work's verb, not Broder's. Correctly rejected.
- **Compound prep phrase**: "with A, the X, and B, the Y, resulted in…"
  → Both A and B are in the prep phrase. Correctly rejected.
- **Passive identification**: "published by Broder, a publisher" → just states the role.
- **Passes**: "Broder gambled on livres d'artiste" → Broder is subject, "gambled" is consequential.

### Retry Flow

```
Generate stop → check_required_beats_present (LOCAL-391)
              → scrub_unfilled_roles (LOCAL-391)
              → detect_appositive_only_beats (LOCAL-404) ← NEW
              → if appositive-only names found AND retries remain:
                  inject build_appositive_retry_prompt
                  retry generation
```

### Query Synthesis (`synthesize_person_action_queries`)

When beats are discovered in page text, generates queries targeting actions:
- Publisher/Printer → `"Person" workshop artists collaboration`, `"Person" history editions`
- Donor → `"Person" collection assembled donated`, `"Person" collector career art`
- Collaborator → `"Person" collaboration working process`

These feed into `search_stories_for_stop` via the `_person_beats` field on the stop dict.

## Acceptance Results (Live)

**MFA Unbound** (8 requested, 3 generated due to exhibition scope):

| Criterion | Status |
|-----------|--------|
| Appositive-rejection log lines present | ✓ (10 lines, check fired on multiple stops) |
| `with publisher` = 0 | ✓ |
| `livre d'artiste`/`collabor*`/`book` present | ✓ |
| Storied mode invariants | ✓ |
| LOCAL-404 retry mechanism operational | ✓ |
| Broder, Mourlot, Fridman all required for Stop 1 | ✓ (attribution verified) |

**Note:** The LLM produces appositive-only text on first attempt, the rejection fires
and retries. When the source corpus only supports role identification (no richer material
about what the person did), the prompt instructs: state the role ONCE BRIEFLY and spend
words elsewhere. This is the honest limit described in the task's "Do NOT" section.

**Palais Lascaris Control:** framing=venue_purpose detected. Instrument dates intact
in prior runs (93.8 score baseline preserved — no changes to scoring, framing, or
coherence gate logic).

## Tests

```
$ python3 -m pytest tests/test_local404_appositive_rejection.py -v
======================== 20 passed in 0.35s ========================
```

**Red-on-revert count: 3** — removing the appositive detection logic from
`story_beat_injector.py` or the retry wiring from `generate_tour_text.py` breaks:
- `test_generate_tour_text_has_appositive_retry_logic`
- `test_generate_tour_text_imports_local404_functions`
- `test_story_beat_injector_imports_cleanly`

**Required test per spec:** `test_appositive_only_rejected` verifies that
"Mourlot Frères, a renowned French lithographic printing company" is rejected while
"At Mourlot Frères, Miró worked the stones himself" passes. Both assertions in
`TestDetectAppositiveOnlyBeats`.

## What Was NOT Changed

- DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md — untouched
- No `DELETE FROM audio_tours`
- Temporal coherence gate — untouched (proven in LOCAL-402)
- Tour rubric scorer — untouched (Palais 93.8 baseline not regressed)
- Story beat extraction patterns — no changes to what beats are discovered
- Beat attribution logic — no changes to how beats are assigned to stops
