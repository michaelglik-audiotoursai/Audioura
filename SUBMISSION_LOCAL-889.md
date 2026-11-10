# SUBMISSION: LOCAL-889 key-fact coverage, removed claims stay removed, filler cap (branch `LOCAL-889-key-fact-coverage`, base subscribed 7d5663b5)

**Status: unproven live. Handing to LEAD.** The one allowed full-tour live run used the first version of the code (5bd7b48c). It exposed four defects in that code, fixed offline in cbadf15c. **The fixed code has not been run live.** Per the task I did not re-run.

## What was built
New module `key_fact_coverage.py` (generic: no venue name, date or claim in the code, D769), wired in at the END of `generate_tour_text` after the 884 final re-pass, plus hooks in `strict_grounding_gate.apply_grounding_gate`:

1. **Key-fact coverage.** For each stop, `key_facts()` reads the stop's OWN Wikipedia article (the article whose title best matches the stop). It uses lead + passages and never the infobox. It extracts:
   - construction/completion years (a build-verb sentence, plus a completion year that sits next to its verb);
   - the architect (`designed by` / `architect X`; later redesigns and renovations are excluded);
   - the dated defining event (the 887/888 `signature_event` + `event_sentences` scorers, restricted to that article).

   After all passes, a missing fact gets its evidence sentence back as ONE plain sentence, placed in chronological order. That sentence is gated once more and only kept if the gate keeps it. Logs `[LOCAL-889] coverage <stop>: k/K key facts`.
2. **Deny-set.** `deny_record` / `is_denied` store each removed claim as normalised key tokens and match on ≥ 2 shared tokens plus a shared predicate token. The gate records its own CONTRADICTED/UNSUPPORTED drops, mechanical drops and the 880 §1 scrub. Every later gate call, and the finishing pass, drops a match again and logs the evidence line that "backs" it.
3. **Filler cap.** `cap_filler`:
   - reflective tails ("…, a reminder that…", "bridging past and present") are trimmed off fact sentences;
   - reflective sentences with no fact and no visible detail are dropped;
   - at most one sensory sentence is kept per stop, the most concrete/visible one.
4. **Mechanical UNSUPPORTED rules** (`deterministic_unsupported`, applied even when the LLM judge says SUPPORTED):
   - a year the evidence never states;
   - a year range with an end stated only in an infobox field list;
   - a departure dated on a day the evidence records a resignation;
   - a former identity of the building that the stop's own evidence contests.
5. **Harness.** The City Hall check now requires the years 1898 AND 1909, not the name. `evaluate_889` reports coverage k/K, "intelligence headquarters", City Hall years, Opera 1944 and ≤ 1 sensory sentence per stop.

## Findings the task asked for
- **Where "intelligence headquarters" comes from:** the stop's OWN article, not a low-tier snippet. The War Remnants Museum Wikipedia History passage says *"It was located in the former United States Information Agency building. The building was the US military's intelligence headquarters during the Vietnam War."* The evidence contradicts itself. In 888 the 5.17 regeneration removed one wording and the 888 coherence re-narration restated it from that passage, so the mini gate judged it SUPPORTED. Rule added: when the stop's evidence gives two different former identities for the building, the narration states neither ("contested former identity"). It is logged with both phrases.
- **Post Office, Eiffel "earlier work in Saigon between 1860 and 1863":** the only 1860–1863 in the evidence is the **infobox** field list, recorded verbatim from the 889 run log: `years built: *1860-1863 (Former building) *1886-1891 (Current building); architect: *Gustave Eiffel (Former building…`. The prose says only "often erroneously credited as being the work of Gustave Eiffel", and nothing says the misconception arose from earlier work. The claim is now UNSUPPORTED (range end stated only in an infobox). There is a test on the recorded evidence.
- **Palace, "Thiệu stayed here until 21 April 1975, when he fled":** the Palace's OWN article says it nearly word for word: *"served as Thiệu's home and office from October 1967 to 21 April 1975, when he fled the country"*. The task's rule ("UNSUPPORTED if the evidence does not say it exactly") therefore does **not** drop it on the Palace evidence alone. Thiệu's own article records *"On 21 April 1975, Thiệu … resigned as president"*. When that sentence is in the stop's evidence, the new resignation-date rule makes the claim UNSUPPORTED. Both cases are tested. **LEAD decision needed:** add the person's article to the Palace bundle, or accept the Palace article's wording.

## Live run (1 full tour, cloud snapshot, `-p local889`, port 55989, `LOCAL_SNAPSHOT_TAG=889`, code 5bd7b48c)
**Meter: $0.0720 over 63 rows** (meter ok: 63 ≥ 37 logged calls). Ledger `LOCAL-889` = **$0.072 of $0.60**. The finishing pass itself cost $0.0037.

