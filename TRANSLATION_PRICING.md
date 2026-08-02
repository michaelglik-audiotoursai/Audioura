# Translation Pricing Options

**Task:** LOCAL-140  
**Branch:** kiro/local140-translation-pricing-options  
**API spend:** $0.00  
**Date:** 2026-08-02  

---

## 1. Is the Second Translation Pass Avoidable?

**Yes. The second pass is avoidable.** Eliminating it would cut translation
cost by ~44% — from $0.53 to $0.30.

### What the code does today

In `translate_tour_with_audio` (translation_service.py, lines 286–297), each
stop is processed in a loop with **two** `self.translate_text()` calls:

```python
# Line 290 — translates full stop text (for the .txt file in the ZIP)
translated_stop = self.translate_text(stop_text, target_language)

# Line 294 — translates nav-stripped text separately (for Polly TTS input)
tts_text = self.translate_text(self._strip_nav_fields_for_tts(stop_text), target_language)
```

The first call translates the entire stop (narrative + all structured fields).
The second call translates a nav-stripped version (same text minus Address,
Coordinates, Type/Specialty, Specific Examples, Operational Details — about
5–10% of the text removed). So **~92% of the text is translated identically
in both calls.**

### Why the second pass exists

`_strip_nav_fields_for_tts` removes structured metadata lines (address,
coordinates, etc.) that would sound unnatural when read aloud by Polly. The
current code strips these from the **English** source before translating, so
the TTS text never contains them.

The alternative — strip from the **already-translated** text — was presumably
not chosen because the nav field labels change per language (French:
"Type/Spécialité\xa0:", "Exemples spécifiques\xa0:", etc.) and `_strip_nav_fields_for_tts`
matches only English prefixes.

### Why it is avoidable

The translated output has a predictable structure (examined in the DB):

```
Stop 1: La fuite en Égypte        ← title (keep for TTS)
                                    ← blank
Coordinates: 43.6972, 7.2764       ← English (restored by _restore_metadata_labels)
Address: Museum Of Naïve Art, ...  ← English (restored by _restore_metadata_labels)
                                    ← blank
Type/Spécialité : Art religieux    ← translated nav field (strip for TTS)
Exemples spécifiques : ...         ← translated nav field (strip for TTS)
Informations sur le musée : ...    ← translated nav field (strip for TTS)
Orientation : À l'approche...      ← keep for TTS
                                    ← blank
[narrative paragraphs]             ← keep for TTS
```

The `_restore_metadata_labels` method already contains logic
(`_is_translated_metadata`) that detects and removes translated
Coordinates/Address lines. Extending this approach to the other nav field
types (Type/Specialty, Specific Examples, Operational Details) is
straightforward because:

1. The structure is line-based — each field occupies exactly one line.
2. Each translated field line has a colon within the first 30–40 characters
   (the pattern is `<Translated Label>\xa0: <value>`).
3. The set of fields to strip is known and fixed (5 prefixes).
4. The English source text is available as a template — one can identify
   which line positions held nav fields and remove the corresponding lines
   from the translated output.

**What would break if naively removed:** Nothing breaks in the TTS audio
path. The full-text .txt file path is unchanged (it still uses the first
translation call). The only risk is a subtle translation quality difference:
translating with vs without surrounding context. In practice, AWS Translate
processes text segment by segment; the nav fields are self-contained lines
that don't provide meaningful context to the narrative paragraphs.

**What it saves:**

| Tour | Current cost | 2nd pass cost | After removal | Saving |
|------|-------------|---------------|---------------|--------|
| 14   | $0.5651     | $0.2532       | $0.3119       | 44.8%  |
| 21   | $0.4863     | $0.2103       | $0.2760       | 43.2%  |
| 27   | $0.5418     | $0.2356       | $0.3062       | 43.5%  |
| 28   | $0.4746     | $0.2076       | $0.2670       | 43.7%  |
| 44   | $0.5913     | $0.2571       | $0.3342       | 43.5%  |
| **Mean** | **$0.5318** | **$0.2327** | **$0.2991** | **43.8%** |

**Recommendation for follow-up:** Create a separate task to implement the
single-pass optimization. The change is localized (only the loop body in
`translate_tour_with_audio` + a new `_strip_nav_fields_from_translated`
helper), but needs testing against multiple language pairs to confirm TTS
quality is not degraded.

---

## 2. Cache Hit Rate — Insufficient Data

### What the ledger shows

```
operation_type          | cache_hit | count | total_cost
─────────────────────────────────────────────────────────
translation_generate    | False     | 1     | $0.3720
translation_cache_hit   | True      | 1     | $0.0000
```

**Two rows total.** The cost_ledger was introduced on 2026-07-31 18:15 UTC.
Of the 12 translations in the `audio_tours` table, 11 were created before
that date. Only 1 fresh generation and 1 cache hit have been metered.

### The translation cache in the service code

The cache mechanism is in `translate_tour_with_audio` (line 273):

```python
cursor.execute(
    "SELECT id FROM audio_tours WHERE original_tour_id = %s AND content_language = %s",
    (original_tour_id, target_language)
)
existing = cursor.fetchone()
if existing:
    return existing[0], True  # cache hit
```

This is a generation-level cache, not a delivery-level cache. It prevents
regenerating a translation that already exists — but it does not track how
many times that existing translation is subsequently downloaded/served.

### What the database does tell us

- 12 translated tours exist across 8 source tours
- Each (tour_id, language) pair has exactly 1 row — no accidental duplicates
- No `tour_requests` rows track non-English delivery
- No download counter exists on translated tours

### Verdict

**Insufficient data to compute a meaningful cache hit rate.** The ledger has
exactly 1 fresh + 1 cache hit (50% rate) but n=2 is meaningless.

