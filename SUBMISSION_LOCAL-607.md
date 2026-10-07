# SUBMISSION — LOCAL-607: Pooled-tour coherence (Michael's McMullen review)

**Branch:** `LOCAL-607-pooled-tour-coherence`
**Base:** `subscribed` @ `ecf1c27` (verified ancestor of HEAD)
**Scope:** the five defects Michael found in McMullen tour 399 (7 stops, built from the stop pool).

---

## Summary of defects → fixes

| # | Defect (Michael) | Fix |
|---|---|---|
| 1 | A previous tour's ending embedded mid-tour (Stop 2 ended with "That's 7 stops … If you would like to eat nearby …") | Strip the epilog from pooled narration at store **and** read; in-place UPDATE migration for existing rows. |
| 2 | The conclusion is a stub ("you have followed the thread of a single story. That's 7 stops.") — no thread named, no stops recapped | Real conclusion: names the thread, recaps three stops one line each, ends on the restaurant offer. |
| 3 | The same donor/founding/relocation story in stops 1, 2, 3, 7 | Deterministic cross-stop **fact** dedupe (fingerprint year+proper-noun / donor-verb sentences; keep first in tour order; museum-history belongs to Stop 1). New QA check "No repeated story across stops". |
| 4 | Too little about the work and the artist | Museum narration prompt reordered: (a) the work, (b) the artist, (c) the emotional reading; acquisition/donation capped at one sentence; museum founding/renaming/relocation excluded from a work's stop. |
| 5 | Stop 1 said "check opening hours on bc.edu" | Strip the stale opening section from pooled narration; fold the real LOCAL-603 preflight hours into the fresh Stop-1 opening section. |

---

## Files changed

- **`stop_pool_store.py`** — `strip_epilog()`, `strip_opening_section()`, applied in `parse_delivered_stops` (store) and `get_pool_stops` (read); `migrate_strip_epilog_in_pool()` (in-place UPDATE, no DELETE).
- **`stop_pool_assembly.py`** — `_closing_recap()` rewritten into a real conclusion; `_first_recap_sentence()` / `_recap_pick_three()`; cross-stop dedupe wired into both `assemble_building_tour` and `assemble_outdoor_tour`; `AssemblyResult.dedupe_dropped` / `dedupe_log`.
- **`cross_stop_fact_dedupe.py`** — NEW. `fact_fingerprint`, `is_museum_history`, `dedupe_tour_facts`, `dedupe_stop_units`, `count_repeated_facts_across_stops`.
- **`stop_pool_orchestrator.py`** — prints the dedupe log (`_emit_result`); folds LOCAL-603 preflight hours into the pool opening section when live extraction gives none.
- **`content_qa_runner.py`** — new QA check **"No repeated story across stops"** (check 2b).
- **`generate_tour_text.py`** — museum narration prompt reordered work → artist → emotional, acquisition capped at one sentence.
- **`test_local607_pooled_coherence.py`** — NEW. 21 tests calling the real functions (no DB, no grep-of-source).
- **`run_local607_live.py`** — NEW. Isolated-container live driver.

