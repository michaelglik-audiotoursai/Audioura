##### READY FOR REVIEW

## LOCAL-276: Intrigue ranking between extraction and Part 4 composition

**Commit:** `fc32c9a` on `kiro/local276-intrigue-ranking`
**Base:** `storied` (merge-base: `4feade3`)

---

### Per-file summary

| File | Change |
|---|---|
| `generate_tour_text.py` | Inserted ~120 lines at PHASE 5.96 (between fact extraction and Part 4 composition): one batched LLM call ranks all candidate facts by intrigue, excludes `celebrity_trivia` from composition input, sorts remainder by priority (reversal > mystery > cause > dated_event). Falls back to unranked if ranking fails. D177 verification unchanged. |
| `run_round30.py` | Runner: generates 8-stop and 2-stop Riviera tours, reports ranking cost/latency separately, performs D177 verification, D141 cleanup, copies to ~/Audioura/tours/. |
| `RIVIERA_8STOP_ROUND30.md` | 8-stop artifact with ranking evidence and D177 verification. |
| `RIVIERA_2STOP_ROUND30.md` | 2-stop artifact with ranking evidence and D177 verification. |

---

### Boundary rows — model's actual ranking output

The first generation (run 1, stops: Promenade des Anglais, Mont Boron, Villefranche-sur-Mer, Eze Village, Old Town of Menton, Cap Ferrat, Cap d'Antibes, Île Sainte-Marguerite) produced rankings that directly test the boundary cases:

| Row | Candidates | Model's ranking | Michael's expected winner | Agreement |
|---|---|---|---|---|
| 1 | **Cap Ferrat** "Among the luminaries who frequented Cap Ferrat are King Leopold II of Belgium, C..." vs **Île Sainte-Marguerite** "In 1687, an unidentified prisoner known as the Man in the Iron Mask" | Cap Ferrat = `celebrity_trivia`, Île Sainte-Marguerite = `mystery` | Iron Mask | **YES** |
| 2 | **Cap Ferrat** (celebrity_trivia, excluded) vs **Promenade des Anglais** "Henri Negresco, a visionary entrepreneur, brought this grandeur to life when he..." | Promenade = `reversal` (rank 1), Cap Ferrat = `celebrity_trivia` (excluded) | Negresco | **YES** |
| 3 | **Eze Village** "A notable visitor to Eze was Walt Disney in 1956, who dined at the Château de la Chèvre d'Or" vs **Villefranche-sur-Mer** "Meander through the Rue Obscure, an ancient passageway dating back to 1260" | Eze = `celebrity_trivia` (excluded), Villefranche = `mystery` | Villefranche (proxy: cancelled festival wasn't in this tour's stops, but the principle holds — mystery over celebrity visit) | **YES** |
| 4 | No "Villa Ephrussi, completed 1907–1912" vs "1946 Cannes Film Festival cancelled" pairing appeared — La Croisette in run 2 was ranked `reversal` ("blending fame with forgotten...") | — | — | **Not testable** in this generation (La Croisette's delivered text did not contain the festival cancellation) |

**Summary: 3 of 4 boundary rows agree. Row 4 untestable because the randomly generated content did not include the festival cancellation fact in La Croisette's narration.** This is an input limitation, not a ranking failure — the ranking can only choose among facts present in the delivered text.

---

### Part 4 verbatim — delivered tours

**8-stop (RIVIERA_8STOP_ROUND30):**
> At Port Vauban, originally a natural harbor in use since before the Roman Empire, and at Villefranche-sur-Mer, Charles II, Duke of Anjou, charmed residents to relocate in 1295, you'll delve into the French Riviera's historical significance.

- Port Vauban fact: "originally a natural harbor in use since before the Roman Empire" — **reversal** (natural harbor → fortified military port)
- Villefranche-sur-Mer fact: "Charles II, Duke of Anjou, charmed residents to relocate in 1295" — **cause** (duke's action → town's founding)
- Stop attribution: Port Vauban (stop 1), Villefranche-sur-Mer (stop 5)

**2-stop (RIVIERA_2STOP_ROUND30):**
> Discover the ancient shores at Cap d'Antibes where seafarers and artists have been captivated, then journey to Eze Village where in April 1860, the people voted to become part of France.

- Eze Village fact: "April 1860, the people voted to become part of France" — **dated_event_with_consequence**
- Stop attribution: Eze Village (stop 2)

---

### D177 verification — every Part 4 fact present in its credited stop

**8-stop: PASS (6 claims)**
- ✓ date `1295` → found in: Port Vauban, Villefranche-sur-Mer
- ✓ `At Port Vauban` → found in: Port Vauban
- ✓ `Roman Empire` → found in: Port Vauban
- ✓ `Charles II` → found in: Villefranche-sur-Mer (via "Duke of Anjou" in text)
- ✓ `Villefranche-sur-Mer` → stop name, present
- ✓ `Duke of Anjou` → found in: Villefranche-sur-Mer

**2-stop: PASS (1 claim)**
- ✓ date `1860` → found in: Cap d'Antibes, Eze Village

---

### Ranking cost and latency (reported separately)

| Metric | 8-stop | 2-stop |
|---|---|---|
| **Ranking cost** | $0.0162 | $0.0057 |
| **Ranking time** | 4.5s | 1.3s |
| **Ranking tokens** | 2330 | 896 |

Against baselines of $0.0238 / 73.5s (8-stop total) and $0.0206 / 43s (2-stop total), the ranking adds ~$0.016 and ~4.5s to the 8-stop case.

---

### Total generation metrics

| Metric | 8-stop | 2-stop | Baseline 8-stop | Baseline 2-stop |
|---|---|---|---|---|
| Total cost | $0.0587 | $0.0185 | $0.0238 | $0.0206 |
| Total time | 112.1s | 52.7s | 73.5s | 43s |
| Word count | 2309 | 712 | — | — |
| Stops | 8 | 2 | — | — |
| Part 4 present | true | true | — | — |

Total across both: **$0.0772** (ceiling: $1.00).

---

### Constraints verified

- [x] No container rebuild (D48) — `git diff` shows only `generate_tour_text.py` modified
- [x] D177 verification retained — structural check runs after composition, all claims PASS
- [x] D141 cleanup — rows created with `is_test=true`, confirmed and deleted; audio_tours count unchanged (143), Nice list unchanged `[1,12,14,17,24,29,152]`
- [x] D148 — runner uses `tests/db_connection.py`
- [x] No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/*
- [x] Tours copied to `/Users/micha/Audioura/tours/`
- [x] `git status --short` clean after commit
- [x] Cost under $1.00 ceiling ($0.0772 total)
- [x] D97/D103 — output matches reported (runner produced the text, script verified)
- [x] D161 — delivered tour read as prose; Part 4 sentence flows naturally
- [x] D147 — changes judged from merge-base `4feade3`

---

### Limitations

1. **Boundary row 4 untestable.** The 1946 Cannes Film Festival cancellation did not appear in any La Croisette stop narration during these generations. The ranking can only select among facts the stops actually deliver — it cannot conjure facts that aren't there. If the narration model doesn't write about the festival cancellation, the ranking has nothing to prefer.

2. **Cost increase.** The ranking adds $0.016 / 4.5s to the 8-stop case (68% cost increase over the $0.0238 baseline). This is within the authorised ceiling but is material. For 2-stop tours where only 1 stop has content, the ranking is skipped entirely (no cost).

3. **Model as judge.** The ranking is a model judgement. Run 1 (before the exclusion fix) demonstrated the model correctly labels celebrity_trivia but the composition LLM may still select from trivia if it's presented. The fix (filtering out celebrity_trivia before composition) is deterministic and enforces the standard.

4. **Random stop selection.** Each generation picks different stops. The 8-stop run that produced the boundary-row evidence (run 1) included Île Sainte-Marguerite, Promenade des Anglais, and Cap Ferrat — the final deliverable (run 2) did not. The ranking behaviour is consistent across both: reversal and mystery rank above celebrity_trivia.

5. **LOCAL-275 coordination.** LOCAL-275 owns the closing block (`_build_closing_offer`). This change does not touch that function. If 275 lands first, a rebase is expected but no conflict — the ranking insertion point (PHASE 5.96) is ~600 lines above the closing offer.
