# SUBMISSION — LOCAL-3500: two phrasings of one venue must not be two paid generations

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-3500-cache-key-normalise`
**Base:** storied @ `e1341e6` (`git merge-base --is-ancestor e1341e6 HEAD` → exit 0)
**Files:** `tour_cache_layer1.py` (fix already present in base — see "Status" below),
`tests/run_local3500_acceptance.py` (new evidence driver),
`tests/measure_local3500_collapse.py` (new collapse measurement)

## Problem

`tour_cache` stored the same exhibition twice, differing only by accents:

```
Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA   6 hits
Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA   3 hits
```

The key was `SHA256(location.strip().lower() | tour_type | total_stops)`. `.lower()`
was the only normalisation, so an accent, a comma or a double space minted a new
venue and we paid to generate the same tour twice. This is the D243 defect class
("accent-fold every stop_corpus join") never applied to the cache key.

## Status — the SAFE-half string fix is already in the tree

The string normalisation this ticket asks for already lives in `tour_cache_layer1.py`
on the base (`e1341e6`), delivered under LOCAL-500 — the identical defect class.
The relevant primitives:

- `_fold()` — NFKD accent-strip + casefold + whitespace collapse.
- `_normalize_location()` — accent-fold, strip meaningless punctuation (`,` `.` `'`
  and typographic apostrophes) to spaces, collapse whitespace. This folds
  `Boston, MA` and `Boston MA` to one form.
- `_cache_key()` — normalised location + `tour_type` + stop bucket.
- `_legacy_cache_key()` — read-only reproduction of the old `.strip().lower()`
  formula for backward resolution.

LOCAL-3500 is therefore the **acceptance** for that fix on the current base: prove
the criteria against the real strings and the live table, and confirm the SAFE-only
boundary (no coordinate/fuzzy/semantic merging — that stays LEAD's decision). All
new artefacts CALL the real functions; none grep source for a marker (D418/D421).

## Acceptance

### 1. The Picasso pair produces the SAME key — real strings, real keys

From `tests/run_local3500_acceptance.py` (`tour_type=museum`, `total_stops=3`):

```
A: 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'
B: 'Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA'

OLD key (.strip().lower()):
  A  5c534e722ccc84fa2dd72952f495e976bdddaf36a5c8fd78cf55915234791da3
  B  55caa09beb18a950372b4ce1363be3f8ebd7d5dad0283e634f7035c43f80fe00   -> DIFFERENT (the bug)
NEW key (normalised):
  A  80169726544a4427d6d253c652e2c6f42e21bcd9047a6c61b688a10238a795e5
  B  80169726544a4427d6d253c652e2c6f42e21bcd9047a6c61b688a10238a795e5   -> IDENTICAL (fixed)

NEW normalised form (both): 'picasso miro dali: unbound exhibition at mfa boston ma'
```

The colon is preserved — it is identical in both strings, so it never split them.

### 2. Pairs that must NOT merge — each tested, each stays distinct

From the same driver (`tour_type=walking`, `total_stops=5`):

| Pair | Distinct under new key? |
|---|---|
| `Musee Matisse, Nice` vs `Musee Marc Chagall, Nice` | ✅ distinct |
| `Boston Logan International Airport` vs `Boston Common` | ✅ distinct |
| `Sacred Heart Parish, Newton` vs `Our Lady Help of Christians, Newton` | ✅ distinct |

These differ in real venue words (`Matisse` vs `Marc Chagall`, `Airport` vs
`Common`, `Sacred Heart Parish` vs `Our Lady Help of Christians`), so string
normalisation leaves them distinct. This is the SAFE boundary holding: only
accent/punct/space noise is folded, never venue-identifying words.

### 3. Existing cached entries keep working — migration-by-fallback (chosen)

**Choice: read-time legacy fallback, NOT a data migration.**

`get_cached_tour` tries the normalised key first, then falls back to
`_legacy_cache_key` (the exact old `.strip().lower()` formula). Every row written
before this change still resolves on read; new writes always use the normalised
key, and a legacy hit is re-stored under the normalised key on the next
`store_tour`, so the estate converges without a DB rewrite.

**Why fallback over a migration:**
- Non-destructive and reversible — no `UPDATE`/`DELETE` on the primary key.
- No deploy-time DB write access needed — pure code.
- Avoids PK-collision handling — a migration would have to pick a survivor among
  rows that now share one key and delete the rest; fallback sidesteps that, and
  duplicates simply stop being written and age out.

Cost: at most one extra indexed PK lookup on a cache miss for a pre-migration
venue — only on the miss path.

### 4. How many current `tour_cache` rows collapse under the new key

Measured against the live `tour_cache` table (`development-postgres-2-1`, **168 rows**)
by applying the real `_cache_key` to every row
(`tests/measure_local3500_collapse.py`). The live key folds in TWO independent
changes, so the report separates them:

| Scheme | Distinct keys | Net rows removed |
|---|---|---|
| Legacy (`.strip().lower()` + exact stops) | 164 | — |
| **String normalisation ONLY** (LOCAL-3500 scope, exact stops) | 160 | **8** |
| Full key (string norm **+** stop bucket, LOCAL-494) | 143 | 25 |

**LOCAL-3500 (the accent/punct/space fix) collapses 8 rows.** The four
string-attributable groups — rows that were distinct only because of accents or
comma spacing — are:

```
[2] 'Picasso, Miró/Miro, Dalí/Dali: … MFA, Boston, MA' | museum | 3   (accents)
[2] 'Picasso, Miró/Miro, Dalí/Dali: … MFA, Boston, MA' | museum | 1   (accents)
[2] 'Musée/Musee Matisse, Nice, France'                | museum | 8   (accent)
[2] 'Museum of Fine Arts, Boston, MA' vs 'Boston MA'   | contained | 4 (comma spacing)
```

The remaining 17 rows down to 143 collapse from LOCAL-494 stop-bucketing (e.g.
the same venue at 2 and 3 stops sharing one bucket), which is a separate change
already present in the key and out of LOCAL-3500's scope. Reported here for
completeness and to keep the attribution honest.

## Verification run

```
python3 tests/run_local3500_acceptance.py                 -> RESULT: ALL PASS
python3 tests/measure_local3500_collapse.py               -> 8 rows (string), 25 (string+bucket)
python3 -m unittest tests.test_local500_cache_key_normalise -> Ran 7 tests — OK
python3 -m py_compile tour_cache_layer1.py tests/run_local3500_acceptance.py tests/measure_local3500_collapse.py -> OK
```
