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

### Filters and group count

The machine splits this tour into **18 groups** across 6 paragraphs (2 stops).
Paragraph minimum length: `> 50` chars. Sentence minimum: `>= 10` chars. The
only sentence excluded by a `> 60` filter would be "Enjoy the refreshing sea
breeze along the way." (46 chars); it passes our `>= 10` threshold and sits
inside a group with "Take the second exit…" — excluding it does not change the
group count. **18 groups is the reproducible result from `storied` HEAD.**

Across all 84 profiled tours, the `> 50` paragraph filter includes 39 groups
(1.4% of 2854) that a `> 60` filter would exclude. This shifts all §1 rates by
< 0.5 percentage points — negligible; the reported rates stand.

### The mapping error in the original submission

The original §5 aligned machine groups 0–10 with Michael's 11 marks 1:1. **This
was wrong.** Michael groups the content differently: his groups span multiple
machine groups. The machine over-splits (18 vs his 11), so a 1:1 alignment puts
the wrong text against his scores.

Critically: the original table reported his 0/5 groups (indexed 9, 10) as
machine groups 9 and 10 and said they were "clean." In reality:

- Machine group 9 = "The nearby Abri de l'Olivette…" — **not** what he scored 0.
- Machine group 10 = "Pedal along the coastline…" — **not** what he scored 0.
- His group 9 (score 0) = "As you continue your journey…" = **machine group 16**, where **R9 fires.**
- His group 10 (score 0) = "From Cap d'Antibes to Villefranche…" = **machine group 17**, where **R9 fires.**

**R9 detects both of his 0/5 sentences correctly.** The original table told
Michael the opposite — that the one thing demonstrably working did not work.

### Correct side-by-side

Michael's 11 groups mapped to the machine's 18 (many-to-one):

| M# | Michael | Machine grps | Machine detects | Agree? |
|---|---|---|---|---|
| 0 | **5** | 0, 1 | NAVIGATION + R1_IMPERATIVE | ✓ machine sees navigation; R1 on "Take second exit" is moot (navigation exempt) |
| 1 | **1** | 2, 3 | R1_IMPERATIVE | ✓ "Look out for" → R1 fires. He scored 1 for the same reason |
| 2 | **3** | 4, 5 | R1_IMPERATIVE | ~ "Join us as we delve" flags R1; his 3 was conditional on later delivery |
| 3 | **3** | 6, 7, 8 | R8_PROMPT_LEAKAGE | **✗** R8 fires on "One concrete sensory detail…" — he valued the Monet/Maupassant facts around it |
| 4 | **2** | 9, 10 | clean (grp 10 = NAVIGATION) | **✗** machine misses; his 2 was for imperatives ("take in", "Pedal", "envisioning") without substance |
| 5 | **1** | 11 | clean | **✗** machine misses; "pause to take in" is R1/R4 that the pattern list does not cover |
| 6 | **1** | 12 | R1_IMPERATIVE | ✓ "Look for the Rue Obscure" → R1 fires. He scored 1 for the same reason |
| 7 | **5** | 13 | clean | ✓ No violations. His 5/5 — specific, informative, no instructions |
| 8 | **1** | 14, 15 | clean | **✗** machine misses; "may evoke the scent", "whispers tales", "adds depth to your understanding" |
| 9 | **0** | 16 | **R9_GENERIC** | ✓ "As you continue your journey…" — R9 fires, correct |
| 10 | **0** | 17 | **R9_GENERIC** | ✓ "From Cap d'Antibes to Villefranche…" — R9 fires, correct |

### Where the machine and Michael disagree

| gap | what it means | which criteria we cannot yet measure |
|---|---|---|
| Group 3: machine flags R8, Michael scores 3 | "One concrete sensory detail" is prompt leakage; he valued the sourced facts (Monet, Maupassant) alongside it | R8 over-fires when the group contains good content around the leaked phrase |
| Group 4: machine says clean, Michael scores 2 | "Pedal along the coastline, envisioning…immersing yourself" — he reads suggestive/instructive filler | R3/R4 misses metaphorical imperatives ("envisioning", "immersing yourself") and the navigation classifier is too broad (movement verb + filler ≠ real directions) |
| Group 5: machine says clean, Michael scores 1 | "pause to take in the breathtaking view" — prescribed feeling + imperative | R1/R4 misses "pause to take in" pattern; "breathtaking" is prescribed feeling |
| Group 8: machine says clean, Michael scores 1 | "may evoke the scent", "whispers tales of a bygone era", "adds depth to your understanding" | R4 misses conditional prescriptions ("may evoke") and personification-as-filler ("whispers tales"). R3/R1 miss "adds depth to your understanding" |

### Summary of calibration

- **Agreements:** 6 of 11 (55%) — groups 0, 1, 2 (partial), 6, 7, 9, 10.
- **Machine too harsh:** 1 (group 3) — R8 flags prompt leakage in a group he scored 3.
- **Machine too lenient:** 4 (groups 4, 5, 8, and partially 2) — misses what he caught.

**Key finding: R9 works perfectly on his 0/5 sentences.** LOCAL-216 verified
this, LOCAL-222 watched it delete those sentences in generation, and the
calibration now confirms it from the profiling path. Zero disagreements on the
two cases Michael cared about most.

**The remaining blind spots** are soft imperatives and prescribed feelings that
use vocabulary outside R1's explicit pattern list: "pause to take in", "may
evoke", "envisioning", "immersing yourself", "adds depth to your understanding."
These are R1/R3/R4 detection gaps — the rules exist but the pattern coverage is
incomplete for conditional and metaphorical forms.

### Discrepancy with LEAD's reported group count

LEAD's bounce reported `total groups: 24` for tour 163. **This cannot be
reproduced.** Running `parse_tour_stops` → `split_into_sentence_groups` on
`storied` HEAD (commit `ceb88ec`, the only version of this code that has ever
existed) produces 18 groups consistently. Possible explanations:

1. LEAD counted individual sentences with `len > 60` (= 27) minus directions
   (= ~24), conflating "sentence" with "group."
2. LEAD ran a different content parsing (including Directions gives 21, still
   not 24).
3. LEAD's `24` is itself a reporting error.

The important conclusion holds regardless: **R9 fires on the last two groups
(whatever the total), and those are the sentences Michael scored 0.** The
mechanism of the original §5 error (1:1 alignment of mismatched group counts)
is the finding — not the specific total.

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

5. **Paragraph filter: `len > 50`.** The profiling includes paragraphs > 50 chars.
   A `> 60` filter would exclude 39 of 2854 groups (1.4%). This does not
   materially change the §1 rates (< 0.5pp shift). The sentence-level filter is
   `len >= 10`, which excludes only trivial fragments.

6. **R1 detection sensitivity.** The calibration shows R1 under-fires on
   metaphorical imperatives and conditional forms (groups 4, 5, 8 — "pause to
   take in", "may evoke", "envisioning"). The net result is approximately
   correct aggregate rates but per-sentence precision is incomplete.

7. **Tour type classification is crude.** Non-English request strings fall to "other",
   which inflates that category. The Russian-language museum tours are functionally
   identical to their English counterparts but classified differently.

---

## Data files

- `quality_profile_data.json` — per-tour raw data (all 84 profiled tours)
- `QUALITY_PROFILE.md` — this document
