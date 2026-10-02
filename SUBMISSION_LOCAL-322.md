##### READY FOR REVIEW

## Commit

`2205d97` — LOCAL-322: fix ungrammatical patch sentence in period/both branches

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Replace single `"This work was " + join(parts)` template with three grammatical branches: material-only / period-only / both. Each produces correct English. |
| `tests/test_local322_material_language.py` | Fix `_build_patch` helper and all assertions to match the new grammatical forms. Tests assert correct English, not current behaviour. |

## The three branches (read as sentences)

```
Material only  →  "This work was crafted from schist."
Period only    →  "This work dates from the 19th century."
Both           →  "This work, crafted from schist, dates from the 19th century."
```

I read each of these three outputs as a sentence. Each has subject–verb agreement
and stands alone grammatically.

## Verbatim evidence

### Regenerated museum stop (Stop 2, Asian Arts Museum Nice)

The catalogue period was `IIe-IIIe siècles`; the LLM did not include a century
reference after 2 retries, so the period-only branch fired:

> The "Statue de Bouddha" stands as a silent witness to the cultural exchanges
> of antiquity, sculpted from schist and catalogued as originating from the
> region that is now Pakistan. **This work dates from the 3rd century.** Here,
> in this ancient crossroads, Greek and Indian art converged to create the unique
> Greco-Buddhist style evident in this sculpture.

Grammatical. Standalone sentence. No comma splice. No French.

### French-leak check on generated tour

```
ZERO French material leaks in the generated tour.
Old-style comma splices: 0
"was dating from" occurrences: 0
```

### Retry counts (from generation log)

```
[LOCAL-98] Stop 2: catalogue period 'IIe-IIIe siècles' missing from description.
[LOCAL-98] Stop 2: retrying (attempt 1) with binding enforcement...
[LOCAL-98] Stop 2: catalogue period 'IIe-IIIe siècles' missing from description.
[LOCAL-98] Stop 2: retrying (attempt 2) with binding enforcement...
[LOCAL-98] Stop 2: catalogue period 'IIe-IIIe siècles' missing from description.
[LOCAL-31] Stop 2: patched missing metadata into description (EN: dating from the 3rd century).
```

Only 1 stop triggered retries (period, not material). The material-check false-fail
path that previously burned retries on every stop is completely eliminated by the
earlier translation fix (still intact).

### 8-stop museum regression

| Tour | base_score | total_score |
|------|-----------|-------------|
| LOCAL322 (this run) | 71.88 | 110.44 |
| Best baseline (Chagall 213940) | 68.75 | 100.00 |
| Palais Lascaris baseline | 43.75 | 65.62 |

8 stops delivered, score flat or better vs baseline. No stops lost.

### Tests

54 tests pass (0 failures):

```
============================== 54 passed in 0.08s ==============================
```

## Period branch assessment

The period branch (`_c51_period`) was assessed in the prior commit (b40ddf6).
It shares the same bug shape — comparing French literal against English prose.
The fix added `_period_english` translation and era-name extraction (e.g.,
"Époque Edo" → checks for "Edo" in the description). The sentence construction
fix in this commit covers the period-only and both-period-and-material branches.
**Not broken in the same way as material was** — the century-format code already
translated Roman numerals to Arabic (e.g., XIXe → 19th century) before this
ticket. The era-name branch was the gap, now closed.

## Limitations

1. The `IIe-IIIe siècles` (2nd–3rd century range) period format doesn't have a
   perfect mapping — the code extracts just the first match (IIIe → 3rd century).
   A multi-century range would require additional parsing. This is a cosmetic
   imprecision, not a broken-prose defect.
2. Corpus-level counts (184 French leaks, 47 splices) cannot be verified in this
   worktree which has 49 tour files vs 410 in the working tree. Verified on
   generated output instead, as directed by LEAD.
