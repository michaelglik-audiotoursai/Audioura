# SUBMISSION — LOCAL-543: the evidence file already says it knows nothing, and nobody reads it

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-543-evidence-carries-no-sourcing`
**Base:** `storied` = `43d407e` (verified: `git merge-base --is-ancestor 43d407e HEAD` exits 0)

---

## What the task asked, and what shape the work turned out to be

`TOURS_FOR_REVIEW/round9/CHURCH_1_evidence.json` is 379 bytes. For all four stops
it says the same thing — "not in discovered landmarks" — and that is the entire
evidentiary record behind a tour that tells a listener, in a confident voice, that
Mother Teresa visited this church in June 1995 and healed a paralyzed parishioner.
The evidence file records *landmark discovery status*. It does not record where a
single sentence of the narrative came from.

The task's first instruction was to read `story_leads.py` and **report which this
is**: is per-claim provenance something that already exists and is being discarded
(a plumbing job), or something that has to be generated (a much bigger job)?

**Answer: it is BOTH, split by class, and that split is the honest finding of this
task.**

- **`grounded` provenance already exists and is discarded.**
  `story_leads.gemini_with_sources` (D508) already returns per-sentence attribution:
  its `out['supports']` is a list of `{'text': source_sentence, 'sources':
  [{domain,url}]}` — Gemini telling us which sentence came from which page. The
  module's own docstring says the metadata "was present on every one and being
  thrown away." So grounded sourcing is a plumbing problem.
- **BUT the plumbing does not currently reach the point where a whole tour is
  assembled.** `gemini_with_sources`' `supports` are consumed inside story
  retrieval and are not retained per-sentence all the way to the finished
  `complete_tour`. I did NOT fabricate a retention path I could not prove end to
  end; I wired the auditor to accept `grounded_supports` (so the plumbing has a
  socket the moment those supports are threaded through) and, for this task,
  passed `grounded_supports=None` and said so plainly. That is why the live run
  below reports **0 grounded** even though it paid for 9 grounding requests — an
  honest gap, reported, not papered over.
- **`corpus` provenance also already exists and is discarded.** The generation path
  collects retrieval snippets per stop in `_DIRECT_SNIPPETS_PER_STOP`, each carrying
  a `link`/`domain`/`source`, and `provenance_gloss.provenance_names` already knows
  the names a stop's own record documents (LOCAL-494: "a name from the record IS its
  source"). Both are available at assembly time and both were uncounted.
- **`parametric` is the class that was invisible, and it is the majority.** Whatever
  a retrieved passage does not carry, the model said from memory.

So the work is mostly plumbing what exists (corpus now, grounded when its supports
are threaded through) plus **counting the residue** — the parametric sentences — for
the first time. It is not a grounding/verification task and it makes no grounded
call of its own: it answers the cheaper, prior question, "did we have ANY source for
this sentence?"

---

## What changed

### 1. `claim_provenance.py` (new) — per-claim sourcing

- Splits a tour into **factual narrative sentences** (reusing `sentence_split`),
  excluding field lines (Address/Coordinates/…), directions, the title, the epilog
  recap, pure navigation ("head towards the altar") and tour meta-narration ("you'll
  learn about…"). A sentence counts as factual only if it carries a year, a month, a
  named entity, or a number.
- Classifies each into `corpus` / `grounded` / `parametric` against a `SourcePool`
  built from what the pipeline already collects:
  `snippets_per_stop` (`_DIRECT_SNIPPETS_PER_STOP`), `grounded_supports`
  (`gemini_with_sources` output), `provenance_names` (documented record names).
  An internal marker like `replenishment_rationale` is explicitly **not** a source.
- With an **empty pool** (auditing a saved tour that captured nothing) every factual
  sentence is `parametric` — the honest reading.
- `audit_tour(text, pool)` returns `counts` (`sourced`/`unsourced`/`total` and the
  three classes), `per_stop`, and a per-claim `claims` list.
- Runnable standalone: `python3 claim_provenance.py <tour.txt>`.

### 2. `tour_quality.py` — the `unsourced_person_event` defect

The worst shape, flagged specifically: **a named person + placed at THIS venue + a
specific date + no source.** That is the Mother Teresa sentence exactly, and the
"Founded in 1868 by St. Mary Help of Christians" / "Gustave Eiffel's iconic Control
Tower" shape too.

- `_find_unsourced_person_events(text, provenance=None)` requires all three
  ingredients **in one sentence** (D577 — the finding is the whole quotable
  sentence): a named person (reusing the existing `_PERSON`/possessive/appositive
  machinery and the `_NOT_A_NAME`/`_NOT_PERSON` vocabularies, so it cannot drift
  from the people-counter), a specific date (a 4-digit year or a month name — not a
  vague era), and a placement (a venue/structure word or a placement verb). Tour
  meta-narration ("At the upcoming stops, you'll learn about…") is excluded.
- Added to `REQUIRED_CLEAN`, so it fails a tour.
- `score_tour` gained a `provenance` parameter (mirroring the existing
  `verify_attribution` callback): when given `claim_provenance`'s classifier bound to
  the run's pool, a sentence a source carries (`corpus`/`grounded`) is **cleared**,
  and only a `parametric` one fires. Offline, with no pool, the shape itself is the
  finding — which is honest for a tour whose only evidence is a 379-byte record.

### 3. `generate_tour_text.py` — record it and print it

- After the `Grounding:` / `Tour total:` cost lines, a new **`Provenance:`** line
  prints `X/Y factual sentences sourced, Z unsourced (a corpus, b grounded, c
  parametric)` — where anyone looking at a run will see it.
- The `*_evidence.json` writer now emits
  `{"landmarks": <old per-stop status>, "claim_provenance": {counts, per_stop,
  claims}}`. When there are no discovered landmarks (the common church/airport case
  that produced the empty CHURCH_1 file), it still writes the provenance block.
- The counts are folded into `_LAST_GENERATION_COST["provenance"]` so a run driver
  reads them without parsing the log.

### 4. Tests — `tests/test_local543_claim_provenance.py`

19 tests, all passing: the five classification paths; the offline audit of the real
`round9/CHURCH_1.txt` (every factual sentence unsourced, Mother Teresa among them);
the defect firing on the real file and being `REQUIRED_CLEAN`; the provenance
classifier clearing a sourced sentence; false-positive guards (person-only,
date-only, meta-preview); and the 48-file survey asserted structurally.

---

## Acceptance

### Live run (the live-artifact hard gate, `remind_Services_ai.md`)

Real venue **Our Lady Help of Christians Catholic Church, Newton MA**, museum, 4
stops — the same one that produced CHURCH_1. Driver: `run_local543_live.py`.
Artifacts committed under `LOCAL543_live/`.

```
Total API cost: $0.2334 (39706 tokens)
Grounding:      $0.3150 (9 requests)
Tour total:     $0.5484
Provenance:     4/29 factual sentences sourced, 25 unsourced (4 corpus, 0 grounded, 25 parametric)
```

- **The number, stated plainly even though it is bad: 25 of 29 factual sentences in
  a freshly generated tour had no source.** Nothing was tuned to improve it.
- `unsourced_person_event` **fired** on the live tour.
- The new evidence file `LOCAL543_live/CHURCH_1_live_evidence.json` is **10,201
  bytes** (vs the original 379) and carries per-claim sourcing for all 29 sentences,
  a per-stop breakdown, and names exactly which 4 sentences had a source.
- **0 grounded** despite 9 grounding requests: as explained above, per-sentence
  grounded `supports` are not retained to the assembly point, so I passed
  `grounded_supports=None` rather than invent a retention path. The 4 `corpus`
  sentences are `knowledge_fallback:gemini` snippets — retrieved lore that carries a
  source marker. That marker names a model provider, so it is weaker than a web URL;
  I classify it `corpus` because it is a captured retrieval passage with a source
  field, and the field is recorded verbatim in the evidence so the reader can judge
  it. Network failures: 0. Wall: 234.8s.

### `unsourced_person_event` fires on the existing round9 CHURCH_1.txt

```
2 unsourced person-event(s); "Teresa" placed here in June with no source:
"In June 1995, the church became the site of an extraordinary moment when Mother Teresa,
 renowned for her humanitarian work, made an unexpected visit."
