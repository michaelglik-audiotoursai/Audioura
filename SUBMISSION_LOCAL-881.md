# SUBMISSION — LOCAL-881: signature-story trust (the picker chose FALSE / off-site stories and the gates protected them)

**Branch:** `LOCAL-881-signature-story-trust`
**Base:** subscribed @ `7d5f2c93` (`git merge-base --is-ancestor 7d5f2c93 HEAD` → exit 0)
**Service:** generator only. No schema, env or secret change.
**Evidence:** ClickUp `wdvrdazeya` (wave 39, proof 547, gen 00041-lkk — rolled back).

## The defect

LOCAL-880 picks 1–2 signature stories per stop before narration and then
**protects** their source sentences from the claim gate (`stop_protected`). Wave 39
drew those stories from whatever evidence was on the stop — including the 873
thin-stop page facts — and protected them, so a wrong pick became *worse* than no
story:

| Stop | Shipped | Truth |
|---|---|---|
| Post Office | "designed by Gustave Eiffel", "built in 1860" | Vildieu + Foulhoux, 1886–91 (the stop's own article flags the Eiffel attribution) |
| Book Street | the 1968 Loan/Lém execution "right here" | it happened in Chợ Lớn; the fact did not name the street |
| City Hall | the Gia Long Palace (Foulhoux 1890, a museum ~600 m away) | the Hôtel de Ville, 1898–1909 — a different building that passed the 2 km geo-gate |
| Palace | "months before … 31 October 1966" of a Nov 1963 event | that is three years, not months |
| Palace | the tank story with no "30 April 1975" | the exact date was lost in regeneration |

## The fix (all generic — D769, nothing hard-coded to any tour)

1. **Own-source provenance.** The signature source must be the stop's OWN article
   (name-matched + geo-gated upstream), or a 873 page fact that NAMES the stop. The
   picker now receives the own evidence and the page facts separately
   (`own_evidence_text`, `page_facts`); a 873 fact that does not name the stop is
   detail only, never the signature source. (`signature_story.story_from_own_source`)
2. **Location claim names the stop.** A story with "right here" / "on this spot" /
   "in this building" is dropped unless the source sentence names this stop as the
   place. A multi-token stop name must appear as an ordered phrase, so the Loan/Lém
   fact ("Nguyễn Ngọc Loan … Nguyễn Văn Lém on a Saigon street"), which shares only
   the common tokens *nguyễn*/*văn*, does not count as naming Book Street.
   (`location_claim_ok`, `source_names_stop`, `_distinctive_name_phrases`)
3. **Contradiction beats protection.** The picker rejects a story whose own evidence
   flags a myth / misattribution about it. In the gate, protection is computed with a
   myth exclusion and applied only AFTER the contradiction checks (build-range,
   evidence-text, claim-vs-authority) and a new relative-time check — each of which
   wins over protection. `stop_protected` can no longer shield a contradicted
   sentence. (`evidence_flags_myth`, `_evidence_flags_myth_about`, `_filter_stop_body_core`)
4. **Dense-centre venue match.** An article whose title does not name-match the stop
   must sit within **300 m** AND share a distinctive name token (city and kind words
   stripped), else it is rejected. The Gia Long Palace (~600 m) no longer stands in
   for City Hall; a bare "Opera House" whose own article name-matches by containment
   keeps the wider 2 km gate. (`landmark_wikipedia_evidence.DENSE_CENTRE_KM`,
   `_titles_share_distinctive_token`, `_pick`)
5. **Relative-time check.** A phrase relating two dated events
   ("months/years before/after X") must agree with the years present; "months before
   … 1966" of a 1963 event (a 3-year gap) is dropped — in the picker and in the gate.
   (`relative_time_consistent`, `_relative_time_consistent`)
6. **The date survives.** When a story's source carries a full date, it is stored as
   `source_date`; the survival check requires its MONTH and YEAR in the delivered body,
   and the regeneration prompt and the narrator block pass the exact date. The Palace
   keeps "30 April 1975". (`source_full_date`, `body_keeps_date`, `body_tells_story`,
   `required_element_block`, `regenerate_body_with_story`)

## Part 1 / Part 3 / Part 4 MISSING (task 7 — investigated, not related)

Two unrelated systems, both benign, confirmed from this branch's own run log:

* **Closing-offer parts (LOCAL-273/275).** `[LOCAL-273] Part 1: no verified nearby
  stop found — omitted` and `Part 4 FAILED all 2 attempts — omitting`: the
  forward-connection / similar-tour / restaurant offers are omitted because the proof
  DB's corpus is Riviera-seeded (its queries look for nice/antibes/monaco/cannes), so
  a Saigon tour has no verified nearby stop, restaurant or treat. It **fails closed**
  by design — silence, not a false offer.
* **Prolog-structure validator.** `[ERROR] Part 1: PART1_MISSING` /
  `[ERROR] Part 3: PART3_MISSING` come from `validate_prolog_structure` (the intro
  template check: Part 1 = tour name + transport mode, Part 3 = purpose/intrigue).
  Advisory, not fatal.

Neither touches signature-story provenance, so no fix was made.

## Proof (ONE live run, budget enforced)

`TASK_BUDGET_ID=LOCAL-881 TASK_BUDGET_USD=0.40`. Own isolated postgres
(`docker-compose.local881-proof.yml`, project `local881`, port 55981), torn down
after; the shared `audioura-*` containers (14 running), the shared dev DB and the
live DB were never touched (D753). Total spend **$0.3626** of $0.40 (control sub-cap
$0.10). Runner: `run_local881_live.py --run`.

**Saigon — Michael's same 10 stops — PASS**
* Post Office: current building Foulhoux + Vildieu, 1886–91; Eiffel appears only as
  the sourced *earlier* building (Saigon Steel Wire Department, 1860–63), exactly as
  the stop's own Wikipedia infobox records — NOT the wave-39 myth of crediting the
  current building to Eiffel.
* Book Street: no Loan/Lém "here".
* City Hall: Hôtel de Ville, 1898–1909 — not the Gia Long Palace.
* No "months before" with years between.
* Palace: *"On 30 April 1975, a tank from the Liberation Army of South Vietnam crashed
  through these very gates."*
* Every stop ≥ 5 content sentences; all banned strings absent; no `/wiki/Saigon_Centre`
  fetch; Opera House is Saigon's; Post Office not empty.
* Every signature story's source logged as the stop's own Wikipedia article URL or a
  873 page naming the stop.

**Control — Paris, 3 stops — PASS**
* Eiffel Tower, Arc de Triomphe, Palais Garnier; each gets a true, sourced signature
  story; no uncorrected "sole design" myth; no empty body.

Tour texts: `submission_artifacts/local881/saigon_tour.txt`,
`submission_artifacts/local881/paris_control_tour.txt`. (Run/meter logs stay in
`_local881_meterlogs/` and are never committed.)

## Tests

`tests/test_local881_signature_trust.py` — 16 offline tests (injected `narrate_fn` /
`fetch_fn`, no network) covering every ticket test string plus a generic Paris
control. Full related suite green: 126 passed (LOCAL-881, 880, 872/872b/872c, 878,
879 families). The four touched modules compile clean.

## Files changed

* `signature_story.py` — own-source provenance, myth reject, location-claim-names-stop,
  relative-time, full-date survival + regen date.
* `landmark_claim_gate.py` — contradiction/myth beats protection; relative-time drop.
* `landmark_wikipedia_evidence.py` — dense-centre 300 m + distinctive-token venue match.
* `generate_tour_text.py` — split own evidence from 873 page facts into the picker;
  log the signature source URL per stop.
* `tests/test_local881_signature_trust.py` (new), `run_local881_live.py` (new),
  `docker-compose.local881-proof.yml` (new), `submission_artifacts/local881/*.txt` (new).
