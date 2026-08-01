##### READY FOR REVIEW

# LOCAL-85: Venue-Coherence Gate Fix

**Commit:** `b3e606e`  
**Branch:** `kiro/local85-venue-coherence-gate`  
**Ahead of storied:** 1 commit

---

## Changes (per-file)

| File | Lines | Purpose |
|------|-------|---------|
| `content_qa_runner.py` | +42/−4 | Replace check 11 substring-count heuristic with negative-drift detection |
| `tests/test_local85_venue_coherence.py` | +218 (NEW) | 8 tests: 3 PASS cases, 3 FAIL cases, 2 cap-consistency proofs |
| `docker-compose-local85.yml` | +33 (NEW) | Testing compose file for LOCAL-85 container |

---

## The Problem

Check 11 (BLOCKER4c venue coherence) required `≥ len(stops)//3` stops to contain `_tour_venue.lower()[:15]` as a literal substring. For "Musée Matisse, Nice", that's `"musée matisse, "` (15 chars including comma and space). The LLM writes "Musée Matisse" or "the museum" — only rarely "Musée Matisse, Nice" with the city suffix. So the gate fired as a FACTUAL failure, blocking delivery of a correct tour.

Meanwhile, LOCAL-47's `cap_location_repetition` limits venue-name occurrences to max 2 for non-museum tours. The two rules pulled in opposite directions: one demanded repetition, the other capped it.

## The Fix

**Old rule (removed):** Fail if fewer than `len(stops)//3` stops contain the first 15 chars of the venue name.

**New rule:** Fail if **more than** `len(stops)//2` stops name a *foreign* venue (using the existing `_NAMED_VENUE_PATTERN` regex from check 9). A stop is "drifted" only if it contains a named venue reference that does NOT match the tour's own venue name.

This catches genuine drift (a "Musée Matisse" tour whose stops are actually about the British Museum) while never penalizing natural prose that omits the full venue string.

## Reconciliation with LOCAL-47 Repetition Cap

| Rule | Requires | Permits |
|------|----------|---------|
| LOCAL-47 cap | — | ≤ 2 occurrences of venue name |
| LOCAL-85 coherence gate (new) | 0 mentions (negative test only) | Unlimited mentions |

The two rules are now **orthogonal**: the coherence gate fires on *positive evidence of drift* (foreign venues named), never on *absence of the venue name*. A tour with 0 mentions of the venue name passes the coherence gate. A tour with 2 mentions passes the repetition cap. These constraints can always be satisfied simultaneously.

---

## Evidence: Musée Matisse — 8/8 stops, DELIVERED

**Job:** `e10d8fd9-a7e1-45fc-abcb-dba436564fc3` | **Tour ID:** 54 | **Cost:** $0.067

```
Stop 1: Nu bleu IV
Stop 2: Nymphe dans la forêt
Stop 3: Tempête à Nice
Stop 4: Pierre Matisse, un marchand d'art à New York
Stop 5: Odalisque au coffret rouge
Stop 6: Lectrice à la table jaune
Stop 7: Nature morte aux grenades
Stop 8: Papeete-Tahiti
```

**Museum Information:** `Closed on Tuesday. 10:00–17:00 (1 Nov–31 Mar); 10:00–18:00 (1 Apr–31 Oct). €12; free for Métropole residents`

**QA Result (from container BLOCKER4c):**
```
PASS: Venue coherence (stops reference correct venue)
```
**QA Result (standalone):** Score 17/20, QA PASSED

---

## Evidence: Deliberately Drifted Tour — REJECTED

Constructed tour: title says "Musée Matisse, Nice" but all 8 stops describe the British Museum (Elgin Marbles, Rosetta Stone, Sutton Hoo, etc.).

```
FAIL: Venue coherence (stops reference correct venue) — 8/8 stops reference a foreign venue (threshold: >4)
FACTUAL INTEGRITY FAILED (2 factual check(s) failed) — RELEASE BLOCKED
```

Exit code: 1 ✓

---

## Evidence: Asian Arts Museum — 8/8 stops, no regression

**Job:** `8d2ddcb0-a0d8-4b03-8ec8-8fb848c1dd15` | **Tour ID:** 55 | **Cost:** $0.063

```
Stop 1: L'Armure d'Andô Naoyuki
Stop 2: Statue de Bouddha
Stop 3: La danse cosmique de Ganesh
Stop 4: Kannon, le bodhisattva de la compassion
Stop 5: Ulysses Grant au Japon
Stop 6: Robe de prêtre taoïste
Stop 7: Kannon à mille bras
Stop 8: Masque du vieillard kojô
```

**Museum Information:** `Closed on Tuesday. 10:00–17:00 (1 Sep–30 Jun); 10:00–18:00 (1 Jul–31 Aug). FREE`

**QA Result:** Score 18/20, QA PASSED  
**"Closed on Tuesday":** ✓ preserved

---

## Evidence: Cost Ceiling

| Tour | Cost | Ceiling |
|------|------|---------|
| Matisse | $0.067 | < $1.30 ✓ |
| Asian Arts | $0.063 | < $1.30 ✓ |

Both within measured baseline ($0.063–$0.073).

---

## Evidence: Distinct Facts (D22 Noise-Floor Caveat)

Per D22, single-run fact counts prove nothing (stdev ≈7 at n=3). This change does not modify the generation pipeline — it only changes whether the QA gate *blocks delivery* of an already-generated tour. Fact density is unchanged by definition: the same tour that was previously rejected is now delivered.

---

## Evidence: Regression Suite

```
251 passed, 3 warnings in 67.74s
```

All LOCAL tests pass including the 8 new LOCAL-85 tests.

---

## Evidence: Database Integrity

| Metric | Before | After |
|--------|--------|-------|
| `audio_tours` row count | 44 | 46 |
| Rows deleted | 0 | — |

Two tours added (IDs 54, 55). Zero deletions. Tour 29 untouched.

---

## Limitations

1. **The `_NAMED_VENUE_PATTERN` regex doesn't catch all French venue forms.** It misses "Musée d'Orsay" and "Musée du Louvre" (because it requires `Mus[ée]+e?\s+[A-Z]` — an uppercase letter after the space). Drift to these specific venues would only be caught by check 9 (other-venue-count), not by the new check 11. This is a pre-existing limitation of the shared regex, not introduced by LOCAL-85.

2. **Style issues persist.** Both tours pass factual checks but have 2–3 style failures (forbidden phrases, unearned adjectives). These are not release-blocking and are unrelated to this task.

3. **Single-run evidence for each museum.** Per D22, a single run cannot prove a fact-density change. Since this task changes only the gate threshold (not the generation prompt), fact-density change is not expected. Three-run arms would be required to prove/disprove any density shift.
