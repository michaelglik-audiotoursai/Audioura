##### READY FOR REVIEW

## LOCAL-36: Practical Facts QA Gate

### What was built

A provenance-based QA gate for practical visitor information (hours, closing days, admission prices) that verifies every claim against its fetched source content. Claims without traceable source are **dropped** — silence is correct; a plausible guess is not.

### Components

| File | Purpose |
|------|---------|
| `practical_facts_gate.py` | Core gate module: extraction → verification → strip |
| `tests/test_local36_practical_facts_qa.py` | 26-test suite (all pass) |
| `content_qa_runner.py` | Audit reporting integration (non-blocking) |
| `generate_tour_text.py` | Pipeline integration (provenance tracking + gate call) |

### Design decisions

1. **Provenance, not plausibility.** The gate does not judge whether "Open 10am-6pm" sounds reasonable — it verifies the source page actually says that.

2. **Fail-closed.** If no source text is available, ALL practical claims are dropped. No source = no claims shipped.

3. **Per-claim audit log.** Format: `claim_type | value | source_url | VERIFIED/DROPPED`. One line per claim, human-reviewable without re-reading the tour.

4. **Cross-language verification.** Claims translated from French ("Fermé le mardi" → "Closed on Tuesdays") verify against the original French source via day-name mapping.

5. **No weakening of existing gates.** The practical facts gate is orthogonal to the content_qa_runner's 8-check style/factual score. It cannot reduce the base score.

### Acceptance evidence

#### 1. Gate running over all three venues (per-claim audit)

**Asian Arts Museum** — PASSED (2 verified, 0 dropped):
```
closed_day | Open daily from 10am to 6pm, closed on Tuesdays | https://maa.departement06.fr/infos-pratiques | VERIFIED
admission  | Free admission | https://maa.departement06.fr/infos-pratiques | VERIFIED
```

**Musée Matisse** — FAILED → claim dropped (2 verified, 1 dropped):
```
hours      | Open from 10am to 6pm | https://musee-matisse-nice.org/tarifs-et-horaires | VERIFIED
closed_day | Closed on Tuesdays | https://musee-matisse-nice.org/tarifs-et-horaires | VERIFIED
admission  | Admission fee required | https://musee-matisse-nice.org/tarifs-et-horaires | DROPPED — not supported by source
```
*Note: Source says "Tarif plein : 10 €" — the vague "Admission fee required" is stripped. The correct behaviour would be to emit "Admission: €10" or nothing.*

**Palais Lascaris** — PASSED (1 verified, 0 dropped):
```
closed_day | Open daily from 10am to 6pm, closed on Tuesdays | https://www.nice.fr/...palais-lascaris-702 | VERIFIED
```

#### 2. Deliberate negative test (unsourced claim injected)

Test: `TestInjectedUnsourcedClaim::test_injected_claim_dropped`
- Injected "Open from 9am to 9pm" (source says 10h-18h)
- **Result:** Gate FAILED — hours claim DROPPED ✓

#### 3. Deliberate positive test (correctly sourced claim passes)

Test: `TestVerificationPositive::test_hours_10_to_6_verified`
- Claim: "Open daily from 10am to 6pm"
- Source: "Du 2 mai au 15 octobre : 10h – 18h"
- **Result:** VERIFIED ✓

#### 4. Three consecutive runs per venue — stability

```
Asian:   STABLE (2 claims, 3 runs identical)
Matisse: STABLE (3 claims, 3 runs identical)
Palais:  STABLE (1 claims, 3 runs identical)
```

Sourced facts do not vary between runs. The extraction is deterministic.

#### 5. No regression

```
tests/test_local30_deterministic_selection.py  — 12 passed
tests/test_local31_metadata_bind.py            — 22 passed
tests/test_local36_practical_facts_qa.py       — 26 passed
Total: 60 passed, 0 failed
```

Content QA scores unchanged:
- Palais Lascaris: 17/19 (style+factual) — QA PASSED
- Matisse: 18/19 (style+factual) — QA PASSED

#### 6. Full test run (verbatim exits)

```
$ python3 -m pytest tests/test_local36_practical_facts_qa.py -v
26 passed in 0.06s

$ python3 -m pytest tests/test_local30_deterministic_selection.py tests/test_local31_metadata_bind.py -v
34 passed, 1 warning in 0.13s
```

### How it catches the original bugs

| Bug | What happened | What the gate does |
|-----|---------------|-------------------|
| Fabricated hours varying between runs | GPT invented "closed Mondays" / "closed Tuesdays" | No source → claim dropped entirely |
| Matisse "Free" when actually €10 | GPT hallucinated free admission | Source says €10 → "Free" fails verification → dropped |
| "Admission fee required" (vague) | Pipeline emitted imprecise claim | Source has specific €10 → vague claim fails → dropped |

### Sequencing note

LOCAL-35 (correct the values) has not landed yet. This gate (LOCAL-36) is designed to work with or without LOCAL-35:
- **Without LOCAL-35:** The gate drops unsupported claims (defensive)
- **With LOCAL-35:** The gate verifies the corrected values are properly sourced (constructive)

The gate does not duplicate LOCAL-35's extraction work. It operates on the output text post-generation.
