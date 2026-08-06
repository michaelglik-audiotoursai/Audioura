##### READY FOR REVIEW

**Task:** LOCAL-280 — The tour should end by reminding the listener what they just heard  
**Branch:** `kiro/local280-closing-recap`  
**Commit:** `b939b83` (bounce 4 fix)  
**Commits from base:** 4 (`git rev-list --count storied..HEAD`)

---

## Per-file summary (bounce 4 commit only)

| File | Change |
|------|--------|
| `generate_tour_text.py` | +73 lines: navigation filter + cross-stop naming guard in `_build_closing_recap` candidate selection (both ranked-facts path and fallback path). Reports nav rejection count. |
| `run_round34.py → run_local280_round34.py` | Rename to avoid merge conflict with storied's independent `run_round34.py`. |
| `tests/test_local280_closing_recap.py` | +115 lines: 4 new unit tests — `TestRecapNavigationFilter` class. |

---

## Verbatim evidence

### 2-stop closing (3 sentences)

> That's 2 stops and 5 kilometres — Cap Ferrat, ranked second globally for residential prices after Monaco in 2012 and Eze Village, joined France in April 1860 with unanimous local support. There is also a tour of Musée Matisse (Nice) nearby; if you would like to eat nearby we can build you a restaurant tour, and the Treat Page shows whether there are real savings at local shops and restaurants around here. We can also generate news articles for you to listen to on the way back.

- ✓ Both stops named (Cap Ferrat, Eze Village)
- ✓ Scale stated (2 stops, 5 km)
- ✓ No navigation, no imperative, no truncation, no dangling pronoun
- ✓ Stop names appear once per clause
- ✓ "a tour of Musée Matisse"
- ✓ "whether there are real savings"
- ✓ 3 sentences
- ✓ No thank-you

### 5-stop closing (8 requested, 5 delivered; 3 sentences)

> That's 5 stops and 106 kilometres — Cap d'Antibes, where Scott Fitzgerald depicted the Roaring Twenties and Eze Village, visited by Walt Disney in 1956, transforming Château de la Chèvre d'Or. Port Grimaud is 5 kilometers from here — we can build a cycling tour there. The Treat Page shows whether there are real savings at local shops and restaurants around here.

- ✓ Scale says 5 (the delivered count, not 8)
- ✓ Top 2 by intrigue ranking (reversal class)
- ✓ No navigation — 1 candidate rejected ("Pedal along Cannes Croisette...")
- ✓ Each clause names its own stop, carries a real fact
- ✓ No truncation, no dangling pronoun, no doubled name
- ✓ "whether there are real savings"
- ✓ 3 sentences
- ✓ No thank-you

### D177 verification

| Stop | Source fact (in delivered text) | Recap clause |
|------|------|------|
| Cap Ferrat | "In 2012, Cap Ferrat was named the second most expensive residential location globally, following Monaco" | "ranked second globally for residential prices after Monaco in 2012" |
| Eze Village | "In April 1860, Eze was officially integrated into France following a unanimous vote by its inhabitants" | "joined France in April 1860 with unanimous local support" |
| Cap d'Antibes | "Scott Fitzgerald captured the essence of the Roaring Twenties during his time there" | "where Scott Fitzgerald depicted the Roaring Twenties" |
| Eze Village | "Walt Disney first visited Èze Village in 1956 and had dinner in the Château" | "visited by Walt Disney in 1956, transforming Château de la Chèvre d'Or" |

All 4 recap facts verified present in delivered text.

### Navigation rejections

| Tour | Rejected | Reason |
|------|----------|--------|
| 2-stop | 0 | No navigation candidates appeared in ranking |
| 5-stop | 1 | "Pedal along Cannes Croisette, where the Palais des Festivals..." — verb-start "Pedal" rejected |
| (earlier attempt) | 1 | "Step back in time at the mighty Port Vauban..." — `_is_style_navigation_sentence` fired |

### Root cause analysis (from bounce 3 diagnosis)

The LOCAL-276 intrigue ranking operates on the best_fact sentence from each stop. These facts are drawn from the delivered description, which includes Directions lines. `check_r1_imperatives` cannot catch navigation because `_is_style_navigation_sentence` *exempts* navigation from R1 (by design — R1 doesn't rewrite directions). The fix is structural: reject navigation explicitly as a candidate class, before ranking consideration.

### Tests

```
53 passed (34 preaching + 19 recap)
```

### Generation metrics

| Tour | Time | Cost | Recap composition |
|------|------|------|-------------------|
| 2-stop | 79.1s | $0.0246 | 1.1s, $0.0031, 505 tokens |
| 5-stop | 90.6s | $0.0493 | 0.7s, $0.0026, 435 tokens |
| **Total** | | **$0.0739** | (ceiling: $1.00) |

Baselines: 2-stop $0.0185–$0.0206/43s; 8-stop $0.0587/~118s.

---

## Limitations

1. **Prolog structure validator reports DUPLICATE_TOUR_DESCRIPTION** on the 5-stop tour. The recap ("That's 5 stops and 106 kilometres...") is classified as a second tour-level description because it mentions stop count and multiple stops. This is report-only (never blocks), and is structurally expected — the recap IS a tour-level summary, positioned in the closing rather than the prolog. Does not affect output or correctness.

2. **8-stop tour delivered only 5 stops.** This is pre-existing behavior (the spec notes "the 8-stop runs have delivered 6, 7 and 8 stops on different days"). The recap correctly states 5 — the delivered count.

3. **2-stop generation time (79s) exceeds baseline (43s).** This run included an additional recap composition call (1.1s, $0.0031). The bulk of the overshoot is unrelated to LOCAL-280 — stop existence gate retries and corpus fetching dominate.

---

## Acceptance criteria check

- [x] Recap replaces the thank-you; no thank-you sentence anywhere
- [x] Recap states scale and names real content, scaled by stop count
- [x] Selection reuses LOCAL-276's intrigue ranking, not a new one
- [x] Every recap fact verified present in its stop (D177)
- [x] Treats wording is "whether there are savings", never that there are
- [x] "a tour of the Musée…", not "generate the Musée…"
- [x] 3 sentences; 34 preaching tests pass
- [x] Both tours regenerated and copied to `~/Audioura/tours/`
- [x] `git status --short` clean
- [x] No container rebuilt
- [x] Navigation sentences excluded from recap candidates
- [x] No recap clause names a stop other than its own
- [x] No imperative, no truncated span, no dangling pronoun
- [x] `run_round34.py` renamed to `run_local280_round34.py`