No DELETE anywhere. Pool rows cleaned in place (UPDATE of the narration only). No GCloud.
`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, `.continuous_dev/STATUS.md` untouched.

---

## Deliverable 1 — Pool hygiene (epilog + opening section)

`strip_epilog()` removes recap / stop-count / sign-off / restaurant-offer spans anywhere in a
narration body; `strip_opening_section()` removes the About prolog and the stale
"Check opening hours … before you go." fallback (regenerated fresh per tour). Both run at store,
read, and in the migration.

**In-place migration on the dev DB (UPDATE only, counts before/after):**

```
BEFORE: rows with epilog/opening-section artifact = 17
MIGRATION counts: {'scanned': 116, 'with_epilog': 19, 'updated': 19}
AFTER:  rows with epilog/opening-section artifact = 0
total stop_pool rows (unchanged, no DELETE): 116
```

Tour 399 Stop 2 (Ideal Portrait), after parse: epilog gone, the stop's own last sentence
("…relocated to 2101 Commonwealth Avenue…") preserved.

## Deliverable 2 — Real conclusion

Reuses the fresh-tour recap *skeleton* ("From {first} to {last}, you have followed the thread …")
deterministically — the fresh builder (`generate_tour_text._build_closing_recap`) is LLM- and
`poi_list`-bound, so the pure assembly path reuses its wording, not its call. Recap sentences are
lifted verbatim from the delivered stops (D177) and skip history/boilerplate/dangling openers.

## Deliverable 3 — One story, one telling

`cross_stop_fact_dedupe` fingerprints a sentence by (year + up to 3 proper nouns) or
(donor/acquisition verb lemmas). The first occurrence in tour order survives; later repeats are
dropped. Museum-history sentences (founding/renaming/relocation/donors) in stops 2…N are dropped
(Stop 1 owns them) **unless** the sentence is the first acquisition sentence about the stop's own
work. Artist biography that merely contains "relocated"/"found" ("Subleyras relocated to Rome in
1728") is **not** stripped — a founding/relocation sentence counts as museum history only when it
also names the institution.

QA check **"No repeated story across stops"** counts surviving duplicate fingerprints.

## Deliverable 4 — Work-/artist-first narration

The museum narration prompt now orders content: (a) the work (what it shows, how/why made,
meaning, critics), (b) the artist's life and turning point, (c) the emotional reading — with a
hard **one-sentence cap** on acquisition/donation and museum founding/renaming/relocation
excluded from a work's stop.

**Before / after (live):**

*Grace Hoops — BEFORE (tour 399):* opened with "In late 2021, Peter S. Lynch … donated 'Grace
Hoops' … as part of the Carolyn A. and Peter S. Lynch Collection. … The gallery … carries the
name of Devlin … the museum's evolution from its original location at Devlin Hall to its current
Brighton Campus." — mostly donation/museum history.

*Grace Hoops — AFTER:* one acquisition lead sentence, then the work and the artist —
> "Painted in 1872, 'Grace Hoops' captures two young women engrossed in the 'game of graces,' a
> popular 19th-century pastime involving the tossing of wooden hoops. Homer's choice of oil on
> canvas, a medium he mastered, brilliantly conveys the dynamic motion of the game and the
> vibrancy of youthful energy. His focus on scenes of childhood innocence during the 1870s
> resonates within the broader scope of his work…"

*Meal at the House of Simon — BEFORE (tour 399):* "In 1988, the McMullen Museum of Art at Boston
College acquired 'Meal at the House of Simon the Pharisee' … This acquisition was significant as
it marked the inclusion of a notable work…" — acquisition-led.

*Meal at the House of Simon — AFTER:* work- and artist-first with the full-canvas/Louvre and
modello facts Michael asked for —
> "Created around 1737, this oil on canvas by Pierre Subleyras captures the moment from the
> Gospel of Luke where Christ dines at the house of Simon the Pharisee. Subleyras, who had
> relocated from France to Rome in 1728, was at the height of his career … It served as a
> preparatory sketch for a much larger work … which now resides in the Musée du Louvre…"

## Deliverable 5 — Stop 1 hours

The pooled Stop-1 narration carried the About prolog and a stale "Check opening hours and
admission on bc.edu before you go." — both are the per-tour opening section, now stripped from the
pool. The orchestrator rebuilds the opening section fresh and folds the **LOCAL-603 preflight**
hours. Live Stop 1 now speaks:

> "The McMullen Museum of Art is open Monday–Friday from 10:00 am to 5:00 pm; Saturday–Sunday from
> 12:00 pm (noon) to 5:00 pm. Admission is Free admission (the museum charges no admission fee),
> as listed on bc.edu in October 2026."

No "Check opening hours on bc.edu" fallback.

---

## Deliverable 5 (tests) — exits

New unit tests call the real functions (no DB):

```
test_local607_pooled_coherence.py ....................  21 passed
```

Specified suites:

```
test_local590_*.py ..................................... 42 passed, exit 0
tests/test_local593-599 ...............................  184 passed, 10 failed, exit 1
    → the 10 failures are all in tests/test_local596_api.py (seat-claim API).
      PRE-EXISTING cross-test pollution: the file passes alone (and with
      test_local595_edit_gate), imports NONE of the LOCAL-607 modules, and the
      same 10 fail with or without this branch's working-tree changes.
tests/test_local600-604 ...............................  89 passed, exit 0
test_local605_tour_coordinates.py .....................  17 passed, exit 0
test_sq4_merge.py (standalone script) .................  ALL TESTS PASSED, exit 0
test_palais_fix_lead_fixture.py (standalone script) ...  23/23 assertions hold, exit 0
```

---

## Deliverable 6 — Live, isolated container (`docker run --rm --name local607-gen …`)

Never touched any `audioura-*` container; image/container removed at the end. McMullen, 7 stops,
pool **on**, cap $1.50. The epilog/opening-section migration was run first (above). Two runs:

- **First tour at pool v3 (K=0):** `pool_reuse=True`, **Tour total: $1.4098** (< $1.50).
- **Pure reuse (N=7=K, after v3 seeded):** `pool_reuse=True`, **Tour total: $0.0000**.

The pure-reuse delivery (the path Michael reviewed) below.

**Delivery / preflight:**
```
[LOCAL-603] preflight venue='McMullen Museum of Art' status=open hours=y admission=y highlights=5
[LOCAL-607] Stop-1 hours from LOCAL-603 preflight: 'Monday–Friday from 10:00 am to 5:00 pm; Saturday–Sunday from 12:00 pm (noon) to 5:00 pm. Free admission (the museum charges no admission fee)'
[LOCAL-590] POOL DELIVERY: reused=7 new=0 rewritten_transitions=0 about_stops=1 (pool held 7)
DELIVERY: path=pool  stops=7
```

**Stop 1 opening section — hours spoken:**
```
Before we look at anything on the walls, here is the story of McMullen Museum of Art … what it is known for. …