```

(The second event is Rev. Walter H. Cuenin, placed at the altar "in late 2002" with
no source — the same shape.)

### False-positive survey — all 48 tour files (LOCAL-536/537/539 format)

Offline (no captured pool), a person+date+venue sentence is unsourced **by
construction** — the saved files carry no provenance — so a high hit rate is the
measurement, not a false alarm. The survey's job is to prove the detector fires ONLY
on genuine person+date+venue sentences.

**Result: 44/48 files fire, 102 events, 0 structural false positives.** Every
flagged sentence, in every file, genuinely contains a named person, a specific date,
and a venue/placement cue (asserted in `test_every_flagged_sentence_has_person_date_and_venue`).

| n | file | first event |
|---|------|-------------|
| 3 | CHURCH_tour_1.txt | Bernard \| 1984 |
| 4 | CHURCH_tour_2.txt | Bernard Law \| 2002 |
| 4 | CHURCH_tour_3.txt | Teresa \| June |
| 1 | LOGAN_handoff_1.txt | Gustave Eiffel \| 1887 |
| 1 | LOGAN_storyfirst_1.txt | Gustave Eiffel \| 1887 |
| 1 | LOGAN_tour_1.txt | Gustave Eiffel \| 1887 |
| 1 | LOGAN_tour_2.txt | Gustave Eiffel \| 1887 |
| **0** | **LOGAN_tour_3.txt** | — (no named people) |
| 2 | buckets/CHURCH_4stops.txt | Bernard Law \| December |
| 2 | buckets/CHURCH_6stops.txt | Bernard Law \| December |
| 2 | buckets/CHURCH_6stops_v2.txt | Walter H. Cuenin \| 1984 |
| 2 | round2/CHURCH_1.txt | Walter H. Cuenin \| 2002 |
| 3 | round2/CHURCH_2.txt | Pius \| 1911 |
| 4 | round2/CHURCH_3.txt | Teresa \| June |
| 1 | round2/LOGAN_1.txt | Gustave Eiffel \| 1887 |
| 1 | round2/LOGAN_2.txt | Gustave Eiffel \| 1887 |
| 1 | round2/LOGAN_3.txt | Gustave Eiffel \| 1887 |
| 2 | round3/CHURCH_1.txt | Cuenin \| 2005 |
| 1 | round3/CHURCH_2.txt | Walter H. Cuenin \| December |
| 2 | round3/CHURCH_3.txt | Walter H. Cuenin \| 2002 |
| **0** | **round3/LOGAN_1.txt** | — (people named only in tenure/biographical context) |
| **0** | **round3/LOGAN_2.txt** | — |
| 1 | round3/LOGAN_3.txt | Gustave Eiffel \| 1887 |
| 3 | round4/LOGAN_1.txt | General Edward Lawrence \| April |
| 1 | round4/LOGAN_2.txt | Gustave Eiffel \| 1887 |
| 2 | round4/LOGAN_3.txt | Gustave Eiffel \| 1887 |
| 4 | round5/CHURCH_1.txt | Mother Teresa \| June |
| 2 | round5/CHURCH_2.txt | Bernard \| 2002 |
| 2 | round5/CHURCH_3.txt | Teresa \| 1995 |
| 1 | round5/LOGAN_1.txt | Channing H. Cox \| 1922 |
| **0** | **round5/LOGAN_2.txt** | — |
| 2 | round5/LOGAN_3.txt | Gustave Eiffel \| 1887 |
| 5 | round6/CHURCH_1.txt | Cuenin \| December |
| 2 | round6/CHURCH_2.txt | Reverend Cuenin \| September |
| 5 | round6/CHURCH_3.txt | Walter Cuenin \| December |
| 2 | round6/LOGAN_1.txt | Gustave Eiffel \| 1887 |
| 2 | round6/LOGAN_2.txt | James Michael Curley \| March |
| 4 | round6/LOGAN_3.txt | Richard Cushing \| 1952 |
| 1 | round7/CHURCH_1.txt | James Murphy \| 1881 |
| 4 | round7/CHURCH_2.txt | Walter H. Cuenin \| December |
| 3 | round7/CHURCH_3.txt | Cuenin \| 1984 |
| 1 | round7/LOGAN_1.txt | Gustave Eiffel \| 1887 |
| 1 | round7/LOGAN_2.txt | Gustave Eiffel \| 1887 |
| 1 | round7/LOGAN_3.txt | Mohamed Atta \| September |
| 4 | round8/CHURCH_1.txt | Monsignor Capik \| 1868 |
| 5 | round8/LOGAN_1.txt | Gustave Eiffel \| 1887 |
| 2 | round9/CHURCH_1.txt | Teresa \| June |
| 4 | round9/LOGAN_1.txt | Edward Lawrence Logan \| 1943 |

The 4 non-firing files are true negatives: `LOGAN_tour_3` names no people at all; the
three `LOGAN` files name people only in a tenure/biographical frame ("Governor from
1921 to 1925") with no dated placement AT the venue — precisely the sentences that
should not be flagged.

Note this survey re-flags the very defects earlier tasks fixed one surface form at a
time — "Gustave Eiffel's Control Tower" (LOCAL-527/539), "Founded in 1868 by St. Mary
Help of Christians" (LOCAL-527) — but now under one honest question: *was there a
source?* Every one of them had none.

---

## Scope honoured

- **No claim was verified against the world.** No grounded call is made by any code
  in this change; the module counts sources, it does not check truth. The LOCAL-534
  claim about Mother Teresa's real June-1995 New Bedford visit is treated as a claim,
  not built upon.
- **Nothing was tuned to make the number look better.** 25/29 unsourced on the live
  run is reported as-is.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
  `.continuous_dev/STATUS.md`, or any tour file (they are evidence).

## Files

- `claim_provenance.py` (new)
- `tour_quality.py` (defect + `provenance` param + `REQUIRED_CLEAN`)
- `generate_tour_text.py` (Provenance cost line + evidence-file provenance + cost record)
- `tests/test_local543_claim_provenance.py` (new, 19 tests)
- `run_local543_live.py` (new, live driver)
- `LOCAL543_live/CHURCH_1_live.txt`, `LOCAL543_live/CHURCH_1_live_evidence.json`,
  `LOCAL543_live/LOCAL543_live_result.json` (live artifacts)

## Verification

- `python3 -m pytest tests/test_local543_claim_provenance.py` → 19 passed.
- Combined regression with the neighbouring gates
  (536/539/527/d585/530/537) → 107 passed.
- All three touched modules byte-compile and import.