The delivery-level re-serve rate (how many users receive a pre-existing
translation without triggering generation) is **not tracked at all**. There
is no download counter, no delivery log for translations, and no way to
determine amortised cost per served translation from existing data.

Query used:
```sql
SELECT operation_type, cache_hit, COUNT(*), SUM(our_cost_usd)
FROM cost_ledger WHERE operation_type LIKE 'translation%'
GROUP BY operation_type, cache_hit;
```

---

## 3. Pricing Options

All options use measured cost = **$0.532** (n=5, stdev $0.050).
"Single-pass" cost = **$0.299** (if the second translation pass is eliminated).

### Reference: tour generation pricing

| | Our cost | User pays (×5) |
|---|---|---|
| Tour generation | $0.068 | $0.34 |
| Michael's ceiling | — | $1.30 |

### Options table

| # | Option | User pays | Our margin | Ceiling? | Key assumption |
|---|--------|-----------|-----------|----------|----------------|
| 1 | ×5 as today (two passes) | **$2.66** | $2.13 | ❌ BREACH (2× ceiling) | Accepts that translation costs 8× a tour |
| 2 | ×5 after eliminating 2nd pass | **$1.50** | $1.20 | ❌ Breach (by $0.20) | Single-pass optimization ships |
| 3 | ×2.5 multiplier on translations only (two passes) | **$1.33** | $0.80 | ≈ ceiling | Half the standard margin |
| 4 | ×2.5 after eliminating 2nd pass | **$0.75** | $0.45 | ✅ well under | Optimization ships; margin still 150% of cost |
| 5 | Flat $1.29 (two passes) | **$1.29** | $0.76 | ✅ at ceiling | Eats variance; some translations are $0.59 → margin $0.70 |
| 6 | Flat $1.29 after single pass | **$1.29** | $0.99 | ✅ at ceiling | Maximum margin within ceiling |
| 7 | Flat $0.75 (two passes) | **$0.75** | $0.22 | ✅ | Low margin; loss on high-end tours ($0.59 cost) |
| 8 | Flat $0.75 after single pass | **$0.75** | $0.45 | ✅ | Comfortable after optimization |
| 9 | First-requester pays ×5, free thereafter | **$2.66 / $0.00** | $2.13 total per translation | Depends on re-serve | Arbitrary: penalizes whoever asks first |
| 10 | Shared cost: charge all requesters equally until break-even | Complex | Varies | Requires delivery tracking | Needs infrastructure that doesn't exist |

### Worked example: "Tour + 5 translations" scenario

A user generates a tour and translates it into 5 languages:

| Option | Tour | 5 translations | Total | Within $10 top-up? |
|--------|------|---------------|-------|---------------------|
| 1 (×5 today) | $0.34 | $13.30 | $13.64 | ❌ |
| 2 (×5 single-pass) | $0.34 | $7.48 | $7.82 | ✅ |
| 4 (×2.5 single-pass) | $0.34 | $3.74 | $4.08 | ✅ |
| 5 (flat $1.29) | $0.34 | $6.45 | $6.79 | ✅ |
| 8 (flat $0.75 single-pass) | $0.34 | $3.75 | $4.09 | ✅ |

### Option 9 detail: "first-requester pays, free thereafter"

This matches Michael's stated principle ("costs nothing if pre-translated").
Amortised cost per *delivered* translation depends on re-serve rate:

| Total deliveries | Amortised cost/user | Note |
|-----------------|--------------------|----|
| 1 (never re-served) | $2.66 | Worst case — same as option 1 |
| 2 | $1.33 | At ceiling |
| 3 | $0.89 | Under ceiling |
| 5 | $0.53 | Under ceiling |
| ∞ | $0.00 | The limit |

**Problem:** We cannot track delivery count today. There is no download
counter on translated tours, no delivery log, and no way to determine how
many users received a given translation. The principle is sound but the
infrastructure to implement shared-cost or amortised pricing does not exist.

### An option I think is better: Optimize first, then ×5

**Eliminate the second pass (separate task), then keep ×5 on the reduced
cost.** Result: user pays $1.50. This barely breaches the $1.30 ceiling but:

- Maintains a uniform multiplier across all operations (simpler system)
- Provides strong margin ($1.20 per translation, 400% markup)
- A tiny ceiling adjustment ($1.30 → $1.50) is less disruptive than a
  translation-specific pricing rule
- No new infrastructure needed (no delivery tracking, no per-operation
  multiplier logic)

If the $1.30 ceiling is firm and non-negotiable, **option 4 (×2.5 after
optimization)** gives $0.75/translation with $0.45 margin — still profitable,
well under ceiling, and a straightforward code change (one multiplier
override for translation operations in `pricing.py`).

---

## 4. Summary of Inputs for Michael's Decision

1. **The second translation pass is avoidable** — saving ~44% ($0.23/translation).
   This should be done regardless of pricing decision. Separate task needed.

2. **Cache hit rate is unknown** — ledger has 2 rows (n too small).
   Delivery-level re-serve tracking does not exist.

3. **The $1.30 ceiling cannot be met at ×5 with the current two-pass cost**
   ($2.66 is 2× the ceiling). Even with single-pass optimization, ×5
   gives $1.50 — still above by $0.20.

4. **To stay under $1.30**: either lower the translation multiplier (×2.5
   gives $1.33 today or $0.75 after optimization), or set a flat price
   ($1.29 or below).

5. **The "first-requester pays, free thereafter" model** aligns with
   Michael's stated philosophy but requires delivery tracking infrastructure
   that doesn't exist. Could be a future enhancement.

---

*No code was changed. No API calls were made. No containers were touched.*
