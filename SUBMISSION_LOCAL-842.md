# SUBMISSION — LOCAL-842: the story scanner recognises a real stake (slashed, attacked, rejected, mocked, stolen, died…) with depiction precision

**Branch:** `LOCAL-842-scan-stakes-precision`
**Base:** subscribed `d2ad4f74` (contains LOCAL-840).
`git merge-base --is-ancestor d2ad4f74 HEAD` → exit 0.

---

## The defect (from LOCAL-840's root-cause)

LOCAL-840 fixed the story **material**: each work's own Wikipedia human-event
passages now reach the museum story pass, and the pipeline writes vivid grounded
human stories into delivered tours — the Night Watch 1975 knife attack. But
`story_opportunity_scan` scored that complete story `agency=1 stakes=0 → NO STORY`:

> "On 14 September 1975, Wilhelmus de Rijk … **attacked** The Night Watch with a
> bread knife, **slashing** several large zig-zagged cuts … the painting was left
> permanently **scarred**. De Rijk **died by suicide** in April 1976 …"

`_STAKES` knew `destroyed/lost/refused/survived/bequeathed/never…` but **not**
`slashed/attacked/scarred/vandalised/stolen/mocked/rejected/died/suicide` — the
words real art-crime, scandal and death events are written in. Orsay and Rijks
scored 1/5 each, although the research now carried real stories. **LEAD ruling
D752:** the D511 bar is unchanged (one subject, action, stake, 3+ consecutive
sentences); the scanner must **RECOGNISE a stake when the text states one.**

## What I changed — scanner only, two halves (`story_opportunity_scan.py`, +88/−4)

### 1. `_STAKES` WIDENED ADDITIVELY (Do-item 1)
Harm / loss / conflict / judgement outcomes, inflected forms: `attacked, slashed,
stabbed, vandalised, damaged, scarred, defaced, stolen, looted, plundered, burned,
banned, censored, suppressed, rejected/rejection, refused/refusal, mocked,
ridiculed, jeered, scandal, outrage, notoriety, controversy, outcry, denounced,
disgraced, sued, prosecuted, arrested, imprisoned, jailed, died, killed, slain,
murdered, suicide, assassinated, perished, fled, hid, escaped, forged, counterfeit,
bankrupt, ruined, in debt, sold to pay … debts, evicted, dispossessed`.
**D512 "widening never narrows":** every pre-842 marker still matches — the
alternation can only make the scanner see MORE stakes, never fewer (asserted by
`test_widening_never_narrows`).

### 2. PRECISION — a stake counts only for a REAL event, never a DEPICTION (Do-item 2)
The width's cost is that the same words appear in descriptions of what a picture
*shows*. New `_DEPICTION_CUE` + `_sentence_has_stakes(sentence)`: a stake word in a
sentence that reaches for the image's content — `shows / depicts / portrays /
represents`, `in the foreground / background`, `at the centre/left/right`, `the
scene …`, `the canvas/fresco/mural shows …` — does **not** count. "The painting
shows a dying soldier", "a stolen kiss in the foreground", "depicts the burning of
Troy" carry a stake word and **no** story. All three stakes counters in `measure()`
(`h['stakes']`, `run_stakes`, `total_stakes`) now route through this one helper, so
the handle table, the run verdict and the totals agree (no D483-shape split).

## Tests (`test_local842_scan_stakes_precision.py`, 14, green) — Do-item 3

| case | verdict |
|---|---|
| exact delivered **Night Watch** paragraph | **STORY** (run=3, agency=1, stakes=3) |
| **Manet** 1863 Salon refusal (840, grounded verbatim) | **STORY** |
| **Lacan** hid L'Origine behind Masson's panel (840, grounded verbatim) | **STORY** |
| **10 depiction sentences** with stake words | **NO STORY** (total_stakes=0) |

Plus RED-CHECK control classes: the harm/loss/judgement vocabulary is seen;
`test_widening_never_narrows` (D512 safety); inflected forms; every depiction cue
suppresses its stake; a real event with a stray "shows" is **not** suppressed; and
the non-story controls (exposition, catalogue, a pure depiction run) still refuse.

**Every existing scanner test still passes** (no regression):
`test_d512 / test_local495 / test_local469 / test_local468 / test_d489 /
test_local461 / test_local462 / test_local832 / test_local832b / test_local837 /
test_local840` — **222 passed**; `test_local483_gate_fold_and_boundary.py` **70/70**.

## Orsay / Rijks re-scored on the 840 DELIVERED texts — before & after (Do-item 4)

`rescore_local840_delivered.py` (no new generation). It restores the exact pre-842
`_STAKES` (depiction guard off) for BEFORE and the current scanner for AFTER, and
quotes the stake sentence each AFTER-story turns on. Full output:
`reports/local842/rescore_delivered.txt`.

**BEFORE** = the per-stop verdicts the 840 live run itself recorded
(`reports/local840/live_result.json`): **Orsay 1/5, Rijks 1/5.**

**AFTER** on the delivered prose:
```
Orsay (delivered tour file):
  L'Origine du monde        NO STORY → STORY  (stake: "…its eventual public unveiling
                                                underline the painting's controversial status…")
  Le Déjeuner sur l'herbe   STORY   → STORY  (stake: "The painting was initially rejected
                                                by the official Paris Salon…")
  Bal du moulin de la Galette  NO STORY → NO STORY  (agency=0 stakes=0)
  Une moderne Olympia          NO STORY → NO STORY
  La Nuit étoilée              NO STORY → NO STORY
