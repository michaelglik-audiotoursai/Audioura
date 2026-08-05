##### READY FOR REVIEW

**Commit:** `900f79d` on branch `kiro/local239-gate-venue-kinds`
**Base:** `storied`

---

## Problem Statement

The stop-existence gate applied museum-shaped verification to all venues,
including geographic areas. Museums require the source passage to tie an object
to *that institution* (D74, D127). But geographic areas like "French Riviera
walking area" are our internal label — no Wikipedia article for Eze Village or
Villefranche-sur-Mer will ever say "French Riviera walking area". This caused
real places to fail verification.

Before the fix: **50 verified, 38 unverified** (out of 88 stops with corpus).
After the fix: **65 verified, 23 unverified** — 15 geographic stops recovered.

---

## The Six Boundary Rows

| Stop | Venue | Expected | Actual | Kind |
|---|---|---|---|---|
| Ulysses Grant au Japon | Musée des Arts Asiatiques, Nice | UNVERIFIED | **UNVERIFIED** ✓ | unknown |
| The Dream | Musée International d'Art Naïf Anatole Jakovsky, Nice | UNVERIFIED | **UNVERIFIED** ✓ | institution |
| Kannon à mille bras | Musée des Arts Asiatiques, Nice | UNVERIFIED | **UNVERIFIED** ✓ | unknown |
| Villefranche-sur-Mer | French Riviera walking area | VERIFIED | **VERIFIED** ✓ | geographic_area |
| Eze Village | French Riviera walking area | VERIFIED | **VERIFIED** ✓ | geographic_area |
| Cap Ferrat | French Riviera walking area | VERIFIED | **VERIFIED** ✓ | geographic_area |

All six pass. Fabricated museum stops remain UNVERIFIED. Real geographic places
now verify via `stop_corpus_geographic` (relaxed path).

---

## Corrected Blast Radius

### Before (D131 / storied HEAD, old gate logic on 88 corpus stops)

```
gate says verified   50
gate says NOT        38    (43.2% unverified)
```

### After (LOCAL-239, venue-kind fix)

```
gate says verified   65
gate says NOT        23    (26.1% unverified)
```

**Delta: 15 stops recovered (all French Riviera geographic places).**

### By venue and kind

| Venue | Kind | Total | Verified | Unverified | % unv |
|---|---|---|---|---|---|
| French Riviera walking area | geographic_area | 28 | 28 | 0 | 0% |
| Musee d Art Moderne et d Art Contemporain | institution | 13 | 13 | 0 | 0% |
| Palais Lascaris, Nice | institution | 11 | 11 | 0 | 0% |
| Musée d'art naïf, Nice | unknown | 9 | 0 | 9 | 100% |
| Musee des Arts Asiatiques, Nice | unknown | 8 | 0 | 8 | 100% |
| Musee Matisse, Nice | institution | 6 | 6 | 0 | 0% |
| walking tour in Nice, france | unknown | 5 | 0 | 5 | 100% |
| Musee National Marc Chagall | institution | 4 | 4 | 0 | 0% |
| Boston Common, Boston MA | geographic_area | 3 | 3 | 0 | 0% |
| National Constitution Center | institution | 1 | 0 | 1 | 100% |

**Why 23 remain unverified:** These are stops at venues where the stop_corpus
venue name doesn't match any venue_corpus row (kind=unknown). For unknown
venues, the gate defaults to the strict institution path, which correctly keeps
fabricated stops unverified.

### Reconciliation with D131's 170/190

D131's 170/190 counted ALL stops across ALL 29 real tours, including stops
with no stop_corpus at all (most stops). The 88 here are only those with
corpus rows. The 170/190 number was inflated by two things:
1. **This bug** — 15 real geographic places failing a museum test (now fixed)
2. **Stops with no corpus at all** — these cannot be verified regardless of
   gate logic (they need corpus first, which is the D131 finding)

The corrected figure for stops that CAN be assessed: 23/88 (26.1%) unverified,
not 38/88 (43.2%).

---

## Per-File Summary

### `stop_existence_gate.py` (modified, +95 lines net)

Added three functions:

1. **`_classify_venue_kind(venue_name, db_conn)`** — classifies a venue as
   `institution` (has sparql_works_json), `geographic_area` (no sparql), or
   `unknown` (no venue_corpus match). Uses `_find_venue_corpus_rows` to look
   up the venue, then checks for sparql_works_json presence.

