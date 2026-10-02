# SUBMISSION — LOCAL-520: Two phrasings of one venue must not be two paid generations

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-520-cache-key-normalise`
**Base:** storied (`d3d469a`) — verified `git merge-base --is-ancestor d3d469a HEAD` exits 0.

---

## TL;DR

The cache key is now built from an accent-folded, punctuation-stripped, whitespace-collapsed,
casefolded form of the location. The two Picasso rows collapse to **one** key; the three
must-not-merge pairs stay **distinct**; old rows still resolve via a retained legacy key
(migration-by-fallback, no DB rewrite). Against the **live `tour_cache` (159 rows)** the new key
collapses **3 duplicate rows** — all accent-only same-venue duplicates, including the ticket's
Picasso pair.

### Honesty note on provenance

While investigating I found the SAFE-half string normalisation **already implemented at base**,
committed under **LOCAL-500** (`1788205 — LOCAL-500: accent-fold + normalise tour_cache key (SAFE
half)`), with a unit suite `tests/test_local500_cache_key_normalise.py`. LOCAL-520 is the same
defect class (the ticket even predicts this: "Known for months, never applied to the cache key").
I did **not** rewrite a working fix. My LOCAL-520 contribution is: (a) an independent acceptance
harness named for this ticket (`tests/test_local520_cache_key_normalise.py`) that calls the real
functions — no source-grep marker (D418/D421); (b) verification of every LOCAL-520 acceptance
criterion with the real strings; and (c) the live-DB row-collapse measurement (criterion 4), which
LOCAL-500's submission did not report.

---

## The fix (string normalisation only — the SAFE half)

`tour_cache_layer1.py`:

```python
_MEANINGLESS_PUNCT = re.compile(r"[,\.\u2019\u2018']")

def _fold(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(s).lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()

def _normalize_location(location: str) -> str:
    folded = _fold(location)                       # 1. NFKD accent-fold + casefold
    depunct = _MEANINGLESS_PUNCT.sub(" ", folded)  # 2. strip ',' '.' ''' to spaces
    return re.sub(r"\s+", " ", depunct).strip()    # 3. collapse whitespace

def _cache_key(location, tour_type, total_stops) -> str:
    raw = f"{_normalize_location(location)}|{tour_type.strip().lower()}|{total_stops}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

Steps 2+3 together also fold state/country suffix spacing: `Boston, MA` and `Boston MA` both
become `boston ma`.

**Deliberately NOT done** (per scope): coordinate matching, fuzzy/semantic venue identity, token
reordering, word dropping. Those can merge *different* venues — worse than paying twice. That is
LEAD's call, made separately.

---

## Acceptance 1 — the two Picasso rows produce the SAME key (real strings)

```
A = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
B = "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"   (tour_type=museum, total_stops=3)

normalized(A) == normalized(B) == "picasso miro dali: unbound exhibition at mfa boston ma"
```

| | key |
|---|---|
| **BEFORE** (legacy, `.lower()` only) A | `5c534e722ccc84fa2dd72952f495e976bdddaf36a5c8fd78cf55915234791da3` |
| **BEFORE** B | `55caa09beb18a950372b4ce1363be3f8ebd7d5dad0283e634f7035c43f80fe00` |
| | **different → two paid generations** |
| **AFTER** (normalised) A | `80169726544a4427d6d253c652e2c6f42e21bcd9047a6c61b688a10238a795e5` |
| **AFTER** B | `80169726544a4427d6d253c652e2c6f42e21bcd9047a6c61b688a10238a795e5` |
| | **identical → one generation** |

## Acceptance 2 — pairs that must NOT merge (each tested, all distinct)

| pair (`tour_type=walking, total_stops=5`) | key prefix | distinct? |
|---|---|---|
| `Musee Matisse, Nice` | `fff21275b7d07b3a…` | ✅ |
| `Musee Marc Chagall, Nice` | `0cf741da1c342da7…` | |
| `Boston Logan International Airport` | `e53c35b640065454…` | ✅ |
| `Boston Common` | `81be5d4f622d330e…` | |
| `Sacred Heart Parish, Newton` | `58a3f949f160034a…` | ✅ |
| `Our Lady Help of Christians, Newton` | `c85a561a771554f2…` | |

## Acceptance 3 — old cached entries keep working (chosen: migration-by-fallback)

**Choice: keep old keys resolving, no DB rewrite.** `get_cached_tour` tries the normalised key
first, then falls back to `_legacy_cache_key` (the exact pre-LOCAL-500 `.strip().lower()` formula).
A legacy hit is transparently re-stored under the normalised key on the next `store_tour`, so the
estate converges to normalised keys naturally.

Why this over a one-shot migration: it is zero-downtime and reversible — no destructive `UPDATE`
against 159 live rows, and a bad normalisation could never orphan existing paid content. The only
cost is one extra indexed `SELECT` on a cache miss, which is negligible next to a tour generation.

## Acceptance 4 — row collapse against the live `tour_cache`

Measured against the running DB (`development-postgres-2-1`, `audiotours`), **159 rows**:

- Distinct OLD keys: **159**
- Distinct NEW keys: **156**
- **Rows eliminated: 3** (across 3 merge groups, each 2 rows → 1 key)

| new key | rows merged | detail |
|---|---|---|
| `80169726…` | 2 | Picasso MFA `museum/3` — **the ticket's headline case** (`Miró,Dalí` vs `Miro,Dali`) |
| `c3414fc9…` | 2 | Picasso MFA `museum/1` — same accents, different stop count |
| `84275593…` | 2 | `Musée Matisse, Nice, France` vs `Musee Matisse, Nice, France` `museum/8` |

Every collapsed group is a genuine accent-only same-venue duplicate. **No two different venues
merged.** (The ticket cites the `museum/3` Picasso pair as 6+3 hits; this DB snapshot shows the
duplicates present with lower live hit counts — the collapse behaviour is identical regardless of
counts.)

---

## Verification

```
$ python3 -m unittest tests.test_local520_cache_key_normalise -v
Ran 7 tests in 0.000s
OK
$ python3 -m unittest tests.test_local500_cache_key_normalise -v
Ran 7 tests in 0.001s
OK
```

Row-collapse count produced by loading all 159 live `tour_cache` rows and grouping by the real
`_cache_key` / `_legacy_cache_key` functions (not a re-implementation).

## Files

- `tests/test_local520_cache_key_normalise.py` — new; LOCAL-520 acceptance harness (calls real functions).
- `tour_cache_layer1.py` — normalisation already present at base (LOCAL-500); unchanged.