| # | Stop | evidence_chars | final gate labelled / kept | content sentences | sensory | coverage k/K (in-run) |
|---|---|---|---|---|---|---|
| 1 | Cathedral | 8974 | 4 / 4 | 6 | 1 | 2/2 |
| 2 | Post Office | 6103 | 4 / 4 | 6 | 1 | 2/2 |
| 3 | Book Street | 1570 | 3 / 3 | 6 | 0 | 0/0 |
| 4 | Independence Palace | 4415 | 4 / 2 | 6 | 1 | **1/3** |
| 5 | War Remnants Museum | 5982 | 5 / 4 | 4 | 0 | 1/1 |
| 6 | Opera House | 11619 | 6 / 4 | 5 | 0 | 3/3 |
| 7 | City Hall | 13052 | 3 / 3 | 6 | 0 | 2/2 |
| 8 | Café Apartments 42 | 299 | 2 / 2 | 4 | 0 | 0/0 |
| 9 | Bạch Đằng Pier | 10410 | 1 / 0 | 4 | 1 | 0/1 |
| 10 | Thi Bar | 1420 | 2 / 2 | 9 | 0 | 0/0 |

The harness re-computes coverage in its own pass, so its numbers differ from the in-run ones: Palace 1/3, Pier 0/1, the rest k = K.

### Checklist (live, code 5bd7b48c)
| Item | Result |
|---|---|
| 10/10 stops; every stop ≥ 4 content sentences | PASS |
| every stop ≥ 5 | FAIL (WRM 4, Café 4, Pier 4) |
| Palace states 30 April 1975 plainly | **FAIL** (regression: my deny-set blocked it, see defect A) |
| City Hall has 1898 and 1909 | PASS (harness, years check) |
| Opera House has 1944 (evidence has it) | **FAIL** |
| no "intelligence headquarters" | **FAIL**: "housed in the former US military intelligence headquarters" |
| ≤ 1 sensory sentence per stop | PASS |
| no orphan openers | FAIL (Book Street "This small"; the Thi Bar closing-line false positive from 888) |
| audit 0 unsupported (gpt-4.1) | **PASS (0)** |
| meter total | $0.0720 |

Artifacts: `submission_artifacts/local889/saigon_warm.txt`, `saigon_warm_audit.json` (committed as shipped). Run and meter logs are in `_local889_meterlogs/` (git-ignored, not committed).

### Defects the live run exposed (all fixed offline in cbadf15c)
- **A. Wrong deny source.** I had recorded Phase 5.17 "removed by gates" sentences. Those are regeneration/style removals, not verdicts. They carried the Palace's sourced tank event, the Foulhoux credit and the WRM opening date, so the deny-set blocked good facts (Palace 1/3, 30 April lost). Fix: only verdict sources count. A soft LLM verdict also no longer blocks a near-verbatim sentence of the stop's own article (same dates and numbers). The mini judge had CONTRADICTED the article's own 30 April sentence.
- **B. Raw evidence injected.** Coverage injected `Infobox: …; architect: *Gustave Eiffel …` into the Post Office and City Hall. Fix: key facts come from prose only, and a raw-field guard drops any `Infobox:`/`Passages:`/`key: value; key: value` sentence before shipping.
- **C. Wrong article for events.** The event was taken from the whole bundle, e.g. the Cathedral got a square-renaming sentence. Fix: only the stop's own article is used.
- **D. Intelligence HQ not caught.** The new wording shared too few tokens with the removed one. Fix: the contested-identity rule above, which also catches the 889 live wording (tested).

## Offline verification (fixed code)
- `tests/test_local889_key_facts.py`: **36 passed**. Inputs:
  - the 888 shipped text (`submission_artifacts/local888/saigon_warm.txt`);
  - the 889 shipped text;
  - `tests/fixtures/local889_recorded.json`: Wikipedia lead/passages fetched 2026-11-10 verbatim, plus infobox lines verbatim from the 889 run log, assembled in the generator's `format_item` shape. Neither run saved its evidence bundle, so this is a stand-in, not the run's own bundle.
- Replay of the fixed finishing pass on the **889 live text** (`test_replay_on_the_889_live_text`): intelligence HQ dropped, Infobox lines gone, Palace 30 April 1975 restored (once), Opera 1944 restored, City Hall keeps "built between 1898 and 1909" plus Gardès, Palace reflective lines dropped, k = K on every stop with facts. **This is an offline replay with a stub judge that says SUPPORTED, not a live measurement.**
- Regression: 873–888 suites + 879: 650 passed, 4 skipped. `tests/test_local88_tour_pollution.py` fails the same 4 tests on the untouched base (DB-data dependent) and was deselected. `run_cloud_parity_proof.py --selfcheck` PASS.

## Not proven / for LEAD
- No live run of the fixed code (cbadf15c). The next task should run it once.
- Thiệu wording: see the LEAD decision above.
- The new year rule drops any sentence with a year the stop's evidence never states. On a thin bundle that can shorten a stop. The floor top-up refills from evidence prose only and was not exercised live.
- Opera years extract as 1900 only (the "1898 … commenced" start is not paired, since the year comes before the verb).
- The harness orphan check still flags the tour-closing line (888 note).
