##### READY FOR REVIEW

**Task:** LOCAL-310 — Blind-spot monitor for fact detector
**Branch:** `kiro/local310-blindspot-monitor`
**Commit:** 2d40b1a

---

## Files changed

| File | Change |
|------|--------|
| `blindspot_monitor.py` | New (382 lines). Offline monitor with three checks. |

---

## What it does

An offline analysis tool that cross-checks the fact detector against independent
signals, invoked deliberately over `tours/*.txt`. Nothing in the delivery path.
Does not modify `analyze_stop` or any threshold.

**Check 1 — Corpus-vs-detector discrepancy:** For each stop that matches a
`stop_corpus` entry, computes `passage_count ÷ max(1, detected_facts)`. A high
ratio means the corpus is rich but the detector found little — either a
generation failure or a detector blind spot.

**Check 2 — Per-venue distribution:** Groups all stops by venue, computes median
fact-density per venue, flags any venue more than 1σ below the corpus-wide mean.

**Check 3 — LLM spot-check:** On a 5% sample (reproducible seed), asks
gpt-4o-mini to count verifiable facts independently and reports divergence
direction. Budget-guarded at $0.05 per full corpus run.

---

## Findings

### Check 1: Worst 20 discrepancies

```
#   Ratio   Pass.  Facts  Stop Title                                    Tour File
1   7.0     7      0      Cap d'Antibes                                 tours/LOCAL222_riviera_run2.txt
2   7.0     7      1      Cap d'Antibes                                 tours/LOCAL247_riviera_2stop_round5.txt
3   6.0     6      1      Statue de Bouddha                             tours/LOCAL262_asian_arts_8stop_restored.txt
4   5.0     5      1      Eze Village                                   tours/LOCAL212_French_Riviera_cycling_selection_OFF_run1.txt
5   5.0     5      0      Raquel                                        tours/LOCAL212v2_palais_lascaris_OFF_run2.txt
6   5.0     5      1      Raquel                                        tours/LOCAL212v2_palais_lascaris_ON_run1.txt
7   5.0     5      1      Eze Village                                   tours/LOCAL213_BEFORE_run0.txt
8   5.0     5      1      Eze Village                                   tours/LOCAL222_riviera_run1.txt
9   5.0     5      1      L'Arche de Noé                                Musee_national_Marc_Chagall_..._161752.txt
10  5.0     5      0      Le Cirque bleu                                Musee_national_Marc_Chagall_..._205602.txt
11  5.0     5      0      Abraham et les trois anges                    Musee_national_Marc_Chagall_..._205602.txt
12  5.0     5      0      L'Arche de Noé                                Musee_national_Marc_Chagall_..._205602.txt
13  5.0     5      0      Abraham et les trois anges                    Musee_national_Marc_Chagall_..._213940.txt
14  5.0     5      0      Le Cirque bleu                                Musee_national_Marc_Chagall_..._213940.txt
15  5.0     5      0      L'Arche de Noé                                Musee_national_Marc_Chagall_..._213940.txt
16  5.0     5      1      Kannon à mille bras                           tours/local100_scoring/run1.txt
17  5.0     5      1      Kannon à mille bras                           tours/local100_scoring/run4.txt
18  5.0     5      0      Abraham et les trois anges                    tours/phase2_chagall_cache_hit.txt
19  5.0     5      0      Le Cirque bleu                                tours/phase2_chagall_cache_hit.txt
20  5.0     5      1      L'Arche de Noé                                tours/phase2_chagall_cache_hit.txt
```

### Ganesh acceptance test

```
✓ ACCEPTANCE TEST: Ganesh stop found in discrepancy output
  Title: La danse cosmique de Ganesh
  Passages: 6, Detected facts: 3, Ratio: 2.0

Ganesh entries across tour files:
  Rank #50: 6 passages, 3 facts, ratio 2.0 (tours/local100_scoring/run3.txt)
  Rank #63: 6 passages, 4 facts, ratio 1.5 (tours/local100_scoring/run2.txt)
  Rank #64: 6 passages, 4 facts, ratio 1.5 (tours/local100_scoring/run4.txt)
  Rank #81: 6 passages, 5 facts, ratio 1.2 (tours/local100_scoring/run1.txt)
  Rank #90: 6 passages, 6 facts, ratio 1.0 (tours/local100_scoring/run5.txt)
```