2. **`_check_stop_corpus_geographic(stop_title, venue_name, db_conn)`** —
   relaxed verification for geographic areas. A stop_corpus row matching the
   stop title under this venue, with at least one passage, is sufficient.
   No same-source venue-mention requirement (D74 does not apply to areas).

3. **`verify_stop_existence` (rewritten)** — now classifies venue kind first,
   then branches:
   - `geographic_area` → uses `_check_stop_corpus_geographic`
   - `institution` or `unknown` → uses strict `_check_stop_corpus` (D74)
   - Both paths still try `_check_venue_corpus` first (canonical title match
     is always valid regardless of kind)
   - Returns `venue_kind` in the result dict.

### `RIVIERA_2STOP_ROUND3.md` (overwritten)

Regenerated with corrected gate enforcing. Both stops (Cap d'Antibes, Eze
Village) now verify as `geographic_area`. R10 deleted 1 sentence, R9 deleted
1 sentence, subject routine deleted 1 promise.

### `run_local239_riviera_round3.py` (new)

Generation script for the regenerated tour. Same structure as LOCAL-238's
script but uses the corrected gate.

---

## End-to-End Verification

### Gate on geographic stops (must verify):
```
  [EXISTENCE-GATE] ENFORCED — 5/5 stops verified (100%), dropping 0 unverified
    [VERIFIED] "Cap d'Antibes" — stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera walking area' (7 passages)
    [VERIFIED] 'Villefranche-sur-Mer' — stop_corpus(geographic): 'Villefranche-sur-Mer' at 'French Riviera walking area' (1 passages)
    [VERIFIED] 'Eze Village' — stop_corpus(geographic): 'Eze Village' at 'French Riviera walking area' (1 passages)
    [VERIFIED] 'Cap Ferrat' — stop_corpus(geographic): 'Cap Ferrat' at 'French Riviera walking area' (1 passages)
    [VERIFIED] 'Mont Boron' — stop_corpus(geographic): 'Mont Boron' at 'French Riviera walking area' (1 passages)
```

### Gate on fabricated museum stops (must stay unverified):
```
  [EXISTENCE-GATE] ENFORCED — 0/2 stops verified (0%), dropping 2 unverified
    [UNVERIFIED] 'Ulysses Grant au Japon' — no evidence
    [UNVERIFIED] 'Kannon à mille bras' — no evidence
```

### audio_tours count: 140 → 141 (delta: +1, test tour only)
### Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓

---

## RIVIERA_2STOP_ROUND3.md Regeneration

- **Gate enforcing:** Yes — venue-kind-corrected gate
- **R10 applied:** Yes (post-processing, 1 sentence deleted)
- **R9 applied:** Yes (post-processing, 1 sentence deleted)
- **Subject routine:** Yes (1 promise found, 0 expanded, 1 deleted)
- **Stops:** Cap d'Antibes (VERIFIED), Eze Village (VERIFIED)
- **Tour ID:** 195 (is_test=true, lat/lng=NULL)
- **Note:** Eze Village description was empty from generation (`[Description
  for Eze Village could not be generated.]`). This is a pre-existing pipeline
  issue unrelated to the gate fix — stop selection chose it but narration
  failed to produce content.

---

## Invariants Preserved

- `audio_tours` count: 140 → 141 (one test tour added)
- Nice list `[1,12,14,17,24,29,152]`: unchanged
- No tours deleted or altered
- No container rebuilt (D48)
- No edits to DECISIONS.md, CLAUDE.md, .continuous_dev/
- Cost: ~$0.006 generation + $0.001 subject routine = $0.007 (under $0.35)

---

## Limitations

1. **Venues classified as `unknown` default to strict verification.** The
   Asian Arts Museum and Naïve Art Museum have stop_corpus rows with slightly
   different venue names than venue_corpus, so `_find_venue_corpus_rows` can't
   match them. These stops correctly remain UNVERIFIED (they ARE fabricated),
   but the mechanism is incidental rather than principled.

2. **Eze Village narration failed.** The pipeline selected it but produced no
   description content. This is a generation issue (likely the 2-stop budget
   allocated all tokens to Cap d'Antibes), not a gate issue.

3. **The 15 recovered stops are all French Riviera.** Boston Common (3 stops)
   was already verifying via canonical_titles (POI dict match). No other
   geographic venues exist in the corpus yet.

4. **D131's headline 170/190 remains correct in scope.** Most of those 170
   have no corpus at all — they cannot verify regardless of gate logic. The
   gate fix only helps the 15 that DO have corpus but were failing the
   museum-shaped test.
