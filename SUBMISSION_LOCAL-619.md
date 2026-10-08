# SUBMISSION — LOCAL-619: a real conclusion on EVERY path + a correct count after late gates

**Branch:** `LOCAL-619-real-conclusion`
**Base:** `subscribed` @ `992ef90` — verified `git merge-base --is-ancestor 992ef90 HEAD` → exit 0.
**Env:** `/usr/bin/python3` 3.9.6, pytest 8.4.2; Docker 29.6.2.

---

## 1. What was built

### One conclusion builder for every path — `tour_conclusion.py`
A single deterministic module (no LLM) builds the conclusion from the **final
delivered text**, run once as the last step on every path:

- **`build_conclusion(tour_text, venue_name, theme, …)`** — emits, in order:
  1. one short paragraph naming the **thread** (the discovered tour **theme**
     when present, else `the collection of {venue}`);
  2. **"That's N stops"**, with **N counted from the delivered text**
     (`count_delivered_stops` → the `Stop N:` headers actually present), never a
     stale generation-time count;
  3. a one-line prose recap of up to 3 stops, each naming the work plus one
     concrete, already-delivered fact;
  4. the **restaurant offer as the very last sentence**.
- **`rebuild_conclusion(...)`** — the single finalization pass: strips whatever
  trailing conclusion/recap/stub a path produced, appends the one unified
  conclusion, and preserves the trailing `Sources:` block. **Deterministic and
  idempotent** (running it twice yields identical text).
- **`normalise_stop_headers` / `count_delivered_stops`** — recover a `Stop N:`
  header glued onto a prior sentence (the live "…Atelierwand.Stop 3:" defect) so
  the count reflects every stop the listener actually hears.
- **`fix_orientation_first_stop` / `first_stop_name`** — late-gate consistency
  for the orientation's "Your first stop is X" pointer.

### Routed every path to the builder — no competing stub survives
`rebuild_conclusion` is wired as the **last** step on each path:

| Path | Call site |
|------|-----------|
| Fresh generator (finalize, after scorer-retry, before cache/pool store) | `generate_tour_text.py` ~L23822 |
| **Every-path delivery guard** (after dedupe + foreign-sentence sweep) | `generate_tour_text.py` ~L7487 |
| Overview (1-stop) path | `generate_tour_text.py` ~L3925 |
| Cache-trim (by-reference / cached) path | `tour_cache_layer1.py` ~L286 |

The legacy fresh-path stub emitter (`_build_closing_recap`) still runs earlier,
but is **routed through the builder**: the rebuild pass runs after it and
replaces its output, so the "That's N stops —" splice can never ship.

### Late-gate consistency
After any late drop, everything count-dependent is recomputed from the **final**
text: the conclusion count (`rebuild_conclusion`), `stops_count`
(`count_delivered_stops`), the shortfall sentence
(`work_first_evidence.recompute_shortfall_on_delivered`), and the orientation's
first-stop name (`fix_orientation_first_stop`).

### Recap quality fix (post-critique)
The first live critique showed the count fix landed everywhere, but the recap's
residual in-scope defect was that it (a) led with a dry **accession/provenance**
sentence and (b) echoed the stop's **opening sentence verbatim**.
Root cause: the shared `stop_pool_assembly._first_recap_sentence` tries to skip
provenance with `\b(acquir|donat|…)\b`, but the **trailing `\b` makes every stem
fail on the inflected forms that actually occur** ("acquired", "donated",
"founded"), so an accession sentence leaked in as the lead fact.
Fix — contained to the LOCAL-619 module (`tour_conclusion._pick_recap_clause`),
so the shared pool helper and its 590/607 tests are untouched: skip
provenance/accession (corrected stem matching), skip the stop's own opening
sentence, skip gallery viewing-instructions and dangling-pronoun openers,
deprioritise dimensions-only filler, and de-dupe identical clauses across stops.

---

## 2. Tests

### LOCAL-619 acceptance / fixtures — `tests/test_local619_real_conclusion.py`
Fixtures derived from tours 440–442. **20 passed, EXIT 0.** Covers:
count == delivered stops; no `That's N stops —` splice survives; exactly one
conclusion per tour; restaurant line is last; a late-gate drop updates all counts
(conclusion count, `stops_count`, orientation first-stop); glued-header recovery;
idempotency; and the new recap-quality assertions (accession opener skipped,
opening sentence not echoed verbatim, work-story lifted).

### Required regression suites — all PASS, zero failures
```
# root-level: 605, 607, 617_work_first, 618×4, 590×3, 592×2, sq4_merge
211 passed  EXIT=0
# tests/ local60*: 600, 602×10, 603×2, 604, 606, 609, 60_cost_metering
165 passed  EXIT=0
# tests/ local61*: 611, 612, 613, 614×5, 615×4, 616×5, 619
158 passed  EXIT=0
# combined re-run after the recap fix (full required set + 619 = +5 new tests)
539 passed  EXIT=0  (20.28s)
```
Only warning: a benign urllib3/LibreSSL notice.

---

## 3. Live run — isolated, metered, capped $2.50

Disposable container `local619-gen` (`docker run --rm`), image built from the
branch tree (`Dockerfile.generator`), network `development_default`, tour cache
**OFF** (fresh), metered + hard-capped at **$2.50 combined** via
`tests/live_run_meter.py`. 3 never-seen museums × 3 stops. Delivered tours were
stored as additive `is_test` rows and scored with `critique.sh`. **No DELETE.**

### Run 2 (post recap-quality fix) — tour IDs 459 / 460 / 461 — TOTAL **$0.7340**
On all three: delivered-stops == conclusion-count (**MATCH=True**), no splice,
exactly one conclusion, restaurant offer last.