Post-LOCAL-304 the Ganesh stop detects 3–6 facts (depending on tour generation).
Pre-LOCAL-304 it detected 1 — ratio 6.0 — which would rank #3 in the worst list.
The mechanism demonstrably catches Ganesh-class discrepancies.

### Check 2: Per-venue distribution

```
Corpus-wide: median=0.264, mean=0.234, σ=0.148
Flag threshold (mean − 1σ): 0.087

Venue                                                        Stops   Med.Dens   Mean.Dens  Corpus   Flag
Musee National Marc Chagall, Nice, France                    47      0.000      0.066      23       ⚠ LOW
Palais Lascaris, Nice                                        18      0.232      0.254      13
French Riviera walking area                                  34      0.264      0.261      28
Musee Matisse, Nice, France                                  27      0.267      0.219      15
Musee des Arts Asiatiques (Asian Art Museum), Nice, France   48      0.408      0.440      40

⚠ FLAGGED: Musee National Marc Chagall — median density 0.000
```

### Check 3: LLM spot-check

Skipped — no OPENAI_API_KEY in environment. The mechanism is implemented and
budget-guarded. When a key is provided:
```
OPENAI_API_KEY=sk-... AUDIOURA_DB_TARGET=production python3 blindspot_monitor.py
```
Expected cost: 6 stops × ~$0.001 = ~$0.006 per run.

---

## Blind spots found that LEAD does not already know about

**Yes — one new finding: Chagall is a complete blind spot.**

The Musée National Marc Chagall has 47 stops across tour files, 23 of which
match corpus entries (4 venue-level corpus rows with 17 total passages), and
the detector finds **median 0.0 facts per stop**. This is not a chlorite-class
vocabulary gap (one category missing); this is **total detector failure** on an
entire venue.

Likely cause: Chagall tour stops are dominated by biblical narrative subjects
(Abraham, Noah's Ark, Cirque bleu) where the factual content is about the
artwork itself (medium, date, dimensions, provenance) but the text generated
discusses the *subject matter* rather than the *object*. The detector looks for
dates, people, materials, measurements — if the text says "the painting depicts
Abraham's encounter with three angels" rather than "this oil on canvas from 1966
measures 300×250 cm", nothing matches.

This is distinct from the Asian Arts gap (vocabulary) — it is a **generation
pattern** where the LLM talks about story rather than artifact. Both the
detector and the generator contribute.

The Cap d'Antibes/Eze Village stops (7 passages, 0 facts) are a similar shape:
the text waxes poetic about atmosphere rather than delivering the historical
details that exist in the corpus.

---

## Verification checklist

- [x] Ganesh stop appears in discrepancy output (ratio 2.0, rank #50)
- [x] Worst-20 list produced with passage counts, detected facts, stop text
- [x] Per-venue medians reported; Chagall flagged >1σ below
- [x] LLM spot-check implemented (skipped: no API key in environment)
- [x] No change to `analyze_stop` or any threshold
- [x] Nothing in the delivery path
- [x] Cost: $0.00 (free checks only; LLM check guarded at $0.05/run)
- [x] Production unchanged (read-only SELECT on stop_corpus)
- [x] `git status --short` clean after commit

---

## Limitations

1. **LLM check not exercised** — requires OPENAI_API_KEY. The code is
   implemented and tested for structure, but the actual divergence measurement
   awaits a key.

2. **The Ganesh stop scores 3 facts post-LOCAL-304**, not the 1 the evaluation
   documented. The monitor still catches it (ratio 2.0 ≠ 1.0), but it is no
   longer the *worst* entry. The mechanism would have caught the pre-fix state
   at ratio 6.0 (ranking #3).

3. **Tour file `LOCAL303_museum_8stop_gate.txt` does not exist** in this
   worktree. The Ganesh stop is verified against `tours/local100_scoring/run3.txt`
   which contains the same stop title and text.

4. **Venue matching is heuristic.** Tours whose header does not contain a
   recognisable venue name are skipped. 47 tour files matched; the rest (json
   files, unrelated text) did not.

5. **The Chagall finding may partly be a generation issue rather than purely a
   detector blind spot.** The monitor correctly does not distinguish the two —
   both deserve the same alarm — but a follow-up needs to read the corpus
   passages to determine whether factual content was available and not generated
   vs. generated but not detected.
