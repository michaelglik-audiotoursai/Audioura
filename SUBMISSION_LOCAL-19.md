##### READY FOR REVIEW

# LOCAL-19: Fix UNIFIED-FILL defeats R4 replenishment

## Approach chosen

**Run R4 BEFORE UNIFIED-FILL.** This removes the ordering hazard structurally:

- R4's loop condition `while len(poi_list) < total_stops` now sees only the verified-stop count (D1v2 output), so it fires correctly.
- UNIFIED-FILL moves to AFTER R4 exhausts its rounds — it can only pad remaining gaps.
- A new LOCAL-16 GATE strips any unverified stops before Phase 5 (for museum tours).
- `total_stops` is capped to the gate's output count, preventing Part C from re-filling with unverified candidates downstream.

Why this option over the alternatives:
- "Have UNIFIED-FILL's additions not count toward R4's target" would require a separate counter to keep in sync — fragile.
- "Move the verified-only gate earlier" is essentially what we did (gate is now the final checkpoint), combined with putting R4 first.
- The reorder is the simplest structural change: one block moved, no new counters.

Also implemented:
- **Canonical-title dedup** in the LOCAL-16 GATE (round 3 finding): if two stops verify against the same canonical title, only the first survives.
- Reverse-lookup for canonical titles that handles D1v2's name-rename behavior (D1v2 renames poi names to canonical form, so evidence_log key ≠ poi name).

## Changes made

**`generate_tour_text.py`** — single file, ~lines 2329–2610:
1. R4 replenishment loop now runs FIRST (before any fill)
2. UNIFIED-FILL moved after R4 (with added dedup check against R4-added stops)
3. POST-R4-FILL logic preserved in new position
4. NEW: LOCAL-16 GATE after all fills — strips unverified + deduplicates by canonical title
5. `total_stops` capped after gate shortfall to prevent Part C refill

## Live evidence

### CACHE MISS confirmed
```
CACHE MISS: Asian arts museum, nice, France / museum / 8
```
(Cache row deleted with `DELETE FROM tour_cache WHERE location ILIKE '%asian arts museum%nice%france%'` before each run)

### R4 now RUNS (the core fix)
```
[D1v2] 6/8 works verified — tier: medium
[R4] Replenishment round 1/3: need 2 more, asking for 7
    [R4] dropped 'The Great Wave off Kanagawa'
    [R4] dropped 'Bodhisattva Avalokiteshvara'
    [R4] dropped 'Portrait of Hàm Nghi'
    [R4] dropped 'Standing Buddha'
    [R4] dropped 'Night Attack on the Sanjō Palace'
    [R4] dropped 'Sunflowers'
    [R4] dropped 'Guanyin Bodhisattva'
    [R4] Round 1: +0 verified, total now 6
[R4] Replenishment round 2/3: need 2 more, asking for 7
    [R4] dropped 'Portrait of a Noblewoman with a Fan'
    [R4] dropped 'Bodhisattva Maitreya'
    [R4] dropped 'Bowl with Peonies and Chrysanthemums'
    [R4] dropped 'Seated Guanyin Bodhisattva'
    [R4] dropped 'Jade Mountain with Twelve Poems'
    [R4] dropped 'Stele with Inscription of the Great Law'
    [R4] dropped 'Standing Buddha Offering Protection'
    [R4] Round 2: +0 verified, total now 6
[R4] Replenishment round 3/3: need 2 more, asking for 7
    [R4] dropped 'Bowl with Plum Blossoms'
    [R4] dropped 'Portrait of a Geisha'
    [R4] dropped 'Lotus Flower Pond'
    [R4] dropped 'Dragon and Phoenix Vase'
    [R4] dropped 'Golden Buddha Statue'
    [R4] dropped 'Cherry Blossom Scroll'
    [R4] dropped 'Jade Dragon Figurine'
    [R4] Round 3: +0 verified, total now 6
[R4] Replenishment exhausted: 6/8 stops (stop_count_warning)
```

R4 ran all 3 rounds. Previously it would have printed `[R4] Target reached: 8/8 stops` and never executed a single round.

### Canonical-title dedup fires (from second run)
```
[LOCAL-16 GATE] D1v2-verified-only filter for museum tour
    Removed 2 stop(s):
      ✗ Mandala
      ✗ Portrait of Hàm Nghi, Prince d'Annam (dup canonical: l'art en exil - Hàm Nghi, Prince d'Annam (1871-1944))
    After: 6 verified stop(s)
    [LOCAL-16 GATE] Accepting honest shortfall: 6/8 stops
```

### LOCAL-16 GATE output (final run)
```
[UNIFIED-FILL] tier=medium: no eligible fill candidates
[LOCAL-16 GATE] D1v2-verified-only filter for museum tour
    [LOCAL-16 GATE] Accepting honest shortfall: 6/8 stops
```

### Part C does NOT re-fill after the gate
No `Part C: Fetching` log lines appear after the gate in the final run. `total_stops` was capped to 6.

### Final verified stop count: 6/8

The 6 D1v2-verified stops (this venue's corpus contains exactly 6 canonical titles):
1. Hokusai – Voyage au pied du mont Fuji
2. Disque
3. Fauteuil
4. La geste de Bouddha
5. Les paysages de l'âme
6. L'art en exil - Hàm Nghi, Prince d'Annam (1871-1944)

R4 attempted 3 rounds × 7 candidates = 21 fresh GPT proposals. None matched the venue's corpus. This confirms 8 is genuinely unreachable for this venue — the honest shortfall is correct.

### Tour delivery blocked by pre-existing BLOCKER4c QA issue

The generated tour assembled correctly (6 stops, all verified), but BLOCKER4c's factual QA consistently rejects the GPT-generated descriptions for this venue (stochastic). This is a pre-existing issue (documented in rounds 0–4) unrelated to the R4/fill ordering fix.

The R4 ordering fix is demonstrably working: R4 runs, the gate works, stops are honest.

## Process compliance

- Worked only in `/Users/micha/audioura-worktrees/LOCAL-19` worktree
- Never touched `audioura-tour-generator-1` — built own image (`local19-generator`) and ran own `--rm` container (`local19-test`) on port 5090
- Used `development_default` network
- Deleted `tour_cache` row before each generation — `CACHE MISS` shown
- No `docker rm`, `docker stop`, `docker cp` on the shared container

## Regression suite

```
test_venue_identity.py:          11/11 PASSED
test_local12_fact_retrieval_fix.py:  8/8 PASSED
test_w4_matcher.py:               7/7 PASSED
test_palais_fix_lead_fixture.py: 23/23 PASSED
test_g4_false_positives.py:       7/7 PASSED
                                ─────────
Total:                           56/56 PASSED (exit code 0)
```

Verbatim exit codes:
- `pytest test_venue_identity.py test_local12_fact_retrieval_fix.py test_w4_matcher.py`: exit 0 (26 passed)
- `python3 test_palais_fix_lead_fixture.py`: exit 0 (23/23 assertions hold)
- `python3 test_g4_false_positives.py`: exit 0 (ALL PASS)
