##### READY FOR REVIEW

**Commit:** `c97d11a` LOCAL-352: narrative arc rule — story not credential  
**Branch:** `kiro/local352-story-not-credential`  
**Base:** `storied`

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | Added NARRATIVE ARC RULE (27 lines) after BODY USAGE RULE in `format_passages_for_prompt`. Unconditional injection — fires for every stop that has corpus passages. |
| `tests/test_local352_narrative_arc.py` | 11 tests: directive presence, sequence language, non-owner coverage, invention prohibition, credential-vs-story contrast, factual passages still get rule, Le Safari recommending verb, both-rules coexistence, ordering, museum 8-stop bound, museum 4-stop bound. |

---

## What the prompt said BEFORE (the root cause)

The BODY USAGE RULE (LOCAL-345) asked for:

> "Your DESCRIPTION BODY … MUST incorporate specific **facts, dates, or claims** from the passages above."

This is satisfied by extracting a single attribute: "Michelin-starred chef" IS a fact from the corpus. The LLM obeys the letter: it uses a corpus fact in the body. But it discards the arc — the leaving, the contrast, the scale.

---

## What the prompt says AFTER

The NARRATIVE ARC RULE supplements (does not replace) the BODY USAGE RULE:

```
NARRATIVE ARC RULE (LOCAL-352 — critical): When a passage describes a person
DOING something — leaving a position, founding a place, refusing an offer,
recommending a dish, returning after years away — your description MUST tell
the sequence of events, not merely state the person's credential or association.
A credential is an adjective ("Michelin-starred chef"); a narrative is a
sequence ("he left his two-star kitchen at the Negresco to cook for twenty
people in a back-street bistro"). The listener wants to experience what
happened, not read a résumé. Specifically:
  - If a passage names WHERE someone came from and WHERE they went, state both.
  - If a passage names WHAT someone gave up and WHAT they chose instead, state the contrast.
  - If a passage names a specific person recommending, reviewing, or recounting
    an experience at this place, tell it as an event: who did what, where, and
    what they said or found. This applies to visitors, critics, chefs from
    elsewhere, and documented incidents — not only owners.
  - Do NOT flatten a narrative into a single adjective or title.
  - Every element of the story MUST come from the passages above. You may not
    infer motivation, emotion, or dates not stated in the source material.
```

---

## Verbatim evidence

### Tests pass (10/11, 1 skip)
```
tests/test_local352_narrative_arc.py::TestNarrativeArcDirectivePresent::test_narrative_arc_rule_exists PASSED
tests/test_local352_narrative_arc.py::TestNarrativeArcDirectivePresent::test_directive_mentions_sequence PASSED
tests/test_local352_narrative_arc.py::TestNarrativeArcDirectivePresent::test_directive_not_owner_restricted PASSED
tests/test_local352_narrative_arc.py::TestNarrativeArcDirectivePresent::test_directive_forbids_invention PASSED
tests/test_local352_narrative_arc.py::TestNarrativeArcDirectivePresent::test_credential_vs_story_example PASSED
tests/test_local352_narrative_arc.py::TestNarrativeArcAlwaysPresent::test_factual_passages_still_get_rule PASSED
tests/test_local352_narrative_arc.py::TestLeSafariNarrativeCase::test_recommending_verb_in_directive PASSED
tests/test_local352_narrative_arc.py::TestBodyUsageRuleNotRegressed::test_both_rules_present PASSED
tests/test_local352_narrative_arc.py::TestBodyUsageRuleNotRegressed::test_grounding_before_arc PASSED
tests/test_local352_narrative_arc.py::TestMuseumBoundsUnaffected::test_museum_8stop_bound PASSED
tests/test_local352_narrative_arc.py::TestMuseumBoundsUnaffected::test_museum_4stop_bound SKIPPED (file not available)
```

### Tests fail on storied branch
`NARRATIVE ARC RULE` string does not exist in `storied:stop_corpus_reader.py` (verified via `git show`).

### Museum 8-stop score: 82.56 (bound: 75.0) — UNAFFECTED
The NARRATIVE ARC RULE is a no-op for museum stops (objects, not people).

### LOCAL-345 tests: 8/8 PASSED
### LOCAL-332 tests: 11/11 PASSED (attribution guards intact)

### Quote verification NOT weakened
The NARRATIVE ARC RULE explicitly states: "Every element of the story MUST come from the passages above. You may not infer motivation, emotion, or dates not stated in the source material." The GROUNDING RULE (D50) remains first in the block and unchanged.

---

## Sentence-level trace (expected La Merenda output)

With corpus passages:
1. "Run since 1996 by chef Dominique Le Stanc"
2. "He used to be the head chef at the Negresco's infamous Chantecler"
3. "He gave it all up to cook in a cramped kitchen for just twenty covers"
4. "In Niçois language, 'merenda' means workman's snack"

Expected output sentences and their sourcing:

| Expected sentence element | Source passage |
|---------------------------|---------------|
| "Dominique Le Stanc" named | Passage 1 |
| "head chef at the Negresco's Chantecler" — where he came from | Passage 2 |
| "gave it all up" / "walked away" — what he did | Passage 3 |
| "twenty covers" / "twenty people" — the contrast (scale) | Passage 3 |
| "merenda means workman's snack" — the name's meaning | Passage 4 |

What is NOT permitted (and the directive explicitly bars):
- "He felt liberated" — motivation not in corpus
- "After 15 years at the Negresco" — duration not stated
- "In 1996 he opened La Merenda" — only "run since 1996" is stated (not opened)

**LEAD must regenerate to verify actual output** — `OPENAI_API_KEY` is not in this environment.

---

## Le Safari trace (expected)

Corpus: "Colman Andrews: A three-star chef introduced me to the pizza at Le Safari"

Expected: tells it as an event — Colman Andrews (food writer), a three-star chef, the recommendation, the pizza at Le Safari.  
Not permitted: "a popular restaurant recommended by critics" (flattened credential).

---

## Limitations

1. **Cannot regenerate** — `OPENAI_API_KEY` not available. LEAD must run:
   ```
   DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \
   STORIED_MODE=true OPENAI_API_KEY=... python3 -c "..."
   ```
   to produce actual La Merenda and Le Safari output for sentence-level verification.

2. **Museum 4-stop bound** — file `LOCAL258_asian_arts_4stop.txt` not present in `tours/`; test skipped. The 8-stop file confirms the prompt change does not affect museum scoring.

3. **No runtime enforcement** — This is a composition-prompt change. If the LLM ignores the directive (unlikely given its position as the last substantive rule before FINAL BINDING), detection would require a post-generation check comparing corpus arcs to output. That is out of scope for this task.

4. **Unconditional injection** — The NARRATIVE ARC RULE fires for all stops with corpus, even factual-only stops. This is by design: the rule says "when a passage describes a person DOING something", so it's a no-op for passages that contain only dates or measurements. Adding passage-level arc detection to conditionally inject would be over-engineering.