Rijks — Night Watch delivered paragraph:
  De Nachtwacht             NO STORY → STORY  (run=3 agency=1 stakes=3;
     stake: "On 14 September 1975, Wilhelmus de Rijk … attacked The Night Watch
             with a bread knife, slashing several large zig-zagged cuts…")
```
The scanner now recognises the violence/judgement/death stakes it was blind to.

## Live — BUDGET ENFORCED (`run_local842_live.sh` + `run_local842_container.py`)

Isolated **`local842-*`** containers (never a shared `audioura-*` container;
verified the shared containers were untouched), throwaway postgres seeded from the
REAL cached rows (Orsay Q23402, Rijks Q190804), meter contract with a dedicated
acceptance ledger, cheap museum arm, `DISABLE_STOP_POOL=1`,
`STORY_PASS_MODEL=gpt-4.1`. `TASK_BUDGET_ID=LOCAL-842 TASK_BUDGET_USD=0.70`.
Orsay (5) + Rijks (5). Evidence: `reports/local842/live_run.log` +
`reports/local842/live_result.json`.

**Cost:** whole-task metered **$0.7147** (Orsay $0.3428, Rijks $0.2945 wall; the
ledger's reserve gate now blocks any further tour at the $0.70 cap).

**Result:** Orsay **2/5**, Rijks **1/5** — **does NOT meet ≥3/5. The miss is NOT
the scanner.** Proven two ways:

1. **Before/after on THIS run's delivered text is identical** (Orsay 2==2,
   Rijks 1==1). Every failing stop fails on `agency=0` in the delivered run, not on
   stakes vocabulary — i.e. the stake-carrying sentences are **absent from the
   delivered text the scanner judges.**
2. **They were written, then deleted downstream.** The story pass DID write the
   Night Watch attack this run (`live_run.log:3225`), and it was removed by two
   OTHER gates:
   - `LOCAL-652` foreign-work/artist remover (`:3368` — flags "Wilhelmus de Rijk");
   - `LOCAL-472` ungrounded-entity gate (`:3370` — *"No concrete link between
     Wilhelmus de Rijk and The Night Watch is established"*, on a sentence that
     literally says he attacked The Night Watch).
   Manet's "The Salon jury … rejected the painting …" was removed the same way
   (`:1379`). On the exact written-but-dropped Night Watch story, the **pre-842
   scanner says NO STORY and the 842 scanner says STORY** (run=3 agency=1
   stakes=3) — the scanner does precisely what the ticket asked; the sentence just
   never reaches delivery.

So the live ≥3/5 ceiling has moved from the scanner (this ticket, now fixed) to the
downstream grounding/foreign-entity gates `LOCAL-652`/`LOCAL-472`, which delete the
grounded Wikipedia-sourced stake sentences before delivery. That is a different
gate, outside this ticket's declared scope (D752: "the scanner must RECOGNISE a
stake"). Editing it was not undertaken here.

## Net

The scanner defect LOCAL-840 named is **fixed within scope**: `_STAKES` now
recognises the harm/loss/conflict/judgement vocabulary of real human stories,
additively (D512) and with depiction precision (Do-item 2), so the delivered Night
Watch / Manet / Lacan stories score **STORY** where they scored NO STORY — proven by
the before/after rescore on the 840 delivered texts and by direct tests. The live
≥3/5 was not reached because the grounded stake sentences are **deleted downstream
by `LOCAL-652`/`LOCAL-472` before delivery** — demonstrated from the live log and
isolated by the before==after rescore on this run's delivered text. 222 scanner
tests + 70 (483) green; no forbidden files touched; no DB written; isolated
containers only.

## Files

- `story_opportunity_scan.py` — `_STAKES` widened additively; `_DEPICTION_CUE` +
  `_sentence_has_stakes` precision; all three stakes counters routed through it.
- `test_local842_scan_stakes_precision.py` — 14 tests (widening, precision, controls).
- `rescore_local840_delivered.py` — before/after rescore on the 840 delivered texts.
- `run_local842_container.py` + `run_local842_live.sh` — isolated budget-enforced live.
- `reports/local842/` — `live_run.log`, `live_result.json`, `rescore_delivered.txt`.

## How to reproduce

```bash
python3 -m pytest test_local842_scan_stakes_precision.py -q                 # 14 green
python3 rescore_local840_delivered.py                                       # before/after on 840 delivered
STORY_PASS_MODEL=gpt-4.1 ./run_local842_live.sh                             # budget-enforced live, Orsay + Rijks
```