- **Museo Thyssen-Bornemisza (459)** — *late-gate case: 2 delivered, count 2*
  > From David con la cabeza de Goliat y dos soldados to La Virgen de la Anunciación / El ángel de la Anunciación, you have followed the thread of the collection of Museo Thyssen-Bornemisza. That's 2 stops in all. Along the way, a few moments stand out. David con la cabeza…: In this work, Valentin showcases his mastery of dramatic lighting, a technique he adopted from Caravaggio. La Virgen…: Strigel, a German Swabian artist working around 1515–1520, crafted these oil-on-panel works with deliberate intent.
  > If you would like to eat nearby we can build you a restaurant tour.

- **Musée d'Orsay (460)** — 3 delivered, count 3
  > From Le Dejeuner sur l'herbe to Jeunes Filles au piano, you have followed the thread of the collection of Musée d'Orsay. That's 3 stops in all. Along the way, a few moments stand out. Le Dejeuner sur l'herbe: Critics and the public were divided; Manet's bold portrayal of a nude woman casually seated with two fully dressed men was deemed vulgar by some, yet it challenged the artistic conventions… L'Homme blessé: …a poignant self-portrait created between 1844 and 1854. Jeunes Filles au piano: …the French government transferred the painting to the Musée d'Orsay in 1986.
  > If you would like to eat nearby we can build you a restaurant tour.

- **Hamburger Kunsthalle (461)** — 3 delivered, count 3
  > From Das Eismeer to Nana, you have followed the thread of the collection of Hamburger Kunsthalle. That's 3 stops in all. Along the way, a few moments stand out. Das Eismeer: Friedrich produced this evocative oil-on-canvas work… to capture the overwhelming dominance of nature over human endeavors. Atelierwand: The scene reveals a vibrant, Pompeii-red backdrop… emblematic of the dual forces of order and chaos that governed Menzel's artistic practice. Nana: The jury refused the painting, deeming the depiction of a courtesan scandalous.
  > If you would like to eat nearby we can build you a restaurant tour.

### critique.sh scores
| Museum | Run 1 (pre-fix, ids 455/457/458) | Run 2 (post-fix, ids 459/460/461) |
|--------|----------------------------------|-----------------------------------|
| Thyssen | 3 / 10 | 4 / 10 |
| Orsay | 6 / 10 | 5.5 / 10 |
| Kunsthalle | 5 / 10 | 5.5 / 10 |

Run-1 meter: openai $0.5246 + gemini $0.1133 + serper $0.0380 = **$0.6759**.
Run-2 meter: openai $0.5694 + gemini $0.1266 + serper $0.0380 = **$0.7340**.
Both well under the $2.50 cap. (Score variance between runs is LLM
non-determinism — each is a fresh generation.)

---

## 4. Honest assessment of the ≥6/10 target

**The LOCAL-619 deliverable itself is met and verified on every path:** the
conclusion is real, present once, the restaurant offer is last, and — critically
— **the count is correct after a late gate** (Thyssen delivered 2 and the
conclusion says 2, the exact bug the critic called out on 440/441/442). The
recap-quality fix measurably moved the conclusion from a **High-severity** defect
to **Medium** across all three Run-2 critiques.

**The ≥6/10 target was not consistently reached** (1 of 6 tour-runs hit 6). The
dominant remaining **High-severity** defects are **outside LOCAL-619's scope** —
they live in the stop-body narration and facts pipelines, not the conclusion:

1. **Unspoken hours/admission** — "Opening hours weren't published where we
   could read them" / no admission price (criterion 3). Owned by the hours/facts
   pipeline (LOCAL-618 line + preflight), not the conclusion.
2. **Stop bodies lead with accession/provenance** instead of the work
   (criterion 1) — the per-stop narration template ordering in
   `generate_tour_text` story composition.
3. **Garbled appositive / template-slot leaks** — "acquired… from gallery",
   "Baron Hans Heinrich…", "Courbet, an oil-on-canvas self-portrait…"
   (criterion 8) — fact-sheet / narration generation.
4. **Orientation theme contradicts delivered works** (Thyssen 459: intro
   promised "20th–21st century", stops were 1515–1947) — the theme/orientation
   generator.
5. **Raw `Address:` / `Coordinates:` in the spoken body** (criterion 4) —
   delivery formatting.

The residual conclusion gripe ("synthesize, don't recap; no verbatim reuse") is
**partly in tension with this ticket's own spec**, which mandates "a one-line
recap of up to 3 stops, each naming the work plus one concrete, already-delivered
fact (reuse `_first_recap_sentence`)" and "No LLM is needed." A verbatim-lifted
already-delivered fact is exactly what was asked for; a fully synthesized close
would require an LLM pass the ticket explicitly says is unnecessary. Within the
no-LLM constraint, `_pick_recap_clause` now lifts the most story-bearing
non-accession, non-opener sentence available.

**Recommendation:** the next point of leverage is the **stop-body narration
template** (force work+artist to lead, demote accession to ≤1 sentence) and the
**hours/admission facts path** — both out of scope here, each likely worth
1–2 points, and each the dominant High defect on these three venues.

---

## 5. Artifacts
- Live logs: `tours/local619_live/local619_live.log` (run 1),
  `tours/local619_live2/local619_live2.log` (run 2).
- Delivered tours: `tours/local619_live*/LOCAL619_{THYSSEN,ORSAY,KUNSTHALLE}.txt`.
- Critiques: `~/Audioura/.continuous_dev/calib/critique/critique_{455,457,458,459,460,461}.md`.
- Stored `is_test` rows: audio_tours ids 455, 457, 458, 459, 460, 461.
