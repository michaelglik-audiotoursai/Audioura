# SUBMISSION — LOCAL-500: cache-key normalisation (the SAFE half)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-500-cache-key-normalise`
**Base:** storied @ `5b269de` (`git merge-base --is-ancestor 5b269de HEAD` → exit 0)
**File changed:** `tour_cache_layer1.py` (+ regression test `tests/test_local500_cache_key_normalise.py`)

## Problem

`tour_cache`'s key was `SHA256(location.strip().lower() | tour_type | total_stops)`.
`.lower()` was the only normalisation, so an accent, a comma or a double space
minted a brand-new venue and we paid to generate the same tour twice. This is the
D243 defect class ("accent-fold every stop_corpus join") never applied to the
cache key.

## What changed

Added `_normalize_location()`, applied string-only normalisation, and split the
key into the normalised `_cache_key` (used for all reads and writes) and
`_legacy_cache_key` (read-only fallback). Normalisation, in order:

1. **Accent-fold + casefold** via NFKD, dropping combining marks (`Miró → miro`, `Musée → musee`).
2. **Strip meaningless punctuation** `,` `.` `'` (ASCII and typographic apostrophes) → replaced with a space, not deleted, so `Boston,MA` does not become `bostonma`.
3. **Collapse internal whitespace** and strip ends.

Steps 2+3 together also normalise state/country suffix spacing: `Boston, MA` and
`Boston MA` both fold to `boston ma`.

**Explicitly NOT done** (out of scope, LEAD's call): coordinate matching,
fuzzy/semantic venue identity, token reordering, word dropping. Merging two
*different* venues serves a listener the wrong tour — far worse than paying twice.

## Acceptance

### 1. The Picasso pair produces the same key — real strings, real keys

```
A: "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
B: "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"

              OLD key (.strip().lower())                                      NEW key (normalised)
A  5c534e722ccc84fa2dd72952f495e976bdddaf36a5c8fd78cf55915234791da3   80169726544a4427d6d253c652e2c6f42e21bcd9047a6c61b688a10238a795e5
B  55caa09beb18a950372b4ce1363be3f8ebd7d5dad0283e634f7035c43f80fe00   80169726544a4427d6d253c652e2c6f42e21bcd9047a6c61b688a10238a795e5
                        ^ DIFFERENT (the bug)                                       ^ IDENTICAL (fixed)

NEW normalised form (both): 'picasso miro dali: unbound exhibition at mfa boston ma'
```

(Keys shown for `tour_type=museum, total_stops=3`. The colon is preserved — it is
identical in both strings, so it does not split them.)

### 2. Pairs that must NOT merge — each tested, each stays distinct

| Pair | New keys distinct? |
|---|---|
| `Musee Matisse, Nice` vs `Musee Marc Chagall, Nice` | ✅ yes |
| `Boston Logan International Airport` vs `Boston Common` | ✅ yes |
| `Sacred Heart Parish, Newton` vs `Our Lady Help of Christians, Newton` | ✅ yes |

Verified by `tests/test_local500_cache_key_normalise.py::TestDifferentVenuesDoNotMerge` (passing).

### 3. Existing cached entries keep working — **migration-by-fallback (no DB rewrite)**

**Choice: read-time legacy fallback, not a data migration.**

`get_cached_tour` now tries the normalised key first, then falls back to
`_legacy_cache_key` (the exact old `.strip().lower()` formula). So every row
written before this change still resolves on read. New writes always use the
normalised key, and a legacy hit is re-stored under the normalised key on the next
`store_tour`, so the estate converges naturally.

**Why fallback over a migration:**
- **Non-destructive & reversible** — no `UPDATE`/`DELETE` on the primary key, nothing to roll back.
- **No deploy-time DB write access required** — the fix is pure code.
- **Avoids PK-collision handling** — a migration would have to merge colliding rows (the whole point is that some old keys map to one new key), which means choosing a survivor and deleting the rest. Fallback sidesteps that entirely; duplicates simply stop being written and age out.

Cost of fallback: at most one extra indexed PK lookup on a cache miss for a
pre-migration venue. Negligible, and only on the miss path.

### 4. How many current `tour_cache` rows collapse under the new key

Measured against the live `tour_cache` table (`development-postgres-2-1`, 154 rows)
by applying the real `_cache_key` to every row:

- **Total rows:** 154
- **Distinct keys under new scheme:** 151
- **Groups that collapse (>1 row → 1 key):** 3
- **Net duplicate rows eliminated:** 3

The three collapsing groups:

```
[2 rows]  Picasso Miro/Miró … MFA, Boston, MA   | museum | 3
[2 rows]  Musee/Musée Matisse, Nice, France     | museum | 8
[2 rows]  Picasso Miro/Miró … MFA, Boston, MA   | museum | 1
```

Each is an accent-only duplicate — exactly the paid-twice defect. (The Picasso
exhibition appears at two different stop counts, 1 and 3; the ticket's "6 hits /
3 hits" describes request volume, while rows group by
`location|tour_type|total_stops`.)

## Verification run

```
python3 -m unittest tests.test_local500_cache_key_normalise -v
Ran 7 tests in 0.000s — OK
python3 -m py_compile tour_cache_layer1.py — OK
```