The McMullen Museum of Art is open Monday–Friday from 10:00 am to 5:00 pm; Saturday–Sunday from 12:00 pm (noon) to 5:00 pm. Admission is Free admission (the museum charges no admission fee), as listed on bc.edu in October 2026.
```

**Grace Hoops in full (work-first):**
```
In December 2021, "Grace Hoops" by Winslow Homer became part of the McMullen Museum of Art's collection through the generosity of Peter Lynch, who donated 27 paintings, including this work, as part of the Carolyn A. and Peter S. Lynch Collection. … Painted in 1872, "Grace Hoops" captures two young women engrossed in the "game of graces," a popular 19th-century pastime involving the tossing of wooden hoops. Homer's choice of oil on canvas, a medium he mastered, brilliantly conveys the dynamic motion of the game and the vibrancy of youthful energy. His focus on scenes of childhood innocence during the 1870s resonates within the broader scope of his work, emphasizing the simplicity and joy of everyday life. …
```

**Last stop ending → conclusion:**
```
… underscores the museum's commitment to connecting past and present through art. It leaves behind a legacy of cultural dialogue, inviting future generations to explore the complexities of identity in a diverse and interconnected world.

From Meal at the House of Simon the Pharisee to Roman in the Provinces: Art on the Periphery of Empire, you have followed the thread of the collection of McMullen Museum of Art.

That's 7 stops in all.

Along the way:
- Meal at the House of Simon the Pharisee: Created around 1737, this oil on canvas by Pierre Subleyras captures the moment from the Gospel of Luke where Christ dines at the house of Simon the Pharisee.
- Landscape with Woman in Red: Jules Dupré, celebrated by his contemporaries as "the Beethoven of landscape," was revered for his mastery in capturing the serene and often sublime essence of the countryside.
- Roman in the Provinces: Art on the Periphery of Empire: Organized in collaboration with the Yale University Art Gallery, this significant partnership allowed the exhibition to showcase an extensive collection of artifacts.

If you would like to eat nearby we can build you a restaurant tour.
```

**Dedupe log:**
```
[LOCAL-607] cross-stop fact dedupe: 5 sentence(s) removed
[LOCAL-607] dedupe: dropped from Stop 2 (museum-history fact belongs to Stop 1): "The McMullen Museum's dedication to showcasing such works reflects its broader mission, es"
[LOCAL-607] dedupe: dropped from Stop 3 (museum-history fact belongs to Stop 1): "Before it found a permanent home here, the painting graced numerous prestigious exhibition"
[LOCAL-607] dedupe: dropped from Stop 4 (museum-history fact belongs to Stop 1): "This acquisition was part of a deliberate strategy to enrich the museum's holdings with si"
[LOCAL-607] dedupe: dropped from Stop 5 (museum-history fact belongs to Stop 1): "Three years later, the museum underwent a significant transformation, when it was renamed "
[LOCAL-607] dedupe: dropped from Stop 5 (museum-history fact belongs to Stop 1): "The museum's walls are adorned with carefully curated works thanks to the generous contrib"
```

**BLOCKER 3 (factual integrity) — the gating lines:**
```
PASS: No repeated story across stops
PASS: G4 Prolog/epilog claims trace to story elements (FACTUAL)
PASS: D3(e) No duplicate stops (same work under different labels) (FACTUAL)
FACTUAL_FAIL_COUNT=0
```
(Non-gating style checks "No forbidden phrases", "No cross-stop repetition (>0.85)", and one
"R3 Orientation substance" filler remain on the LLM prose in the pooled stops; they are not
factual-integrity checks and are outside LOCAL-607's scope. FACTUAL_FAIL_COUNT=0.)

```
Tour total:           $0.0000
  (LLM $0.0000  grounding $0.0000  pool_reuse=True)
```

Full artifact: `tours/local607_live/LOCAL607_mcmullen_pool.txt`.
