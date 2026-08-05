# Quality Profile — All Stored Tours

**For Michael, 2026-08-04.** Measured with the existing instruments
(`sentence_group_scorer.py`, `style_validator_detector.py`, `claim_check.py`,
`corpus_coverage.py`) — **unmodified**, run read-only against 84 tours with
content. No i-con score computed (§7 floors not set, D102).

---

## Headlines (real tours, n=29)

| figure | value | reading |
|---|---|---|
| R1 (imperatives) mean rate | **35.1%** of groups | one in three groups tells the listener what to do |
| R1 > 50% of groups | 6 of 29 tours | six tours are more instruction than content |
| R9 (generic-delete) | 7 of 29 tours have at least one | rare, but present |
| Contradicted claims | **0 of 29 tours** | the hard block (D114) would fire on nothing today |
| All stops EMPTY (no corpus) | **24 of 29 tours** | 83% of real tours have zero sourced material |
| At least one COVERED stop | 5 of 29 tours | only 5 tours have any stop with its own corpus |
| Unsupported claims/group | mean 0.065, max 0.239 | low — because most tours lack corpus to check against |

**The corpus is the ceiling.** The low unsupported-claim rate is not a sign of
truthfulness — it is an artefact of having nothing to check claims against
(D94's trap). 24 of 29 real tours have zero stop-level corpus for any stop.
Claims in those tours are **unchecked, not clean**.

---

## 1. Distribution — the shape, not just the mean

### 1a. Style violations (all 84 tours, 2854 groups)

| rule | groups hit | rate |
|---|---|---|
| R1_IMPERATIVE | 797 | **27.9%** |
| R3_SUGGESTIVE_EXPLORATION | 154 | 5.4% |
| R4_PRESCRIBED_FEELING | 101 | 3.5% |
| R7_HALLUCINATED_SENSORY | 68 | 2.4% |
| R9_GENERIC | 62 | 2.2% |
| R8_PROMPT_LEAKAGE | 16 | 0.6% |

**R1 dominates.** More than one quarter of all sentence groups contain an
imperative aimed at the listener. R9 (deletable filler) is rare but is
exactly what Michael scored 0/5.

### 1b. Style distribution across real tours (n=29)

| R1 rate bucket | tours |
|---|---|
| 0–10% | 0 |
| 10–20% | 8 |
| 20–30% | 8 |
| 30–50% | 7 |
| 50–70% | 3 |
| 70%+ | 3 |

**No real tour is R1-free.** The minimum R1 rate across 29 real tours is 7.7%
(Musée d'art naïf, tour 14). The problem is structural, not tour-specific.

### 1c. Corpus coverage across all stops (n=408)

| verdict | stops | % |
|---|---|---|
| EMPTY | 263 | **64.5%** |
| COVERED | 106 | 26.0% |
| VENUE_ONLY | 39 | 9.6% |
| CREATOR_ONLY | 0 | 0% |

Nearly two thirds of all stops across all tours have no corpus whatsoever.
`claim_check` can only report on what it has passages for — for 64.5% of stops,
it cannot flag anything. **Absence of a check is not a pass.**

---

## 2. Worst 10 and Best 10 (real tours only)

Ranking metric: R1 rate + R9 rate×3 + unsupported claims per group. This
surfaces tours with the most style problems and unchecked claims.

### Worst 10

| rank | ID | name | type | R1 | R9 | unsup | coverage |
|---|---|---|---|---|---|---|---|
| 1 | 7 | тур по верховой езде на собаках… | other | 0.86 | 0.00 | 0 | ALL EMPTY |
| 2 | 9 | тур на собачьих упряжках… | other | 0.82 | 0.00 | 1 | ALL EMPTY |
| 3 | 32 | Музей азиатского искусства «Браво»… | other | 0.71 | 0.00 | 3 | ALL EMPTY |
| 4 | 30 | Музей азиатского искусства Alpha… | other | 0.71 | 0.00 | 4 | ALL EMPTY |
| 5 | 22 | Музей азиатского искусства, Ницца… | other | 0.68 | 0.00 | 3 | ALL EMPTY |
| 6 | 151 | Музей современного искусства… | other | 0.40 | 0.00 | 6 | ALL EMPTY |
| 7 | 19 | Музей наивного искусства, Ницца… | other | 0.60 | 0.00 | 0 | ALL EMPTY |
| 8 | 27 | Alpha Asian Arts Museum Nice | museum | 0.25 | 0.04 | 11 | ALL EMPTY |
| 9 | 33 | Musée des arts asiatiques Bravo… | museum | 0.48 | 0.00 | 3 | ALL EMPTY |
| 10 | 152 | French Riviera cycling tour… | cycling | 0.30 | 0.03 | 8 | 9 COV, 4 VEN, 2 EMPTY |

**Pattern:** 7 of the worst 10 are Russian-language tours classified "other" —
they have extreme R1 rates and no corpus. The worst English-language real tour
is tour 27 (Alpha Asian Arts Museum Nice) at rank 8.

### Best 10

| rank | ID | name | type | R1 | R9 | unsup | coverage |
|---|---|---|---|---|---|---|---|
| 1 | 10 | National Constitution Center… | museum | 0.17 | 0.00 | 0 | ALL EMPTY |
| 2 | 14 | Museum Of Naïve Art, Nice… | museum | 0.11 | 0.00 | 3 | ALL EMPTY |
| 3 | 2 | Camel Tour in Abu Dhabi… | museum | 0.13 | 0.00 | 2 | ALL EMPTY |
| 4 | 5 | Camelback riding tour Abu Dhabi… | museum | 0.17 | 0.00 | 0 | ALL EMPTY |
| 5 | 6 | dog ridding tour, Big Lake, AK… | museum | 0.17 | 0.00 | 0 | ALL EMPTY |
| 6 | 17 | restaurants tour old city Nice… | other | 0.26 | 0.00 | 0 | ALL EMPTY |
| 7 | 12 | walking tour in Nice, france… | walking | 0.21 | 0.02 | 1 | 1 COV, 1 VEN, 8 EMPTY |
| 8 | 4 | Camel tour Abu Dhabi… | museum | 0.20 | 0.00 | 4 | ALL EMPTY |
| 9 | 3 | Camelback riding your Abu Dhabi… | museum | 0.29 | 0.00 | 0 | ALL EMPTY |
| 10 | 8 | dog ridding tour, Big Lake, AK… | other | 0.17 | 0.04 | 0 | ALL EMPTY |

**Pattern:** The "best" tours still have 11–29% R1 rates. They score well
because they have fewer imperatives, but even the best real tour has no corpus
to check against. The distinction between "best" and "worst" is mostly style;
truthfulness is unmeasured for both.

---

## 3. By-type split (real tours only)

| type | count | mean R1 | mean R9 | unsup/group |
|---|---|---|---|---|
| cycling | 2 | 0.302 | 0.023 | 0.089 |
| museum | 16 | 0.231 | 0.005 | 0.072 |
| walking | 1 | 0.207 | 0.023 | 0.011 |
| other | 10 | 0.568 | 0.004 | 0.049 |

**"Other" is worst on R1** — at 56.8% mean rate, more than double museum tours.
These are the Russian-language tours plus a few miscategorized ones (the
`detect_tour_type_category` classifier falls back to "other" for non-English
request strings). D107's finding that R1 behaves differently across tour types
is confirmed: museum tours at 23% R1 vs "other" at 57% R1.

**Cycling has the most unsupported claims per group** (0.089) — because it is
also the only type with significant corpus coverage, so `claim_check` actually
has something to measure against.

---

## 4. Corpus as ceiling — per-tour coverage

| coverage state | real tours |
|---|---|
| All stops COVERED | 1 (tour 29, French Riviera Biking Tour — 13 COV, 2 VEN_ONLY) |
| Mixed (some COVERED) | 4 (tours 1, 12, 24, 152) |
| ALL stops EMPTY | **24** |

For those 24 tours with all stops EMPTY:
- `claim_check` cannot flag unsupported claims
- `corpus_coverage` reports EMPTY verdict for every stop
- Any claims the tour makes are **unchecked, not verified**
- No publishability gate would fire because there is nothing to gate against

**D78's finding (MAMAC's two selected stops had no artwork material) is not
unique — it is the overwhelming majority.** Only 5 of 29 real tours have any
corpus at all.

---

## 5. Calibration against Michael's marks (tour 163)

Michael scored tour 163's 11 sentence groups: `5, 1, 3, 3, 2, 1, 1, 5, 1, 0, 0`.
Mean 2.0. "Far from acceptable."

The machine split this tour into **18 groups** (vs Michael's 11). The first 11
machine groups aligned to his marks as follows:

| grp | Michael | classification | machine detects | agree? |
|---|---|---|---|---|
| 0 | **5** | NAVIGATION | no violations | ✓ machine sees it is navigation and correctly exempts |
| 1 | **1** | CONTENT | R1_IMPERATIVE | ✓ "Take the second exit" is an imperative → he scored 1 |
| 2 | **3** | CONTENT | clean | ~ no detection; his 3 was "acceptable if sourced later" |
| 3 | **3** | CONTENT | R1_IMPERATIVE | **✗** machine flags "Look out for" as R1; he scored 3 |
| 4 | **2** | CONTENT | clean | **✗** machine misses; his 2 was for imperative/suggestive tone |
| 5 | **1** | CONTENT | R1_IMPERATIVE | ✓ "Join us as we delve" → imperative, scored low |
| 6 | **1** | CONTENT | clean | **✗** machine misses; his 1 was for R1/R4 violations |
| 7 | **5** | CONTENT | R8_PROMPT_LEAKAGE | **✗** machine wrongly flags; his 5 was for sourced content |
| 8 | **1** | CONTENT | clean (1 unsup) | ~ unsupported detected, but style miss on "allows you to" |
| 9 | **0** | CONTENT | clean | **✗** machine misses; his 0 was R9 (generic, belongs nowhere) |
| 10 | **0** | NAVIGATION | clean | **✗** machine classifies as NAVIGATION; his 0 was "remove it" |

### Where the machine and Michael disagree

| gap | what it means | which criteria we cannot measure |
|---|---|---|
| Group 3: machine flags R1, Michael scores 3 | "Look out for" is borderline; he accepts it as guidance | R1 detector is too aggressive on observational imperatives |
| Group 4: machine says clean, Michael scores 2 | "embark on a journey… delve into the timeless elegance" — he reads suggestive/instructive | R3/R4 detection misses metaphorical imperatives ("embark", "delve") |
| Group 6: machine says clean, Michael scores 1 | "Walking through… may evoke the scent" — prescribed feeling | R4 detection misses conditional prescriptions ("may evoke") |
| Group 7: machine flags R8, Michael scores 5 | "One concrete sensory detail" is prompt leakage for us; he valued the facts (Monet, Maupassant) | R8 may over-fire when the content around it is sourced and good |
| Group 9: machine says clean, Michael scores 0 | "The nearby Abri de l'Olivette" with no connection to anything | R9 (generic) needs to fire on context-free facts, not just platitudes |
| Group 10: machine says NAVIGATION, Michael scores 0 | "Pedal along the coastline, envisioning…" — he reads filler | Navigation classification is too broad: movement verb + filler ≠ real directions |

### Summary of calibration

- **Agreements:** 4 of 11 (36%) — groups 0, 1, 5, and partially 8.
- **Machine too harsh:** 2 (groups 3, 7) — flags that contradict his score.
- **Machine too lenient:** 5 (groups 4, 6, 9, 10, and partially 2) — misses what he caught.

**The most useful output:** The machine currently catches ~36% of what Michael's
ear catches. Its biggest blind spot is **soft imperatives and metaphorical
instructions** (groups 4, 6) that R1's pattern list does not cover, and
**context-free content that is technically specific but contributes nothing**
(group 9) that R9's generic detector does not reach.

---

## 6. Limitations

1. **Row count.** The task expected 133 rows; actual is **138**. The 5 extra rows
   are test tours created between when the task was specified and when this
   profiling ran. The Nice list `[1,12,14,17,21,24,27,28,29,152]` is verified
   intact.

2. **Unsupported claim measurement is unreliable for most tours.** 24 of 29 real
   tours have ALL stops EMPTY — `claim_check` has no passages to compare against,
   so it reports zero unsupported claims. This is absence of measurement, not
   absence of problems.

3. **No i-con score computed.** Michael has not set the floors (§7), and a number
   invented now would be re-litigated (D102). This report provides the inputs:
   rule rates, claim verdicts, group counts, coverage verdicts.

4. **Group boundary agreement with Michael: 54.5%** (D102). The machine over-splits —
   18 groups for his 11. This means the per-group rates above are computed over more
   groups than Michael would draw, slightly diluting per-group rates.

5. **R1 detection sensitivity.** The calibration shows R1 both over-fires (group 3,
   "Look out for") and under-fires (groups 4, 6 — metaphorical imperatives). The
   net result is approximately correct aggregate rates but imprecise per-sentence
   verdicts.

6. **Tour type classification is crude.** Non-English request strings fall to "other",
   which inflates that category. The Russian-language museum tours are functionally
   identical to their English counterparts but classified differently.

---

## Data files

- `quality_profile_data.json` — per-tour raw data (all 84 profiled tours)
- `QUALITY_PROFILE.md` — this document
