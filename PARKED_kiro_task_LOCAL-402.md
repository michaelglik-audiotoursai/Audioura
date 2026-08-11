# LOCAL-402 (PARKED — dispatch ONLY if LOCAL-401 fails to deliver stories) — Skip the pipeline, feed the snippets

## When to use this

**Only if LOCAL-401's live run still shows `beats_in_delivered_text=0`.** If 401
works, discard this task.

## Why it exists

Three rounds have now tried to deliver a story through the SQ pipeline:

| round | outcome |
|---|---|
| 397 | search wired; 18 results; 0 stories delivered |
| 400 | instrumented; located two failing hops; 0 stories delivered |
| 401 | fixing extraction + injection |

The pipeline is `search → extract elements → score → select → inject beats →
prose`. That is five stages, and D329 found two of them failing independently on
the same run. **Each stage is another place a story can die silently**, and the
listener does not care whether a fact arrived as a scored "element".

## The alternative

Skip the middle. Put the retrieved material in front of the writer directly:

- Take the top N search results for the stop (title + snippet + URL), already
  available from `search_stories_for_stop()` — it returns 14–23 per stop today.
- Put them in the stop prompt verbatim, as **reference material with sources**,
  under an instruction to write one grounded story about a named person and what
  they did, citing nothing the material does not support.
- Let the **existing gates** do the validation they already do well: person
  grounding (with the story corpus added, from 397), form-claim, numeric, and the
  coherence check from 401. The corpus for grounding is the snippet set.

This trades a structured element model for fewer failure points. The gates are the
safety net and they are already proven — `Rousseau`, `Corbusier`, `Lalanne`,
`Matisse` and `Chagall` have all stayed at zero for many rounds.

## What must still hold

Everything from D291–D329: correct exhibition, correct works, correct stop count,
correct artist per stop, `livre d'artiste` framing, `book` framing, zero fabricated
persons, zero form fabrications, zero impossible relations (no "collaboration
between Dalí and Freud" — Freud d.1939, illustrations 1974), no prompt bleed, no
stop ever dropped (D317).

## Acceptance

Same as LOCAL-401: every stop with ≥1 story sentence naming a person and something
they did that is not visible; `Broder`/`Mourlot`/`Fridman` in stop 1; the chain
line per stop (`serp_results` and `beats_in_delivered_text` at minimum); control
case Palais 4/4 with live base score reported.

**Report the trade honestly:** if this path delivers stories where the pipeline
could not, say so plainly — that is a finding about the architecture, not a
workaround to hide.

## PROCESS
- Branch `kiro/local402-snippets-direct` off whichever of 400/401 last carried the
  working search wiring.
- Write `SUBMISSION_LOCAL-402.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
